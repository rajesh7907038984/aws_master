/**
 * Unified Error Handler for LMS
 * Centralized error handling and reporting
 */

(function() {
    'use strict';

    const UnifiedErrorHandler = {
        errors: [],
        maxErrors: 50,
        
        init: function() {
            this.setupGlobalErrorHandling();
            this.setupUnhandledRejectionHandling();
        },
        
        setupGlobalErrorHandling: function() {
            window.addEventListener('error', (event) => {
                this.handleError(event.error, 'JavaScript Error', {
                    filename: event.filename,
                    lineno: event.lineno,
                    colno: event.colno
                });
            });
        },
        
        setupUnhandledRejectionHandling: function() {
            window.addEventListener('unhandledrejection', (event) => {
                this.handleError(event.reason, 'Unhandled Promise Rejection');
            });
        },
        
        handleError: function(error, type, context = {}) {
            const errorInfo = {
                type: type,
                message: error.message || 'Unknown error',
                stack: error.stack || '',
                timestamp: new Date().toISOString(),
                url: window.location.href,
                userAgent: navigator.userAgent,
                context: context
            };
            
            this.errors.push(errorInfo);
            
            // Keep only recent errors
            if (this.errors.length > this.maxErrors) {
                this.errors.shift();
            }
            
            // Log to console in development
            if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
                console.error('Error handled by UnifiedErrorHandler:', errorInfo);
            }
            
            // Send to server in production
            if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
                this.reportError(errorInfo);
            }
        },
        
        reportError: function(errorInfo) {
            fetch('/api/errors/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.getCSRFToken ? window.getCSRFToken() : ''
                },
                body: JSON.stringify(errorInfo)
            }).catch(() => {
                // Silently fail if error reporting fails
            });
        },
        
        getErrors: function() {
            return this.errors;
        },
        
        clearErrors: function() {
            this.errors = [];
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            UnifiedErrorHandler.init();
        });
    } else {
        UnifiedErrorHandler.init();
    }

    // Export to global scope
    window.UnifiedErrorHandler = UnifiedErrorHandler;
})();
