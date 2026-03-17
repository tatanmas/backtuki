// Messages routes
const express = require('express');
const router = express.Router();
const config = require('../config');
const contactHelper = require('../utils/contactHelper');

/**
 * Normalize phone from body (trim, string). Return null if missing or empty.
 */
function normalizePhone(phone) {
    if (phone == null) return null;
    const s = String(phone).trim();
    return s.length > 0 ? s : null;
}

/**
 * Normalize phone to digits only for comparison (e.g. "56912345678" or "912345678" -> digits).
 */
function digitsOnly(phone) {
    if (phone == null) return '';
    return String(phone).replace(/\D/g, '');
}

/**
 * Return true if two digit strings represent the same number (allow leading country code or not).
 */
function phoneDigitsMatch(a, b) {
    if (!a || !b) return false;
    if (a === b) return true;
    if (a.length >= 9 && b.length >= 9) {
        const aTail = a.length >= 11 ? a.slice(-9) : a;
        const bTail = b.length >= 11 ? b.slice(-9) : b;
        if (aTail === bTail) return true;
        if (a.endsWith(bTail) || b.endsWith(aTail)) return true;
    }
    return false;
}

/**
 * Find an individual chat that matches the given phone (by contact number or chat id).
 * Used when getChatById(phone@c.us) throws "No LID for user" - the chat may exist with LID id.
 * @param {string} rawPhone - Phone in any format (e.g. "56912345678")
 * @returns {Promise<object|null>} Chat or null
 */
async function findChatByPhone(rawPhone) {
    const targetDigits = digitsOnly(rawPhone);
    if (!targetDigits || targetDigits.length < 8) return null;
    const chats = await config.client.getChats();
    for (const chat of chats) {
        if (chat.isGroup) continue;
        try {
            const idStr = chat.id && chat.id._serialized ? chat.id._serialized : '';
            const fromId = contactHelper.extractPhoneFromId(idStr);
            const contactDigits = fromId ? digitsOnly(fromId) : '';
            if (contactDigits && phoneDigitsMatch(contactDigits, targetDigits)) {
                return chat;
            }
            try {
                const contact = await chat.getContact();
                const num = contactHelper.getContactNumber(contact) || (contact.number || '');
                const numDigits = digitsOnly(num);
                if (numDigits && phoneDigitsMatch(numDigits, targetDigits)) {
                    return chat;
                }
            } catch (_) {
                // getContact can fail for @lid; we already tried id above
            }
        } catch (_) {
            // skip this chat
        }
    }
    return null;
}

/**
 * Map known WhatsApp/library errors to 400 with a clear message.
 */
function isClientError(message) {
    if (!message || typeof message !== 'string') return false;
    const m = message.toLowerCase();
    return (
        m.includes('number not registered') ||
        m.includes('invalid wid') ||
        m.includes('not registered on whatsapp') ||
        m.includes('cannot find') ||
        m.includes('no lid for user') ||
        m.includes('chat not found')
    );
}

/**
 * POST /api/send-message
 * Send a message to a WhatsApp chat.
 * Uses getChatById + chat.sendMessage for all targets to avoid 500 with @c.us when WhatsApp uses LID.
 * On "No LID for user", falls back to finding the chat by phone in getChats() and sending via that chat.
 */
router.post('/api/send-message', async (req, res) => {
    if (!config.isReady) return res.status(503).json({ error: 'WhatsApp no listo' });
    
    const { phone, text, message, groupId, chatId } = req.body;
    const messageText = (text != null && text !== '') ? String(text) : (message != null && message !== '') ? String(message) : null;
    
    if (!messageText) {
        return res.status(400).json({ error: 'Message text required (use "text" or "message" field)' });
    }
    
    let rawPhoneForFallback = null;
    try {
        let targetId;
        
        if (groupId) {
            targetId = String(groupId).trim() || null;
        } else if (chatId) {
            targetId = String(chatId).trim() || null;
        } else {
            const rawPhone = normalizePhone(phone);
            if (!rawPhone) {
                return res.status(400).json({ error: 'phone, chatId, or groupId required' });
            }
            rawPhoneForFallback = rawPhone;
            if (rawPhone.includes('@')) {
                targetId = rawPhone;
            } else {
                // Resolve to correct ID (may be LID); fallback to @c.us
                try {
                    const numberId = await config.client.getNumberId(rawPhone);
                    targetId = (numberId && numberId._serialized) ? numberId._serialized : `${rawPhone}@c.us`;
                } catch (_) {
                    targetId = `${rawPhone}@c.us`;
                }
            }
        }

        if (!targetId) {
            return res.status(400).json({ error: 'phone, chatId, or groupId required' });
        }

        // Use getChatById + chat.sendMessage for all targets so DMs work with both @c.us and LID.
        const chat = await config.client.getChatById(targetId);
        await chat.sendMessage(messageText);
        res.json({ success: true, targetId: chat.id._serialized || targetId });
    } catch (error) {
        const msg = error && error.message ? String(error.message) : 'Error sending message';
        const isNoLid = msg.toLowerCase().includes('no lid for user');
        if (isNoLid && rawPhoneForFallback) {
            try {
                const chat = await findChatByPhone(rawPhoneForFallback);
                if (chat) {
                    await chat.sendMessage(messageText);
                    const targetId = chat.id && chat.id._serialized ? chat.id._serialized : rawPhoneForFallback;
                    return res.json({ success: true, targetId });
                }
            } catch (fallbackErr) {
                console.error('Fallback findChatByPhone failed:', fallbackErr);
            }
        }
        console.error('Error sending message:', error);
        if (isClientError(msg)) {
            return res.status(400).json({ error: msg });
        }
        res.status(500).json({ error: msg });
    }
});

/**
 * POST /api/send-media
 * Send image/document to a WhatsApp chat
 */
router.post('/api/send-media', async (req, res) => {
    if (!config.isReady) return res.status(503).json({ error: 'WhatsApp no listo' });

    const { phone, groupId, chatId, mediaBase64, mediaUrl, mimetype, filename, caption } = req.body;

    if (!mediaBase64 && !mediaUrl) {
        return res.status(400).json({ error: 'mediaBase64 or mediaUrl required' });
    }

    try {
        const { MessageMedia } = require('whatsapp-web.js');
        let media;

        if (mediaBase64) {
            media = new MessageMedia(
                mimetype || 'image/png',
                mediaBase64,
                filename || 'ticket.png'
            );
        } else {
            media = await MessageMedia.fromUrl(mediaUrl, { unsafeMime: true });
        }

        let targetId;
        if (groupId) {
            targetId = groupId;
        } else if (chatId) {
            targetId = chatId;
        } else if (phone) {
            targetId = phone.includes('@') ? phone : `${phone}@c.us`;
        } else {
            return res.status(400).json({ error: 'phone, chatId, or groupId required' });
        }

        if (targetId && targetId.includes('@lid')) {
            const chat = await config.client.getChatById(targetId);
            await chat.sendMessage(media, { caption: caption || '' });
        } else {
            await config.client.sendMessage(targetId, media, { caption: caption || '' });
        }
        res.json({ success: true, targetId });
    } catch (error) {
        console.error('Error sending media:', error);
        res.status(500).json({ error: error.message });
    }
});

module.exports = router;

