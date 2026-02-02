// QR code handler
const qrcode = require('qrcode-terminal');
const config = require('../config');
const { createLogger } = require('../utils/logger');

const logger = createLogger('QRHandler');

/**
 * Handle QR code generation
 */
async function handleQR(qr) {
    logger.info('QR code generated, scan with WhatsApp to connect');
    qrcode.generate(qr, { small: true });
    config.setCurrentQR(qr);
    
    // Notify Django about QR code
    try {
        const response = await fetch(`${config.DJANGO_API_URL}/api/v1/whatsapp/webhook/qr/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ qr })
        });
        
        if (response.ok) {
            logger.info('Django notified about QR code');
        } else {
            logger.warn('Django QR notification returned non-OK status', { status: response.status });
        }
    } catch (err) {
        logger.error('Failed to notify Django about QR code', { error: err.message });
    }
}

module.exports = {
    handleQR
};

