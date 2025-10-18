// Enhanced Error Handler for LMS - Fixed Version
// Handles JavaScript errors with improved browser compatibility and error suppression

(function() {
    'use strict';

    // Global error handler object
    window.LMSErrorHandler = window.LMSErrorHandler || {
        errors: [],
        maxErrors: 50,
        cleanupInterval: null,
        
        logError: function(message, error) {
            var errorObj = {
                message: message,
                error: error,
                timestamp: new Date().toISOString(),
                url: window.location.href,
                userAgent: navigator.userAgent
            };
            
            this.errors.push(errorObj);
            
            // Limit stored errors with circular buffer
            if (this.errors.length > this.maxErrors) {
                this.errors.shift();
            }
            
            // Auto-cleanup old errors (older than 1 hour)
            this.cleanupOldErrors();
            
            // Log to console in development
            if (window.location.hostname === 'localhost' || window.location.hostname.includes('dev')) {
                console.error('[LMS Error]', message, error);
            }
            
            // Send to server if available
            this.sendToServer(errorObj);
        },
        
        sendToServer: function(errorObj) {
            // Only send to server in production
            if (window.location.hostname === 'localhost' || window.location.hostname.includes('dev')) {
                return;
            }
            
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/api/log-error/', true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                
                // Get CSRF token
                var csrfToken = this.getCSRFToken();
                if (csrfToken) {
                    xhr.setRequestHeader('X-CSRFToken', csrfToken);
                }
                
                xhr.send(JSON.stringify(errorObj));
            } catch (e) {
                // Silently fail if we can't send to server
            }
        },
        
        getCSRFToken: function() {
            var csrfMeta = document.querySelector('meta[name="csrf-token"]');
            if (csrfMeta) {
                return csrfMeta.getAttribute('content');
            }
            
            var csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
            if (csrfInput) {
                return csrfInput.value;
            }
            
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                var parts = cookie.split('=');
                if (parts[0] === 'csrftoken') {
                    return parts[1];
                }
            }
            
            return '';
        },
        
        cleanupOldErrors: function() {
            var oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
            this.errors = this.errors.filter(function(error) {
                return error.timestamp > oneHourAgo;
            });
        },
        
        startAutoCleanup: function() {
            var self = this;
            if (this.cleanupInterval) {
                clearInterval(this.cleanupInterval);
            }
            // Cleanup every 30 minutes
            this.cleanupInterval = setInterval(function() {
                self.cleanupOldErrors();
            }, 30 * 60 * 1000);
        },
        
        stopAutoCleanup: function() {
            if (this.cleanupInterval) {
                clearInterval(this.cleanupInterval);
                this.cleanupInterval = null;
            }
        },
        
        getErrors: function() {
            return this.errors;
        },
        
        clearErrors: function() {
            this.errors = [];
        }
    };

    // Global error event handler
    window.addEventListener('error', function(event) {
        try {
            var message = event.message || 'Unknown error';
            var filename = event.filename || '';
            var lineno = event.lineno || 0;
            var colno = event.colno || 0;
            var error = event.error;
            
            // Check if this is a syntax error
            var isSyntaxError = message.includes('SyntaxError') || message.includes('Unexpected token');
            
            // Format error message
            var errorMessage = 'JavaScript Error: ' + message;
            if (filename) {
                errorMessage += ' at ' + filename;
            }
            if (lineno) {
                errorMessage += ' line ' + lineno;
            }
            if (colno) {
                errorMessage += ' column ' + colno;
            }
            
            // Log error details
            console.error(errorMessage);
            console.error('Error details:', error);
            
            // Handle syntax errors specifically
            if (isSyntaxError) {
                console.error('Syntax Error Detected:', message);
                
                // Try to auto-fix common issues
                if (typeof window.hideInstructionsTypes === 'undefined') {
                    console.warn('Auto-initializing hideInstructionsTypes');
                    window.hideInstructionsTypes = ['video', 'audio', 'document', 'image', 'file', 'link', 'web', 'quiz', 'assignment', 'conference', 'discussion'];
                }
            }
            
            // Log to our error handler
            window.LMSErrorHandler.logError(errorMessage, {
                message: message,
                filename: filename,
                lineno: lineno,
                colno: colno,
                stack: error ? error.stack : null
            });
            
            // Suppress error popup in production
            if (window.location.hostname !== 'localhost' && !window.location.hostname.includes('dev')) {
                event.preventDefault();
                return true;
            }
        } catch (handlerError) {
            console.error('Error in error handler:', handlerError);
        }
    }, true);

    // Unhandled promise rejection handler
    window.addEventListener('unhandledrejection', function(event) {
        try {
            var reason = event.reason;
            var message = reason ? (reason.message || reason.toString()) : 'Unknown rejection';
            
            console.error('Unhandled Promise Rejection:', message);
            
            window.LMSErrorHandler.logError('Unhandled Promise Rejection', reason);
            
            // Prevent default handling in production
            if (window.location.hostname !== 'localhost' && !window.location.hostname.includes('dev')) {
                event.preventDefault();
            }
        } catch (handlerError) {
            console.error('Error in rejection handler:', handlerError);
        }
    });

    // Console error wrapper for better tracking
    if (window.location.hostname !== 'localhost' && !window.location.hostname.includes('dev')) {
        var originalConsoleError = console.error;
        console.error = function() {
            // Convert arguments to array
            var args = Array.prototype.slice.call(arguments);
            
            // Check if this is from our error handler
            var isLMSError = args.length > 0 && 
                           (typeof args[0] === 'string') && 
                           args[0].includes('[LMS Error]');
            
            // Only suppress non-LMS errors in production
            if (!isLMSError) {
                // Log to our handler
                window.LMSErrorHandler.logError('Console Error', args.join(' '));
            }
            
            // Always call original for debugging
            originalConsoleError.apply(console, args);
        };
    }

    // Initialize global variables that might be missing
    function initializeMissingGlobals() {
        // Initialize hideInstructionsTypes if not defined
        if (typeof window.hideInstructionsTypes === 'undefined') {
            window.hideInstructionsTypes = ['video', 'audio', 'document', 'image', 'file', 'link', 'web', 'quiz', 'assignment', 'conference', 'discussion'];
        }
        
        // Initialize other commonly used globals
        if (typeof window.toggleContentFields === 'undefined') {
            window.toggleContentFields = function(contentType) {
                console.warn('toggleContentFields called but not yet loaded, deferring...');
                setTimeout(function() {
                    if (typeof window.updateContentTypeSections !== 'undefined') {
                        window.updateContentTypeSections(contentType);
                    }
                }, 100);
            };
        }
    }

    // Run initialization on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initializeMissingGlobals();
            window.LMSErrorHandler.startAutoCleanup();
        });
    } else {
        initializeMissingGlobals();
        window.LMSErrorHandler.startAutoCleanup();
    }

    // Export for module systems
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = window.LMSErrorHandler;
    }

    console.log('✅ Enhanced Error Handler initialized');

})();

