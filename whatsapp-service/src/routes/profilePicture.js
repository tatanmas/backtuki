/**
 * Profile picture proxy route
 * Fetches WhatsApp profile pictures server-side to avoid CORS and URL expiration issues.
 * Returns image as binary stream - frontend uses this via Django proxy.
 */
const express = require('express');
const router = express.Router();
const config = require('../config');
const chatHelper = require('../utils/chatHelper');
const { createLogger } = require('../utils/logger');

const logger = createLogger('ProfilePicture');

/**
 * GET /api/profile-picture/:chatId
 * Proxy for WhatsApp profile pictures. Fetches image server-side, returns as image/jpeg.
 * chatId must be URL-encoded (e.g. 56912345678%40c.us for 56912345678@c.us)
 */
router.get('/api/profile-picture/:chatId', async (req, res) => {
    if (!config.isReady) {
        return res.status(503).json({ error: 'WhatsApp no listo' });
    }
    const chatId = decodeURIComponent(req.params.chatId);
    if (!chatId) {
        return res.status(400).json({ error: 'chatId requerido' });
    }
    try {
        const chat = await config.client.getChatById(chatId);
        if (!chat) {
            return res.status(404).json({ error: 'Chat no encontrado' });
        }
        const contactOrChat = chat.isGroup ? chat : await chat.getContact();
        const profilePicUrl = await chatHelper.getProfilePicture(contactOrChat);
        if (!profilePicUrl) {
            return res.status(404).json({ error: 'Sin foto de perfil' });
        }
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10000);
        const imgRes = await fetch(profilePicUrl, { signal: controller.signal });
        clearTimeout(timeout);
        if (!imgRes.ok) {
            logger.warn(`Profile picture fetch failed for ${chatId}`, { status: imgRes.status });
            return res.status(502).json({ error: 'No se pudo obtener la foto' });
        }
        const contentType = imgRes.headers.get('content-type') || 'image/jpeg';
        const buffer = Buffer.from(await imgRes.arrayBuffer());
        res.set('Content-Type', contentType);
        res.set('Cache-Control', 'private, max-age=300'); // 5 min cache
        res.send(buffer);
    } catch (error) {
        logger.error(`Error fetching profile picture for ${chatId}`, { error: error.message });
        res.status(500).json({ error: 'Error al obtener foto de perfil' });
    }
});

module.exports = router;
