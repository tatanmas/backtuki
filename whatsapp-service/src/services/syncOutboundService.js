/**
 * Sync service: captura mensajes enviados desde otros dispositivos (teléfono, etc.)
 * whatsapp-web.js NO emite message_create para mensajes con isNewMsg=false (synced).
 * Este sync periódico los captura vía fetchMessages y los envía a Django.
 */
const config = require('../config');
const contactHelper = require('../utils/contactHelper');
const chatHelper = require('../utils/chatHelper');
const { createLogger } = require('../utils/logger');

const logger = createLogger('SyncOutbound');

const SYNC_INTERVAL_MS = 45000; // 45 segundos
const MESSAGES_PER_CHAT = 40;
const MAX_AGE_SECONDS = 300; // Solo mensajes de los últimos 5 min (evita re-enviar todo el historial)
const MEDIA_PLACEHOLDERS = {
    ptt: '[Audio de voz]',
    audio: '[Audio]',
    image: '[Imagen]',
    video: '[Video]',
    document: '[Documento]',
    sticker: '[Sticker]',
    location: '[Ubicación]',
};

/** IDs ya enviados en esta sesión (evita duplicados en el mismo ciclo) */
const sentThisCycle = new Set();
let lastCycleClear = Date.now();

function buildPayloadFromMessage(message, chat, chatId, isGroup, phoneNumber, chatName, whatsappName, senderName, senderPhone) {
    const isFromMe = message.fromMe;
    const mediaType = message.type || 'chat';
    let text = message.body || '';
    if (!text && MEDIA_PLACEHOLDERS[mediaType]) {
        text = MEDIA_PLACEHOLDERS[mediaType];
    } else if (!text && mediaType !== 'chat') {
        text = `[${mediaType}]`;
    }
    const whatsappId = message.id?._serialized || message.id?.id || String(message.id);
    return {
        id: whatsappId,
        phone: phoneNumber || chatId.replace('@c.us', '').replace('@g.us', ''),
        chat_id: chatId,
        chat_type: isGroup ? 'group' : 'individual',
        chat_name: chatName,
        whatsapp_name: whatsappName,
        profile_picture_url: null,
        text: text || '',
        timestamp: message.timestamp,
        from_me: isFromMe,
        sender_name: senderName || null,
        sender_phone: senderPhone || null,
        media_type: mediaType,
        reply_to_whatsapp_id: null, // sync simplificado, sin quoted
    };
}

async function postMessageToDjango(payload) {
    const djangoUrl = `${config.DJANGO_API_URL}/api/v1/whatsapp/webhook/process-message/`;
    try {
        const response = await fetch(djangoUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        return response.ok;
    } catch (e) {
        logger.warn('Sync POST failed', { error: e.message });
        return false;
    }
}

async function syncChatMessages(client, chat) {
    const chatId = chat.id?._serialized || (typeof chat.id === 'string' ? chat.id : null);
    if (!chatId) return 0;

    const isGroup = chat.isGroup;
    let chatName = chatHelper.getChatDisplayName(chat);
    let whatsappName = null;
    let phoneNumber = isGroup ? chatId.replace('@g.us', '') : contactHelper.extractPhoneFromId(chatId);
    if (!isGroup && phoneNumber) {
        chatName = contactHelper.formatPhoneNumber(phoneNumber);
    }

    let messages = [];
    try {
        messages = await chat.fetchMessages({ limit: MESSAGES_PER_CHAT });
    } catch (e) {
        logger.debug('fetchMessages failed', { chatId, error: e.message });
        return 0;
    }

    const nowSec = Math.floor(Date.now() / 1000);
    const cutoff = nowSec - MAX_AGE_SECONDS;
    let sent = 0;

    for (const msg of messages) {
        const ts = msg.timestamp;
        if (typeof ts !== 'number' || ts < cutoff) continue;

        const wid = msg.id?._serialized || msg.id?.id || String(msg.id);
        const key = `${chatId}:${wid}`;
        if (sentThisCycle.has(key)) continue;

        let senderName = null;
        let senderPhone = null;
        if (isGroup && !msg.fromMe && msg.author) {
            const authorStr = typeof msg.author === 'string' ? msg.author : (msg.author?._serialized || '');
            const basic = contactHelper.getBasicContactInfoFromId(authorStr || '');
            senderPhone = basic.number || authorStr.replace(/@c.us|@g.us|@lid/g, '').replace(/\D/g, '') || null;
            senderName = msg._data?.pushname || msg._data?.notifyName || null;
        }

        const payload = buildPayloadFromMessage(msg, chat, chatId, isGroup, phoneNumber, chatName, whatsappName, senderName, senderPhone);
        const ok = await postMessageToDjango(payload);
        if (ok) {
            sentThisCycle.add(key);
            sent++;
        }
    }
    return sent;
}

let syncInProgress = false;

async function runSync() {
    if (!config.isReady || !config.client) return;
    if (syncInProgress) return;
    syncInProgress = true;
    const client = config.client;

    try {
        if (Date.now() - lastCycleClear > 60000) {
            sentThisCycle.clear();
            lastCycleClear = Date.now();
        }

        let totalSent = 0;
    let chats = [];
    try {
        chats = await client.getChats();
    } catch (e) {
        logger.warn('getChats failed during sync', { error: e.message });
        return;
    }

    for (const chat of chats) {
        try {
            const n = await syncChatMessages(client, chat);
            totalSent += n;
        } catch (e) {
            logger.warn('syncChatMessages failed', { chatId: chat.id?._serialized, error: e.message });
        }
    }

    if (totalSent > 0) {
        logger.info('Sync outbound completed', { totalSent, chatsProcessed: chats.length });
    }
    } catch (e) {
        logger.warn('Sync outbound error', { error: e.message });
    } finally {
        syncInProgress = false;
    }
}

let intervalId = null;

function startSyncOutbound() {
    if (intervalId) return;
    logger.info('Starting sync outbound service', { intervalMs: SYNC_INTERVAL_MS });
    intervalId = setInterval(runSync, SYNC_INTERVAL_MS);
    runSync();
}

function stopSyncOutbound() {
    if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
        logger.info('Stopped sync outbound service');
    }
}

module.exports = {
    startSyncOutbound,
    stopSyncOutbound,
    runSync,
};