// Additional browser compatibility fixes
(function() {
    'use strict';

    // Polyfill for Array.prototype.includes (IE11)
    if (!Array.prototype.includes) {
        Array.prototype.includes = function(searchElement, fromIndex) {
            if (this == null) {
                throw new TypeError('"this" is null or not defined');
            }
            var o = Object(this);
            var len = o.length >>> 0;
            if (len === 0) {
                return false;
            }
            var n = fromIndex | 0;
            var k = Math.max(n >= 0 ? n : len - Math.abs(n), 0);
            while (k < len) {
                if (o[k] === searchElement) {
                    return true;
                }
                k++;
            }
            return false;
        };
    }

    // Polyfill for String.prototype.includes (IE11)
    if (!String.prototype.includes) {
        String.prototype.includes = function(search, start) {
            if (typeof start !== 'number') {
                start = 0;
            }
            if (start + search.length > this.length) {
                return false;
            }
            return this.indexOf(search, start) !== -1;
        };
    }

    // Polyfill for Element.prototype.closest (IE11)
    if (!Element.prototype.closest) {
        Element.prototype.closest = function(s) {
            var el = this;
            do {
                if (el.matches(s)) return el;
                el = el.parentElement || el.parentNode;
            } while (el !== null && el.nodeType === 1);
            return null;
        };
    }

    // Polyfill for Element.prototype.matches (IE11)
    if (!Element.prototype.matches) {
        Element.prototype.matches = Element.prototype.msMatchesSelector || 
                                    Element.prototype.webkitMatchesSelector;
    }

    console.log('✅ Browser compatibility polyfills loaded');

})();
