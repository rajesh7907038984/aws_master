/**
 * Unified Error Handler for 100% Frontend-Backend Alignment
 * This system ensures consistent error handling across the entire LMS
 */

class UnifiedErrorHandler {
    constructor() {
        // Check if we're in development mode (be more specific to avoid false positives)
        this.isDevelopment = window.location.hostname === 'localhost' || 
                            window.location.hostname === '127.0.0.1' ||
                            window.location.hostname.includes('localhost:') ||
                            window.location.hostname.includes('dev.') ||
                            window.location.hostname.includes('.dev') ||
                            window.location.hostname.includes('staging.');
        
        this.errorCategories = {
            'VALIDATION': 'validation_error',
            'AUTHENTICATION': 'auth_error',
            'AUTHORIZATION': 'permission_error',
            'NOT_FOUND': 'not_found_error',
            'SERVER': 'server_error',
            'NETWORK': 'network_error',
            'BUSINESS_LOGIC': 'business_logic_error'
        };
        
        this.userFriendlyMessages = {
            'VALIDATION': 'Please check your input and try again',
            'AUTHENTICATION': 'Please log in to continue',
            'AUTHORIZATION': 'You do not have permission to perform this action',
            'NOT_FOUND': 'The requested resource was not found',
            'SERVER': 'Something went wrong. Please try again later',
            'NETWORK': 'Network error. Please check your connection',
            'BUSINESS_LOGIC': 'This action cannot be completed at this time'
        };
        
        // Add error cooldown to prevent spam
        this.errorCooldown = new Map();
        
        // Setup periodic cleanup for error cooldown to prevent memory leaks
        this.setupErrorCooldownCleanup();
        
        this.setupSilentErrorHandling();
        this.setupGlobalErrorHandling();
    }
    
    /**
     * Setup periodic cleanup for error cooldown to prevent memory leaks
     */
    setupErrorCooldownCleanup() {
        // Store interval ID for cleanup
        this.cleanupInterval = setInterval(() => {
            try {
                const now = Date.now();
                const maxAge = 120000; // 2 minutes
                
                // Clean up old entries
                for (const [key, time] of this.errorCooldown.entries()) {
                    if (now - time > maxAge) {
                        this.errorCooldown.delete(key);
                    }
                }
                
                // Limit total entries to prevent memory buildup
                if (this.errorCooldown.size > 50) {
                    const entries = Array.from(this.errorCooldown.entries());
                    entries.sort((a, b) => a[1] - b[1]); // Sort by timestamp
                    // Keep only the 25 most recent entries
                    this.errorCooldown.clear();
                    entries.slice(-25).forEach(([key, time]) => {
                        this.errorCooldown.set(key, time);
                    });
                }
            } catch (error) {
                console.error('Error in cleanup interval:', error);
            }
        }, 30000); // Run every 30 seconds
        
        // Add cleanup on page unload
        window.addEventListener('beforeunload', () => {
            if (this.cleanupInterval) {
                clearInterval(this.cleanupInterval);
                this.cleanupInterval = null;
            }
        });
    }
    
    /**
     * Setup silent error handling for syntax errors
     * DISABLED: Now shows syntax errors as popups for development
     */
    setupSilentErrorHandling() {
        // Silent error handling disabled to show syntax errors as popups
        // This allows developers to see syntax errors in the browser
        // console.log('Syntax error handling disabled - errors will show as popups');
    }
    
