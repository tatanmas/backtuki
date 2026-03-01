// Status routes
const express = require('express');
const router = express.Router();
const QRCode = require('qrcode');
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
 * Get current QR code. Returns 200 with qr: null when no QR (e.g. after disconnect, waiting for client to emit).
 */
router.get('/api/qr', (req, res) => {
    if (config.currentQR) {
        res.json({ qr: config.currentQR });
    } else {
        // 200 + qr: null so backends don't treat as "endpoint not found"; frontend can keep polling
        res.status(200).json({ qr: null, message: 'No QR yet (waiting for client to generate)' });
    }
});

/**
 * GET /api/qr-page
 * Display QR code as HTML page for easy scanning
 */
router.get('/api/qr-page', async (req, res) => {
    if (!config.currentQR) {
        if (config.isReady) {
            res.send(`
                <!DOCTYPE html>
                <html>
                <head><title>WhatsApp Connected</title></head>
                <body style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;background:#25D366;">
                    <div style="text-align:center;color:white;">
                        <h1>✓ WhatsApp Connected</h1>
                        <p>Session is active</p>
                    </div>
                </body>
                </html>
            `);
        } else {
            res.send(`
                <!DOCTYPE html>
                <html>
                <head><title>Waiting for QR</title><meta http-equiv="refresh" content="3"></head>
                <body style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;">
                    <div style="text-align:center;">
                        <h1>Waiting for QR Code...</h1>
                        <p>Page will refresh automatically</p>
                    </div>
                </body>
                </html>
            `);
        }
        return;
    }
    
    try {
        const qrDataUrl = await QRCode.toDataURL(config.currentQR, { width: 400, margin: 2 });
        res.send(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>WhatsApp QR Code</title>
                <meta http-equiv="refresh" content="20">
            </head>
            <body style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;background:#f0f0f0;">
                <div style="text-align:center;background:white;padding:40px;border-radius:20px;box-shadow:0 4px 20px rgba(0,0,0,0.1);">
                    <h1 style="color:#25D366;">Scan QR Code with WhatsApp</h1>
                    <img src="${qrDataUrl}" alt="WhatsApp QR Code" style="margin:20px 0;"/>
                    <p style="color:#666;">QR code refreshes every 20 seconds</p>
                </div>
            </body>
            </html>
        `);
    } catch (error) {
        res.status(500).send(`Error generating QR: ${error.message}`);
    }
});

/**
 * POST /api/request-new-qr
 * Ask for a new QR. If the browser is already running (client already initialized), we cannot
 * call initialize() again (Puppeteer would try to launch a second browser with same userDataDir).
 * In that case we return success and rely on the library's automatic QR refresh (~20s).
 */
function isProfileLockedError(error) {
    const msg = error && error.message ? String(error.message) : '';
    const full = (error && error.toString && error.toString()) || msg;
    return (
        msg.includes('profile') && (msg.includes('in use') || msg.includes('locked')) ||
        msg.includes('Singleton') ||
        msg.includes('Code: 21') ||
        full.includes('another Chromium process')
    );
}

router.post('/api/request-new-qr', async (req, res) => {
    console.log('[API /api/request-new-qr] Requesting new QR...');
    try {
        if (!config.client) {
            return res.status(400).json({ success: false, error: 'No client instance' });
        }
        // Do NOT clear currentQR here: if initialize() throws "already running", we'd leave the user with no QR.
        await config.client.initialize();
        config.setCurrentQR(null); // clear so UI shows loading until next qr event
        return res.json({ success: true, message: 'Client re-initializing; new QR will be available shortly via GET /api/qr' });
    } catch (error) {
        const msg = error && error.message ? String(error.message) : '';
        if (msg.includes('already running') || msg.includes('userDataDir')) {
            console.log('[API /api/request-new-qr] Browser already running; QR refreshes automatically.');
            // Keep current QR so GET /api/qr still returns it; user is not stuck with "no hay QR disponible"
            return res.status(200).json({
                success: true,
                message: 'El código QR se renueva solo cada ~20 s. Sigue visible abajo. Para vincular otra cuenta, usa «Reiniciar sesión».'
            });
        }
        if (isProfileLockedError(error)) {
            const userMessage = 'El perfil de Chromium está bloqueado (otro proceso o reinicio previo). Reinicia el contenedor del servicio WhatsApp: docker compose restart whatsapp-service';
            console.warn('[API /api/request-new-qr] Profile locked:', error.message);
            return res.status(503).json({
                success: false,
                error: 'profile_locked',
                message: userMessage
            });
        }
        console.error('[API /api/request-new-qr] Error:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

/**
 * POST /api/disconnect
 * Disconnect WhatsApp session and re-initialize to show new QR for linking another account
 */
router.post('/api/disconnect', async (req, res) => {
    console.log('[API /api/disconnect] Disconnecting WhatsApp session...');
    try {
        if (config.client) {
            await config.client.logout();
            config.setIsReady(false);
            config.setCurrentQR(null);
            console.log('[API /api/disconnect] Logged out, re-initializing client to generate new QR...');
            // Re-initialize so a new QR is emitted (allows linking a different account)
            await config.client.initialize();
            res.json({ success: true, message: 'WhatsApp session disconnected. New QR will appear shortly.' });
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

