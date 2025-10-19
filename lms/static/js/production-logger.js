/**
 * Production-Safe Logger
 * Provides controlled logging that can be disabled in production
 */

(function() {
    'use strict';
    
    // Check if we're in production
    const isProduction = window.location.hostname !== 'localhost' && 
                        !window.location.hostname.includes('dev') && 
                        !window.location.hostname.includes('test');
    
    // Logging levels
    const LOG_LEVELS = {
        ERROR: 0,
        WARN: 1,
        INFO: 2,
        DEBUG: 3
    };
    
    // Current log level (can be overridden via localStorage)
    let currentLogLevel = isProduction ? LOG_LEVELS.ERROR : LOG_LEVELS.DEBUG;
    
    // Try to get log level from localStorage
    try {
        const storedLevel = localStorage.getItem('lms_log_level');
        if (storedLevel !== null) {
            currentLogLevel = parseInt(storedLevel, 10);
        }
    } catch (e) {
        // Ignore localStorage errors
    }
    
    /**
     * Production-safe logger
     */
    const ProductionLogger = {
        error: function(...args) {
            if (currentLogLevel >= LOG_LEVELS.ERROR) {
                console.error(...args);
            }
        },
        
        warn: function(...args) {
            if (currentLogLevel >= LOG_LEVELS.WARN) {
                console.warn(...args);
            }
        },
        
        info: function(...args) {
            if (currentLogLevel >= LOG_LEVELS.INFO) {
                console.info(...args);
            }
        },
        
        debug: function(...args) {
            if (currentLogLevel >= LOG_LEVELS.DEBUG) {
                console.log(...args);
            }
        },
        
        log: function(...args) {
            if (currentLogLevel >= LOG_LEVELS.INFO) {
                console.log(...args);
            }
        },
        
        // Set log level
        setLevel: function(level) {
            currentLogLevel = level;
            try {
                localStorage.setItem('lms_log_level', level.toString());
            } catch (e) {
                // Ignore localStorage errors
            }
        },
        
        // Get current log level
        getLevel: function() {
            return currentLogLevel;
        },
        
        // Check if a level is enabled
        isEnabled: function(level) {
            return currentLogLevel >= level;
        },
        
        // Production check
        isProduction: isProduction
    };
    
    // Expose globally
    window.ProductionLogger = ProductionLogger;
    
    // Override console methods in production
    if (isProduction) {
        // Keep error and warn for critical issues
        // Override info, log, and debug
        const originalConsole = {
            log: console.log,
            info: console.info,
            debug: console.debug
        };
        
        console.log = function(...args) {
            if (ProductionLogger.isEnabled(LOG_LEVELS.INFO)) {
                originalConsole.log(...args);
            }
        };
        
        console.info = function(...args) {
            if (ProductionLogger.isEnabled(LOG_LEVELS.INFO)) {
                originalConsole.info(...args);
            }
        };
        
        console.debug = function(...args) {
            if (ProductionLogger.isEnabled(LOG_LEVELS.DEBUG)) {
                originalConsole.debug(...args);
            }
        };
    }
    
    // Initialize
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            if (!isProduction) {
                ProductionLogger.debug('✅ Production Logger initialized (development mode)');
            }
        });
    } else {
        if (!isProduction) {
            ProductionLogger.debug('✅ Production Logger initialized (development mode)');
        }
    }
    
})();