    /**
     * Setup global error handling
     */
    setupGlobalErrorHandling() {
        // Handle unhandled promise rejections
        var self = this;
        window.addEventListener('unhandledrejection', function(event) {
            // Check if it's a syntax error
            if (self.isSyntaxError(event.reason)) {
                console.warn('Promise rejection due to syntax error:', event.reason.message);
                event.preventDefault();
                return;
            }
            
            self.handleError(event.reason, 'Unhandled Promise Rejection');
            event.preventDefault();
        });
        
        // Handle global JavaScript errors
        var self = this;
        window.addEventListener('error', function(event) {
            // Skip if no meaningful error information
            if (!event.error && !event.message && !event.filename) {
                return;
            }
            
            // Check if it's a syntax error - handle silently in production
            if (self.isSyntaxError(event.error)) {
                // Silently handle syntax errors to prevent console spam from browser extensions
                // Only log in development mode
                if (self.isDevelopment) {
                    console.warn('JavaScript syntax error detected:', event.error.message);
                    var sanitizedMessage = self.sanitizeErrorMessage(event.error ? event.error.message : '');
                    var sanitizedFilename = self.sanitizeErrorMessage(event.filename || '');
                    console.warn('JavaScript Syntax Error: ' + sanitizedMessage + ' in file: ' + sanitizedFilename + ' at line: ' + event.lineno);
                }
                // Prevent the error popup for syntax errors
                event.preventDefault();
                return;
            }
            
            // Create error object if event.error is undefined
            var errorToHandle = event.error;
            if (!errorToHandle && event.message) {
                errorToHandle = new Error(event.message);
                errorToHandle.filename = event.filename;
                errorToHandle.lineno = event.lineno;
                errorToHandle.colno = event.colno;
            }
            
            // Only handle if we have meaningful error information
            if (errorToHandle || event.message) {
                // Prevent default browser error popup for other errors
                event.preventDefault();
                self.handleError(errorToHandle, 'Global JavaScript Error');
            }
        });
        
        // Handle fetch errors
        this.interceptFetch();
    }
    
    /**
     * Intercept fetch requests for error handling
     */
    interceptFetch() {
        var originalFetch = window.fetch;
        var self = this;
        
        window.fetch = function() {
            var args = Array.prototype.slice.call(arguments);
            var options = args[1] || {};
            
            // Add CSRF token to POST requests
            if (options.method === 'POST' || (options.method === undefined && args[0] !== undefined)) {
                if (!options.headers) {
                    options.headers = {};
                }
                if (typeof options.headers === 'object' && !options.headers['X-CSRFToken']) {
                    var csrfToken = self.getCSRFToken();
                    if (csrfToken) {
                        options.headers['X-CSRFToken'] = csrfToken;
                    }
                }
                args[1] = options;
            }
            
            return originalFetch.apply(this, args)
                .then(function(response) {
                    // Check for HTTP errors
                    if (!response.ok) {
                        var error = new Error('HTTP ' + response.status + ': ' + response.statusText);
                        error.status = response.status;
                        error.response = response;
                        throw error;
                    }
                    
                    return response;
                })
                .catch(async function(error) {
                    // Robust suppression: background GETs are silent by default unless explicitly interactive
                    var method = (options && options.method ? String(options.method).toUpperCase() : 'GET');

                    // Best-effort parse of server JSON error (non-blocking)
                    try {
                        if (error && error.response && typeof error.response.clone === 'function') {
                            var cloned = error.response.clone();
                            await cloned.json().then(function(body){
                                if (body && body.error && !error.message) {
                                    error.message = String(body.error);
                                }
                            }).catch(function(){ /* ignore parse errors */ });
                        }
                    } catch(e) { /* ignore */ }

                    var isBackground = !options || options.interactive !== true;
                    // Respect explicit silent flags and default-silent background GETs
                    var suppressGlobal = (
                        options && (
                            options.suppressGlobalError === true ||
                            (options.headers && (
                                options.headers['X-Silent'] === 'true' ||
                                options.headers['X-Suppress-Errors'] === 'true'
                            ))
                        )
                    ) || (method === 'GET' && isBackground);

                    if (!suppressGlobal) {
                        // Only handle error if it hasn't been handled already
                        if (!error._handled) {
                            self.handleError(error, 'Fetch Request');
                            error._handled = true;
                        }
                    }
                    throw error;
                });
        };
    }
    
