/**
 * Structured logging utility for WhatsApp Service
 * 
 * Provides consistent logging format with levels and context
 */

const LOG_LEVELS = {
    ERROR: 'ERROR',
    WARN: 'WARN',
    INFO: 'INFO',
    DEBUG: 'DEBUG'
};

/**
 * Format log message with timestamp and context
 */
function formatLog(level, module, message, data = null) {
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${level}] [${module}]`;
    
    if (data) {
        return `${prefix} ${message} ${JSON.stringify(data)}`;
    }
    return `${prefix} ${message}`;
}

/**
 * Logger class for structured logging
 */
class Logger {
    constructor(module) {
        this.module = module;
    }

    error(message, data = null) {
        console.error(formatLog(LOG_LEVELS.ERROR, this.module, message, data));
    }

    warn(message, data = null) {
        console.warn(formatLog(LOG_LEVELS.WARN, this.module, message, data));
    }

    info(message, data = null) {
        console.log(formatLog(LOG_LEVELS.INFO, this.module, message, data));
    }

    debug(message, data = null) {
        if (process.env.NODE_ENV !== 'production') {
            console.log(formatLog(LOG_LEVELS.DEBUG, this.module, message, data));
        }
    }
}

/**
 * Create a logger instance for a specific module
 */
function createLogger(module) {
    return new Logger(module);
}

module.exports = {
    createLogger,
    LOG_LEVELS
};
