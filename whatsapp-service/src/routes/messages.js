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
    
    const { phone, text, groupId } = req.body;
    
    try {
        if (groupId) {
            // Enviar a grupo
            await config.client.sendMessage(groupId, text);
        } else {
            // Enviar a chat individual
            await config.client.sendMessage(`${phone}@c.us`, text);
        }
        res.json({ success: true });
    } catch (error) {
        console.error('Error sending message:', error);
        res.status(500).json({ error: error.message });
    }
});

module.exports = router;