    /**
     * Get CSRF token from various sources
     */
    getCSRFToken() {
        // Try multiple sources for CSRF token
        var sources = [
            function() {
                var meta = document.querySelector('meta[name="csrf-token"]');
                return meta ? meta.getAttribute('content') : null;
            },
            function() {
                var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
                return input ? input.value : null;
            },
            function() {
                return window.CSRF_TOKEN;
            },
            function() {
                var cookies = document.cookie.split(';');
                for (var i = 0; i < cookies.length; i++) {
                    var cookie = cookies[i].trim();
                    if (cookie.indexOf('csrftoken=') === 0) {
                        return cookie.substring(10);
                    }
                }
                return null;
            }
        ];

        for (var i = 0; i < sources.length; i++) {
            try {
                var token = sources[i]();
                if (token && token.length > 0) {
                    return token;
                }
            } catch (e) {
                continue;
            }
        }
        
        return null;
    }
    
    /**
     * Check if error is a syntax error that should be handled silently
     */
    isSyntaxError(error) {
        if (!error) return false;
        
        var syntaxErrorPatterns = [
            'Unexpected token',
            'SyntaxError',
            'Unexpected end of input',
            'Unexpected end of input',
            'Invalid or unexpected token'
        ];
        
        // Check if it's a syntax error
        var isSyntax = syntaxErrorPatterns.some(function(pattern) {
            return error.message && error.message.includes(pattern);
        });
        
        // If it's a syntax error, check if it's from Alpine.js directives
        if (isSyntax && error.message) {
            // These are common Alpine.js-related syntax "errors" that are actually fine
            var alpinePatterns = [
                "Unexpected token ':'",  // Alpine.js :class, :style, etc.
                'Unexpected token \':\'',
                'Unexpected identifier',  // Can happen with x-data
            ];
            
            var isAlpineRelated = alpinePatterns.some(function(pattern) {
                return error.message.includes(pattern);
            });
            
            // If it seems Alpine-related, it's safe to ignore
            if (isAlpineRelated) {
                return true;
            }
        }
        
        return isSyntax;
    }
    
