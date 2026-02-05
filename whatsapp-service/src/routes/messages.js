// Messages routes
const express = require('express');
const router = express.Router();
const config = require('../config');

/**
 * POST /api/send-message
 * Send a message to a WhatsApp chat
 */
router.post('/api/send-message', async (req, res) => {
    if (!config.isReady) return res.status(503).json({ error: 'WhatsApp no listo' });
    
    const { phone, text, message, groupId, chatId } = req.body;
    const messageText = text || message; // Support both 'text' and 'message' fields
    
    if (!messageText) {
        return res.status(400).json({ error: 'Message text required (use "text" or "message" field)' });
    }
    
    try {
        let targetId;
        
        if (groupId) {
            targetId = groupId;
        } else if (chatId) {
            targetId = chatId;
        } else if (phone) {
            if (phone.includes('@')) {
                targetId = phone;
            } else {
                targetId = `${phone}@c.us`;
            }
        } else {
            return res.status(400).json({ error: 'phone, chatId, or groupId required' });
        }

        // @lid: client.sendMessage falla con "No LID for user". Usar getChatById + chat.sendMessage.
        if (targetId && targetId.includes('@lid')) {
            const chat = await config.client.getChatById(targetId);
            await chat.sendMessage(messageText);
        } else {
            await config.client.sendMessage(targetId, messageText);
        }
        res.json({ success: true, targetId });
    } catch (error) {
        console.error('Error sending message:', error);
        res.status(500).json({ error: error.message });
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

