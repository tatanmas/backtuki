// Main server file - refactored to use modular structure
const express = require('express');
const config = require('./config');
const { createLogger } = require('./utils/logger');
const { initClient } = require('./services/whatsappClient');
const { handleQR } = require('./handlers/qrHandler');
const { handleReady } = require('./handlers/readyHandler');
const { handleMessage } = require('./handlers/messageHandler');

// Import routes
const messagesRoutes = require('./routes/messages');
const statusRoutes = require('./routes/status');
const chatsRoutes = require('./routes/chats');
const groupsRoutes = require('./routes/groups');

const logger = createLogger('Server');

// Express app setup
const app = express();
app.use(express.json());

// Request logging middleware
app.use((req, res, next) => {
    const start = Date.now();
    res.on('finish', () => {
        const duration = Date.now() - start;
        if (req.path !== '/health' && req.path !== '/api/health') {
            logger.info(`${req.method} ${req.path} ${res.statusCode} ${duration}ms`);
        }
    });
    next();
});

// Initialize WhatsApp client
logger.info('Initializing WhatsApp client...');
const client = initClient();

// Register event handlers
client.on('qr', handleQR);
client.on('ready', () => handleReady(client));
client.on('message', (message) => handleMessage(message, client));

// Handle WhatsApp client errors
client.on('auth_failure', (msg) => {
    logger.error('Authentication failure', { message: msg });
});

client.on('disconnected', (reason) => {
    logger.warn('WhatsApp disconnected', { reason });
    config.setIsReady(false);
    config.setCurrentQR(null);
});

// Register routes
app.use('/', messagesRoutes);
app.use('/', statusRoutes);
app.use('/', chatsRoutes);
app.use('/', groupsRoutes);

// Error handling middleware
app.use((err, req, res, next) => {
    logger.error('Unhandled error', { 
        error: err.message, 
        stack: err.stack,
        path: req.path 
    });
    res.status(500).json({ error: 'Internal server error' });
});

// Graceful shutdown
process.on('SIGTERM', async () => {
    logger.info('SIGTERM received, shutting down gracefully...');
    if (config.client) {
        try {
            await config.client.destroy();
            logger.info('WhatsApp client destroyed');
        } catch (e) {
            logger.error('Error destroying client', { error: e.message });
        }
    }
    process.exit(0);
});

process.on('SIGINT', async () => {
    logger.info('SIGINT received, shutting down gracefully...');
    if (config.client) {
        try {
            await config.client.destroy();
            logger.info('WhatsApp client destroyed');
        } catch (e) {
            logger.error('Error destroying client', { error: e.message });
        }
    }
    process.exit(0);
});

// Start server
app.listen(config.PORT, () => {
    logger.info(`WhatsApp Service started`, {
        port: config.PORT,
        djangoUrl: config.DJANGO_API_URL,
        nodeEnv: process.env.NODE_ENV || 'development'
    });
});
