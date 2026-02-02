// Status routes
const express = require('express');
const router = express.Router();
const config = require('../config');

/**
 * GET /api/status
 * Get WhatsApp connection status
 */
router.get('/api/status', (req, res) => {
    res.json({ 
        isReady: config.isReady, 
        number: config.client?.info?.pushname,
        phone_number: config.client?.info?.wid?.user || null,
        hasQR: config.currentQR !== null
    });
});

/**
 * GET /api/qr
 * Get current QR code
 */
router.get('/api/qr', (req, res) => {
    if (config.currentQR) {
        res.json({ qr: config.currentQR });
    } else {
        res.status(404).json({ qr: null, error: 'No QR code available' });
    }
});

/**
 * POST /api/disconnect
 * Disconnect WhatsApp session
 */
router.post('/api/disconnect', async (req, res) => {
    console.log('[API /api/disconnect] Disconnecting WhatsApp session...');
    try {
        if (config.client) {
            await config.client.logout();
            config.setIsReady(false);
            config.setCurrentQR(null);
            console.log('[API /api/disconnect] Successfully disconnected');
            res.json({ success: true, message: 'WhatsApp session disconnected' });
        } else {
            res.status(400).json({ success: false, error: 'No active client' });
        }
    } catch (error) {
        console.error('[API /api/disconnect] Error:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

/**
 * GET /health
 * Health check endpoint for Docker/monitoring
 */
router.get('/health', (req, res) => {
    const health = {
        status: 'ok',
        timestamp: new Date().toISOString(),
        service: 'tuki-whatsapp-service',
        whatsapp: {
            isReady: config.isReady,
            hasClient: !!config.client,
            hasQR: config.currentQR !== null
        }
    };
    
    // Return 200 even if WhatsApp is not connected (service is healthy)
    res.json(health);
});

/**
 * GET /api/health
 * Alternative health check endpoint
 */
router.get('/api/health', (req, res) => {
    const health = {
        status: 'ok',
        timestamp: new Date().toISOString(),
        service: 'tuki-whatsapp-service',
        whatsapp: {
            isReady: config.isReady,
            hasClient: !!config.client,
            hasQR: config.currentQR !== null
        }
    };
    
    res.json(health);
});

module.exports = router;

