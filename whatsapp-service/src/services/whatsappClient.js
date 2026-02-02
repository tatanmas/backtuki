// WhatsApp client initialization
const { Client, LocalAuth } = require('whatsapp-web.js');
const config = require('../config');
const { createLogger } = require('../utils/logger');

const logger = createLogger('WhatsAppClient');

/**
 * Initialize WhatsApp client
 */
function initClient() {
    logger.info('Creating WhatsApp client instance...');
    
    // Build puppeteer config based on environment
    const isProduction = process.env.NODE_ENV === 'production';
    const chromiumPath = process.env.PUPPETEER_EXECUTABLE_PATH;
    
    const puppeteerConfig = {
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--disable-extensions',
            '--disable-background-networking',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-breakpad',
            '--disable-component-extensions-with-background-pages',
            '--disable-component-update',
            '--disable-default-apps',
            '--disable-features=TranslateUI',
            '--disable-hang-monitor',
            '--disable-ipc-flooding-protection',
            '--disable-popup-blocking',
            '--disable-prompt-on-repost',
            '--disable-renderer-backgrounding',
            '--disable-sync',
            '--enable-features=NetworkService,NetworkServiceInProcess',
            '--force-color-profile=srgb',
            '--metrics-recording-only',
            '--no-default-browser-check',
            '--password-store=basic',
            '--use-mock-keychain'
        ]
    };
    
    // Only set executablePath in production (Docker) or if explicitly set
    if (chromiumPath) {
        puppeteerConfig.executablePath = chromiumPath;
        logger.info(`Using Chromium at: ${chromiumPath}`);
    } else if (isProduction) {
        puppeteerConfig.executablePath = '/usr/bin/chromium-browser';
        logger.info('Using Chromium at: /usr/bin/chromium-browser (production)');
    } else {
        logger.info('Using Puppeteer bundled Chromium (development)');
    }
    
    const client = new Client({
        authStrategy: new LocalAuth({
            dataPath: './sessions'
        }),
        puppeteer: puppeteerConfig,
        webVersionCache: {
            type: 'remote',
            remotePath: 'https://raw.githubusercontent.com/AironDev/whatsapp-web.js/main/src/util/Injected.js'
        }
    });
    
    // Set client in config
    config.setClient(client);
    
    // Add error handling for initialization
    client.on('loading_screen', (percent, message) => {
        logger.info(`Loading WhatsApp: ${percent}% - ${message}`);
    });
    
    client.on('authenticated', () => {
        logger.info('WhatsApp authenticated successfully');
    });
    
    client.on('auth_failure', (msg) => {
        logger.error('WhatsApp authentication failed', { message: msg });
    });
    
    // Initialize client with error handling
    logger.info('Starting WhatsApp client initialization...');
    client.initialize().catch(err => {
        logger.error('Failed to initialize WhatsApp client', { error: err.message, stack: err.stack });
    });
    
    return client;
}

module.exports = {
    initClient
};