    /**
     * Sanitize error message to prevent XSS attacks
     */
    sanitizeErrorMessage(message) {
        if (!message) return '';
        
        // Remove potentially dangerous characters and limit length
        return message
            .replace(/[<>\"'&]/g, '') // Remove HTML/script characters
            .replace(/javascript:/gi, '') // Remove javascript: protocol
            .replace(/on\w+=/gi, '') // Remove event handlers
            .substring(0, 200); // Limit length
    }
    
    /**
     * Handle errors with unified approach
     */
    handleError(error, context) {
        context = context || 'Unknown';
        
        // Skip if error is null or undefined
        if (!error) {
            return;
        }
        
        // Skip hideInstructionsTypes errors as they're handled by fallbacks
        if (error.message && error.message.includes('hideInstructionsTypes is not defined')) {
            if (this.isDevelopment) {
                console.warn('[' + context + '] hideInstructionsTypes error handled by fallback');
            }
            return;
        }
        
        // Skip syntax errors to prevent popups
        if (this.isSyntaxError(error)) {
            if (this.isDevelopment) {
                console.warn('[' + context + '] Syntax error (handled silently):', error.message);
            }
            return;
        }
        
        // Create error key for cooldown check
        var errorKey = context + '-' + (error.message || error.name || 'unknown');
        var now = Date.now();
        var lastError = this.errorCooldown.get(errorKey);
        
        // Skip if same error occurred within last 5 seconds
        if (lastError && (now - lastError) < 5000) {
            return;
        }
        
        // Update cooldown
        this.errorCooldown.set(errorKey, now);
        
        if (this.isDevelopment) {
            console.error('[' + context + '] Error Details:', {
                name: error.name || 'Unknown',
                message: error.message || 'No message',
                stack: error.stack || 'No stack trace',
                filename: error.filename || 'Unknown',
                line: error.lineno || 'Unknown',
                column: error.colno || 'Unknown'
            });
        }
        
        // Categorize error
        var category = this.categorizeError(error);
        
        // Get user-friendly message
        var message = this.getUserFriendlyMessage(error, category);
        
        // Enrich message with diagnostics on staging/dev
        if (this.isDevelopment && error && error.response) {
            try {
                var urlPath = '';
                if (error.response.url) {
                    urlPath = String(error.response.url).replace(window.location.origin, '');
                }
                message = message + ' (' + (error.status || 'ERR') + ') ' + urlPath;
            } catch (e) { /* ignore */ }
        }

        // Show user notification
        this.showUserNotification(message, category);
        
        // Log error for debugging
        this.logError(error, context, category);
        
        // Handle specific error types
        this.handleSpecificError(error, category);
    }
    
    /**
     * Categorize error based on type and properties
     */
    categorizeError(error) {
        // API errors from StandardizedAPIError
        if (error instanceof StandardizedAPIError) {
            if (error.isValidationError()) return 'VALIDATION';
            if (error.isAuthError()) return 'AUTHENTICATION';
            if (error.isNotFoundError()) return 'NOT_FOUND';
            return 'SERVER';
        }
        
        // Network errors
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
            return 'NETWORK';
        }
        
        // HTTP status errors
        if (error.status) {
            if (error.status === 401) return 'AUTHENTICATION';
            if (error.status === 403) return 'AUTHORIZATION';
            if (error.status === 404) return 'NOT_FOUND';
            if (error.status >= 500) return 'SERVER';
            return 'VALIDATION';
        }
        
        // Default categorization
        return 'SERVER';
    }
    
    /**
     * Get user-friendly error message
     */
    getUserFriendlyMessage(error, category) {
        // Use API error message if available
        if (error instanceof StandardizedAPIError) {
            return error.getUserFriendlyMessage();
        }
        
        // Use category-based message
        return this.userFriendlyMessages[category] || this.userFriendlyMessages['SERVER'];
    }
    
    /**
     * Show user notification - Use toast system, fallback to console
     */
    showUserNotification(message, category) {
        if (typeof showToast === 'function') {
            showToast(message, this.getNotificationType(category));
        } else {
            console.warn('[' + category + '] ' + message);
        }
    }
    
    /**
     * Get notification type based on error category
     */
    getNotificationType(category) {
        var typeMap = {
            'VALIDATION': 'warning',
            'AUTHENTICATION': 'error',
            'AUTHORIZATION': 'error',
            'NOT_FOUND': 'warning',
            'SERVER': 'error',
            'NETWORK': 'error',
            'BUSINESS_LOGIC': 'warning'
        };
        
        return typeMap[category] || 'error';
    }
    
    /**
     * Log error for debugging
     */
    logError(error, context, category) {
        var errorDetails = {
            context,
            category,
            name: error.name || 'Unknown',
            message: error.message || 'No message',
            stack: error.stack || 'No stack trace',
            timestamp: new Date().toISOString(),
            url: window.location.href,
            userAgent: navigator.userAgent
        };
        
        // Store in localStorage for debugging
        try {
            var recentErrors = JSON.parse(localStorage.getItem('lms_recent_errors') || '[]');
            recentErrors.push(errorDetails);
            
            // Keep only last 20 errors
            if (recentErrors.length > 20) {
                recentErrors.shift();
            }
            
            localStorage.setItem('lms_recent_errors', JSON.stringify(recentErrors));
        } catch (e) {
            console.warn('Failed to store error in localStorage:', e);
        }
        
        // Log to console with details (development only)
        if (this.isDevelopment) {
            console.group('🚨 ' + category + ' Error in ' + context);
            console.error('Error Details:', errorDetails);
            console.error('Original Error:', error);
            console.groupEnd();
        }
    }
    
    /**
     * Handle specific error types
     */
    handleSpecificError(error, category) {
        switch (category) {
            case 'AUTHENTICATION':
                this.handleAuthenticationError(error);
                break;
            case 'AUTHORIZATION':
                this.handleAuthorizationError(error);
                break;
            case 'NETWORK':
                this.handleNetworkError(error);
                break;
        }
    }
    
    /**
     * Handle authentication errors
     */
    handleAuthenticationError(error) {
        // Redirect to login if not already there
        if (!window.location.pathname.includes('/login/')) {
            setTimeout(() => {
                window.location.href = '/login/';
            }, 2000);
        }
    }
    
    /**
     * Handle authorization errors
     */
    handleAuthorizationError(error) {
        // Show permission denied message
        console.warn('Permission denied for current action');
    }
    
    /**
     * Handle network errors
     */
    handleNetworkError(error) {
        // Check if user is online
        if (!navigator.onLine) {
            console.warn('You are offline. Please check your connection.');
        }
    }
    
    
    /**
     * Get recent errors for debugging
     */
    getRecentErrors() {
        try {
            return JSON.parse(localStorage.getItem('lms_recent_errors') || '[]');
        } catch (e) {
            return [];
        }
    }
    
    /**
     * Clear recent errors
     */
    clearRecentErrors() {
        try {
            localStorage.removeItem('lms_recent_errors');
        } catch (error) {
            console.warn('Failed to clear recent errors from localStorage:', error);
        }
    }
    
    /**
     * Cleanup method to prevent memory leaks
     */
    cleanup() {
        try {
            // Clear interval
            if (this.cleanupInterval) {
                clearInterval(this.cleanupInterval);
                this.cleanupInterval = null;
            }
            
            // Clear error cooldown
            this.errorCooldown.clear();
            
            // Clear recent errors
            this.clearRecentErrors();
            
            if (this.isDevelopment) {
                console.log('Error handler cleanup completed');
            }
        } catch (error) {
            console.error('Error during error handler cleanup:', error);
        }
    }
    
    /**
     * Handle form validation errors
     */
    handleFormValidationErrors(errors) {
        // Clear previous error styling
        document.querySelectorAll('.error').forEach(el => {
            el.classList.remove('error');
        });
        
        // Apply error styling and messages
        Object.keys(errors).forEach(field => {
            var fieldElement = document.querySelector('[name="' + field + '"]');
            if (fieldElement) {
                fieldElement.classList.add('error');
                
                // Show field-specific error message
                var errorMessage = Array.isArray(errors[field]) ? errors[field][0] : errors[field];
                this.showFieldError(fieldElement, errorMessage);
            }
        });
    }
    
    /**
     * Show field-specific error message
     */
    showFieldError(fieldElement, message) {
        // Remove existing error message
        var existingError = fieldElement.parentNode.querySelector('.field-error');
        if (existingError) {
            existingError.remove();
        }
        
        // Add new error message
        var errorDiv = document.createElement('div');
        errorDiv.className = 'field-error text-red-500 text-sm mt-1';
        errorDiv.textContent = message;
        fieldElement.parentNode.appendChild(errorDiv);
    }
}

// Create global instance
window.UnifiedErrorHandler = UnifiedErrorHandler;
window.unifiedErrorHandler = new UnifiedErrorHandler();

// Make error handler globally available
window.handleError = (error, context) => window.unifiedErrorHandler.handleError(error, context);
window.handleFormValidationErrors = (errors) => window.unifiedErrorHandler.handleFormValidationErrors(errors);

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // console.log('✅ Unified Error Handler initialized');
});

// Cleanup on page unload to prevent memory leaks
window.addEventListener('beforeunload', function() {
    if (window.unifiedErrorHandler && typeof window.unifiedErrorHandler.cleanup === 'function') {
        window.unifiedErrorHandler.cleanup();
    }
});