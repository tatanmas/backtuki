// Message handler
const config = require('../config');
const contactHelper = require('../utils/contactHelper');
const chatHelper = require('../utils/chatHelper');
const { createLogger } = require('../utils/logger');

const logger = createLogger('MessageHandler');

/**
 * Handle incoming WhatsApp messages
 */
async function handleMessage(message, client) {
    const msgId = message.id?._serialized || message.id?.id || String(message.id);
    logger.info(`[handleMessage] INVOKED msgId=${msgId} fromMe=${message.fromMe} type=${message.type}`);

    try {
    // IMPORTANTE: Capturar TODOS los mensajes, incluyendo los propios (fromMe)
    // Esto permite tener el flujo completo del chat
    
    const isFromMe = message.fromMe;
    
    // Para mensajes propios, usar message.to; para entrantes, usar message.from
    const chatId = isFromMe ? message.to : message.from;
    const isGroup = chatId.endsWith('@g.us');
    const chatType = isGroup ? 'group' : 'individual';
    
    // Obtener información del chat
    let chatName = null;
    let whatsappName = null;
    let profilePictureUrl = null;
    let senderName = null;
    let senderPhone = null;
    let phoneNumber = null;
    
    try {
        const chat = await message.getChat();
        
        if (isGroup) {
            // Para grupos, obtener nombre del grupo
            chatName = chatHelper.getChatDisplayName(chat);
            
            // Para mensajes de grupo, obtener información del remitente (si no es propio)
            if (isGroup && !isFromMe && message.author) {
                logger.debug('Group message received, extracting sender info', { author: message.author });
                const authorStr = contactHelper.normalizeContactId ? contactHelper.normalizeContactId(message.author) : (typeof message.author === 'string' ? message.author : (message.author?._serialized || ''));
                if (contactHelper.isLidContact(authorStr) || (authorStr && authorStr.includes('@lid'))) {
                    const basic = contactHelper.getBasicContactInfoFromId(authorStr);
                    senderName = basic.formattedNumber || null;
                    senderPhone = basic.number || null;
                } else {
                    try {
                        const senderContactInfo = await contactHelper.getContactInfo(client, message.author);
                        senderName = senderContactInfo.pushname || senderContactInfo.name || null;
                        senderPhone = senderContactInfo.number || null;
                        logger.debug('Sender info extracted', { senderName, senderPhone });
                    } catch (e) {
                        logger.warn('Failed to get sender info, using fallback', { author: message.author, error: e.message });
                        senderPhone = authorStr ? authorStr.replace(/@\w+\.?\w*/g, '') : '';
                    }
                }
            } else if (isGroup && isFromMe) {
                logger.debug('Own message in group, skipping sender extraction');
            } else if (isGroup && !message.author) {
                logger.warn('Group message without author field', {
                    chatId: chatId,
                    messageId: message.id._serialized,
                    fromMe: isFromMe
                });
            }
            
            // Obtener foto de perfil del grupo
            profilePictureUrl = await chatHelper.getProfilePicture(chat);
            
            // Para grupos, phoneNumber es el ID del grupo (no hay número individual)
            phoneNumber = chatId.replace('@g.us', '');
        } else {
            // Para chats individuales
            let contact = null;
            
            if (isFromMe) {
                // Para mensajes propios, obtener el contacto del destinatario
                try {
                    contact = await chat.getContact();
                } catch (e) {
                    logger.warn('Failed to get contact for own message', { error: e.message });
                }
            } else {
                // Para mensajes entrantes, obtener el contacto del remitente
                try {
                    contact = await message.getContact();
                } catch (e) {
                    logger.warn('Failed to get contact for incoming message', { error: e.message });
                }
            }
            
            // Obtener nombre y número usando helpers
            if (contact) {
                chatName = chatHelper.getChatDisplayName(chat, contact);
                whatsappName = chatHelper.getWhatsAppName(contact);
                phoneNumber = contactHelper.getContactNumber(contact);
                profilePictureUrl = await chatHelper.getProfilePicture(contact);
            } else {
                // Fallback: extraer del chat ID
                phoneNumber = contactHelper.extractPhoneFromId(chatId);
                chatName = phoneNumber ? contactHelper.formatPhoneNumber(phoneNumber) : chatId.replace('@c.us', '');
            }
        }
    } catch (e) {
        logger.error('Failed to get chat info', { chatId, error: e.message });
        // Fallback: extraer número del chat ID
        if (!isGroup) {
            phoneNumber = contactHelper.extractPhoneFromId(chatId);
            chatName = phoneNumber ? contactHelper.formatPhoneNumber(phoneNumber) : chatId.replace('@c.us', '').replace('@g.us', '');
        } else {
            chatName = chatId.replace('@g.us', '');
        }
    }
    
    // Asegurar que phoneNumber esté formateado correctamente (para no grupos)
    if (phoneNumber && !isGroup) {
        // phoneNumber ya debería estar en formato correcto si viene de contactHelper
        // pero por seguridad, si es solo dígitos, lo formateamos
        if (/^\d+$/.test(phoneNumber)) {
            phoneNumber = contactHelper.formatPhoneNumber(phoneNumber);
        }
    }
    
    // Obtener texto: message.body puede venir vacío (bug conocido, media usa caption)
    let text = message.body || '';
    if (!text && message.type === 'chat') {
        const raw = message.rawData || message._data || {};
        text = raw.body || raw.conversation
            || (raw.extendedTextMessage && raw.extendedTextMessage.text)
            || (Array.isArray(raw) ? raw[0] : '') || '';
    }
    if (!text && typeof message.reload === 'function') {
        try {
            const reloaded = await message.reload();
            if (reloaded && reloaded.body) text = reloaded.body;
        } catch (e) {
            logger.debug('Message reload failed', { error: e.message });
        }
    }

    // Enterprise: media_type, reply_to, placeholder para audios/archivos
    const mediaType = message.type || 'chat';
    const MEDIA_PLACEHOLDERS = {
        ptt: '[Audio de voz]',
        audio: '[Audio]',
        image: '[Imagen]',
        video: '[Video]',
        document: '[Documento]',
        sticker: '[Sticker]',
        location: '[Ubicación]'
    };
    if (!text && MEDIA_PLACEHOLDERS[mediaType]) {
        text = MEDIA_PLACEHOLDERS[mediaType];
    } else if (!text && mediaType !== 'chat') {
        text = `[${mediaType}]`;
    }

    let replyToWhatsappId = null;
    try {
        if (message.hasQuotedMsg && typeof message.getQuotedMessage === 'function') {
            const quoted = await message.getQuotedMessage();
            if (quoted && quoted.id) {
                replyToWhatsappId = quoted.id._serialized || quoted.id.id || null;
            }
        }
    } catch (e) {
        logger.debug('getQuotedMessage failed', { error: e.message });
    }

    // Enviar a Django webhook
    try {
        const timestamp = message.timestamp;
        
        const payload = {
            id: message.id._serialized || message.id.id || String(message.id),
            phone: phoneNumber || chatId.replace('@c.us', '').replace('@g.us', ''),
            chat_id: chatId,
            chat_type: chatType,
            chat_name: chatName,
            whatsapp_name: whatsappName,
            profile_picture_url: profilePictureUrl,
            text: text || '',
            timestamp: timestamp,
            from_me: isFromMe,
            sender_name: senderName || null,
            sender_phone: senderPhone || null,
            media_type: mediaType,
            reply_to_whatsapp_id: replyToWhatsappId
        };
        
        logger.info('Message received', {
            type: isFromMe ? 'outgoing' : 'incoming',
            chatType: chatType,
            chatName: chatName,
            mediaType: mediaType,
            textPreview: text ? text.substring(0, 80) : '(empty)'
        });
        
        const djangoUrl = `${config.DJANGO_API_URL}/api/v1/whatsapp/webhook/process-message/`;
        logger.info(`[handleMessage] POSTing to Django: ${djangoUrl} text_len=${(text || '').length}`);
        const response = await fetch(djangoUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            const result = await response.json().catch(() => ({}));
            logger.info(`[handleMessage] Django OK status=${result.status || 'unknown'}`);
        } else {
            const errBody = await response.text();
            logger.warn(`[handleMessage] Django FAILED status=${response.status} body=${errBody?.substring(0, 200)}`);
        }
    } catch (error) {
        logger.error(`[handleMessage] FAILED to send to Django: ${error.message}`, { error: error.stack });
    }
    } catch (outerError) {
        logger.error(`[handleMessage] UNHANDLED ERROR: ${outerError.message}`, { error: outerError.stack });
    }
}

module.exports = {
    handleMessage
};
