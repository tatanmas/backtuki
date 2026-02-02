// Ready handler
const config = require('../config');
const { createLogger } = require('../utils/logger');

const logger = createLogger('ReadyHandler');

/**
 * Handle WhatsApp client ready event
 */
async function handleReady(client) {
    const phoneNumber = client.info?.wid?.user || 'unknown';
    const name = client.info?.pushname || 'unknown';
    
    logger.info('WhatsApp connected successfully', { phoneNumber, name });
    config.setIsReady(true);
    config.setCurrentQR(null); // Clear QR once connected
    
    // Notify Django about connection
    try {
        const response = await fetch(`${config.DJANGO_API_URL}/api/v1/whatsapp/webhook/status/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                status: 'connected',
                phone_number: phoneNumber,
                name: name
            })
        });
        
        if (response.ok) {
            logger.info('Django notified about connection status');
        } else {
            logger.warn('Django status notification returned non-OK', { status: response.status });
        }
    } catch (err) {
        logger.error('Failed to notify Django about connection status', { error: err.message });
    }
}

module.exports = {
    handleReady
};

