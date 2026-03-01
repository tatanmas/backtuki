/**
 * POST /api/check-saved-contacts
 * Check which participant IDs are saved contacts (in phone address book).
 * Body: { "ids": ["569xxx@c.us", "123@lid", ...] }
 * Response: { "569xxx@c.us": true, "123@lid": false, ... }
 * @lid IDs are never considered saved (getContactById fails); we return false for them.
 */
const express = require('express');
const router = express.Router();
const config = require('../config');
const contactHelper = require('../utils/contactHelper');

router.post('/api/check-saved-contacts', async (req, res) => {
    if (!config.isReady) {
        return res.status(503).json({ error: 'WhatsApp no listo' });
    }

    const { ids } = req.body;
    if (!Array.isArray(ids) || ids.length === 0) {
        return res.status(400).json({ error: 'Body must include "ids" array' });
    }

    const result = {};
    const client = config.client;

    for (const idStr of ids) {
        const normalized = contactHelper.normalizeContactId(idStr);
        if (!normalized || normalized.includes('@lid') || normalized.includes('[object Object]')) {
            result[idStr] = false;
            continue;
        }
        try {
            const contact = await client.getContactById(normalized);
            result[idStr] = !!(contact && contact.isMyContact);
        } catch (_) {
            result[idStr] = false;
        }
    }

    res.json(result);
});

module.exports = router;
