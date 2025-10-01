/**
 * Universal Error Handler for LMS JavaScript
 * Provides standardized error handling, CSRF management, and form processing across all JS files
 */

(function() {
    'use strict';

    // Global LMS namespace
    window.LMS = window.LMS || {};
    
    // Ensure TypeSafety utilities are available
    const TypeSafety = window.LMS.TypeSafety || window.TypeSafety || {};
    
    // Universal Error Handler
    window.LMS.ErrorHandler = {
        
        // Configuration
        config: {
            debugMode: false,
            showDetailedErrors: false,
            maxRetries: 3,
            retryDelay: 1000,
            timeoutDuration: 30000,
            productionMode: true // Enable production mode for better error handling
        },

        // Initialize the error handler
        init: function(options = {}) {
            this.config = { ...this.config, ...options };
            this.setupGlobalErrorHandling();
            this.setupCSRFTokenManagement();
            this.setupNetworkErrorHandling();
            console.log('LMS Universal Error Handler initialized');
        },

        // Setup global error handling with enhanced user feedback
        setupGlobalErrorHandling: function() {
            // Handle uncaught JavaScript errors
            window.addEventListener('error', (event) => {
                this.logError('JavaScript Error', {
                    message: event.message,
                    filename: event.filename,
                    lineno: event.lineno,
                    colno: event.colno,
                    stack: event.error ? event.error.stack : 'No stack trace'
                });
                
                // DON'T show automatic error messages - only log to console
                // Critical errors should be handled by specific error handlers
                // This prevents false error messages for expected errors
                if (this.config.debugMode) {
                    console.warn('JavaScript error caught by global handler:', event.message);
                }
            });

            // Handle unhandled promise rejections
            window.addEventListener('unhandledrejection', (event) => {
                this.logError('Unhandled Promise Rejection', {
                    reason: event.reason,
                    promise: event.promise
                });
                
                // DON'T prevent console logging - developers need to see these
                // DON'T show automatic error notifications
                // Let specific handlers deal with user-facing errors
                if (this.config.debugMode) {
                    console.warn('Unhandled promise rejection:', event.reason);
                }
            });
        },

        // CSRF Token Management
        setupCSRFTokenManagement: function() {
            this.csrfToken = this.getCSRFToken();
            
            // Refresh CSRF token periodically
            setInterval(() => {
                this.refreshCSRFToken();
            }, 300000); // Every 5 minutes
        },

        // Get CSRF token from multiple sources
        getCSRFToken: function() {
            const sources = [
                () => document.querySelector('meta[name="csrf-token"]')?.getAttribute('content'),
                () => document.querySelector('input[name="csrfmiddlewaretoken"]')?.value,
                () => window.CSRF_TOKEN,
                () => this.getCookieValue('csrftoken'),
                () => document.cookie.match(/csrftoken=([^;]+)/)?.[1]
            ];

            for (let source of sources) {
                try {
                    const token = source();
                    if (token && token.length > 10) {
                        return token;
                    }
                } catch (e) {
                    // Continue to next source
                }
            }
            
            console.warn('CSRF token not found');
            return null;
        },

        // Refresh CSRF token
        refreshCSRFToken: function() {
            const newToken = this.getCSRFToken();
            if (newToken && newToken !== this.csrfToken) {
                this.csrfToken = newToken;
            }
        },

        // Get cookie value
        getCookieValue: function(name) {
            const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
            return match ? match[2] : null;
        },

        // Enhanced fetch wrapper with error handling
        fetch: async function(url, options = {}) {
            options = this.prepareRequestOptions(options);
            
            let attempt = 0;
            const maxRetries = options.maxRetries || this.config.maxRetries;
            
            while (attempt <= maxRetries) {
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), this.config.timeoutDuration);
                    
                    const response = await fetch(url, {
                        ...options,
                        signal: controller.signal
                    });
                    
                    clearTimeout(timeoutId);
                    
                    return await this.handleResponse(response, url, options);
                    
                } catch (error) {
                    attempt++;
                    
                    if (attempt > maxRetries || !this.isRetryableError(error)) {
                        throw this.createEnhancedError(error, url, options);
                    }
                    
                    // Wait before retrying
                    await this.delay(this.config.retryDelay * attempt);
                }
            }
        },

        // Prepare request options with CSRF and defaults
        prepareRequestOptions: function(options) {
            options.headers = options.headers || {};
            
            // Use centralized CSRF token manager if available
            if (window.CSRFManager) {
                options.headers = window.CSRFManager.addTokenToHeaders(options.headers);
            } else {
                // Fallback to manual CSRF token handling
                if (options.method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(options.method.toUpperCase())) {
                    if (!options.headers['X-CSRFToken']) {
                        options.headers['X-CSRFToken'] = this.csrfToken || this.getCSRFToken();
                    }
                }
            }
            
            // Add common headers
            if (!options.headers['X-Requested-With']) {
                options.headers['X-Requested-With'] = 'XMLHttpRequest';
            }
            
            return options;
        },

        // Handle response with comprehensive error checking
        handleResponse: async function(response, url, options) {
            // Check for specific error types
            if (response.status === 403) {
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    try {
                        const data = await response.json();
                        if (data && data.error_type === 'csrf_error') {
                            this.handleCSRFError();
                            throw new Error('CSRF token expired. Please refresh the page.');
                        }
                    } catch (jsonError) {
                        // If JSON parsing fails, continue with generic error
                        console.warn('Failed to parse JSON error response:', jsonError);
                    }
                }
                throw new Error('Permission denied. Please check your access rights.');
            }
            
            if (response.status === 404) {
                throw new Error('The requested resource was not found.');
            }
            
            if (response.status >= 500) {
                throw new Error('Server error. Please try again later.');
            }
            
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Request failed: ${response.status} ${response.statusText}${errorText ? ` - ${errorText}` : ''}`);
            }
            
            return response;
        },

        // Check if error is retryable
        isRetryableError: function(error) {
            const retryableErrors = [
                'NetworkError',
                'TimeoutError', 
                'AbortError',
                'TypeError' // Often network-related
            ];
            
            const retryableMessages = [
                'Failed to fetch',
                'network',
                'timeout',
                'connection',
                'ECONNRESET',
                'ENOTFOUND',
                'ETIMEDOUT',
                'ECONNREFUSED'
            ];
            
            return retryableErrors.some(type => 
                error.name === type || 
                error.message.includes(type)
            ) || retryableMessages.some(msg => 
                error.message.toLowerCase().includes(msg.toLowerCase())
            );
        },

        // Create enhanced error with context
        createEnhancedError: function(error, url, options) {
            const enhancedError = new Error(error.message);
            enhancedError.originalError = error;
            enhancedError.url = url;
            enhancedError.options = options;
            enhancedError.timestamp = new Date().toISOString();
            
            this.logError('Network Request Failed', {
                url: url,
                method: options.method || 'GET',
                error: error.message,
                stack: error.stack
            });
            
            return enhancedError;
        },

        // Handle CSRF errors
        handleCSRFError: function() {
            this.showError('Security token expired. Please refresh the page and try again.');
            this.refreshCSRFToken();
        },

        // Network error handling setup
        setupNetworkErrorHandling: function() {
            // Monitor network status
            window.addEventListener('online', () => {
                this.showSuccess('Connection restored');
            });
            
            window.addEventListener('offline', () => {
                this.showError('No internet connection. Please check your network.');
            });
        },

        // Utility function for delays
        delay: function(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        },

        // Form submission with comprehensive error handling
        submitForm: async function(form, options = {}) {
            if (!form) {
                throw new Error('Form element is required');
            }

            // Prevent double submission
            if (form.hasAttribute('data-submitting')) {
                return;
            }

            try {
                form.setAttribute('data-submitting', 'true');
                this.setLoadingState(form, true);

                const formData = new FormData(form);
                const url = options.url || form.action || window.location.href;
                
                const response = await this.fetch(url, {
                    method: 'POST',
                    body: formData,
                    ...options
                });

                if (options.expectJson !== false) {
                    const data = await response.json();
                    
                    if (data.success === false) {
                        this.handleFormErrors(form, data.errors || {}, data.message);
                        return { success: false, data: data };
                    }
                    
                    return { success: true, data: data };
                } else {
                    return { success: true, response: response };
                }

            } catch (error) {
                this.showError(error.message);
                return { success: false, error: error };
            } finally {
                form.removeAttribute('data-submitting');
                this.setLoadingState(form, false);
            }
        },

        // Handle form errors
        handleFormErrors: function(form, errors, message) {
            if (!form) {
                console.warn('handleFormErrors called with null/undefined form');
                return;
            }
            
            // Clear previous errors
            form.querySelectorAll('.field-error').forEach(el => el.remove());
            
            // Show general message
            if (message && typeof message === 'string') {
                this.showError(message);
            }
            
            // Show field-specific errors with type safety
            if (errors && typeof errors === 'object' && !Array.isArray(errors)) {
                for (const [field, fieldErrors] of Object.entries(errors)) {
                    if (typeof field === 'string') {
                        const fieldElement = form.querySelector(`[name="${field}"]`);
                        if (fieldElement) {
                            this.showFieldError(fieldElement, fieldErrors);
                        }
                    }
                }
            }
        },

        // Show field-specific error
        showFieldError: function(field, errors) {
            if (!field) {
                console.warn('showFieldError called with null/undefined field');
                return;
            }
            
            const errorDiv = document.createElement('div');
            errorDiv.className = 'field-error text-red-600 text-sm mt-1';
            
            // Type-safe error message extraction
            let errorMessage = '';
            if (Array.isArray(errors) && errors.length > 0) {
                errorMessage = String(errors[0]);
            } else if (errors) {
                errorMessage = String(errors);
            } else {
                errorMessage = 'An error occurred';
            }
            
            errorDiv.textContent = errorMessage;
            
            field.classList.add('border-red-500');
            field.parentNode.insertBefore(errorDiv, field.nextSibling);
            
            // Clear error on focus
            field.addEventListener('focus', () => {
                field.classList.remove('border-red-500');
                if (errorDiv.parentNode) {
                    errorDiv.remove();
                }
            }, { once: true });
        },

        // Set loading state for forms
        setLoadingState: function(form, loading) {
            const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
            
            if (submitButton) {
                if (loading) {
                    submitButton.disabled = true;
                    submitButton.setAttribute('data-original-text', submitButton.textContent || submitButton.value);
                    
                    if (submitButton.tagName.toLowerCase() === 'button') {
                        submitButton.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Processing...';
                    } else {
                        submitButton.value = 'Processing...';
                    }
                } else {
                    submitButton.disabled = false;
                    const originalText = submitButton.getAttribute('data-original-text');
                    
                    if (originalText) {
                        if (submitButton.tagName.toLowerCase() === 'button') {
                            submitButton.innerHTML = originalText;
                        } else {
                            submitButton.value = originalText;
                        }
                        submitButton.removeAttribute('data-original-text');
                    }
                }
            }
        },

        // Error logging
        logError: function(title, details) {
            if (this.config.debugMode) {
                console.error(`[LMS] ${title}:`, details);
            }
            
            // Send to server if logging endpoint exists
            this.sendErrorToServer(title, details);
        },

        // Send error to server
        sendErrorToServer: function(title, details) {
            // Only send in production and if endpoint exists
            if (this.config.debugMode) return;
            
            try {
                fetch('/core/log-error/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken
                    },
                    body: JSON.stringify({
                        title: title,
                        details: details,
                        url: window.location.href,
                        userAgent: navigator.userAgent,
                        timestamp: new Date().toISOString()
                    })
                }).catch(() => {
                    // Fail silently if logging endpoint is not available
                });
            } catch (e) {
                // Fail silently
            }
        },

        // User notification methods
        showError: function(message) {
            this.showNotification(message, 'error');
        },

        showSuccess: function(message) {
            this.showNotification(message, 'success');
        },

        showWarning: function(message) {
            this.showNotification(message, 'warning');
        },

        showInfo: function(message) {
            this.showNotification(message, 'info');
        },

        // Generic notification display
        showNotification: function(message, type = 'info') {
            // Try to use existing notification system
            if (window.showToast && typeof window.showToast === 'function') {
                window.showToast(message, type);
                return;
            }

            // Fallback to our own notification system
            this.createNotification(message, type);
        },

        // Create notification element
        createNotification: function(message, type) {
            const notification = document.createElement('div');
            notification.className = `lms-notification lms-notification-${type}`;
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000;
                max-width: 400px;
                padding: 12px 16px;
                border-radius: 8px;
                color: white;
                font-size: 14px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                cursor: pointer;
                transform: translateX(100%);
                transition: transform 0.3s ease;
            `;

            // Set background color based on type
            const colors = {
                error: '#dc3545',
                success: '#28a745', 
                warning: '#ffc107',
                info: '#17a2b8'
            };
            notification.style.backgroundColor = colors[type] || colors.info;

            notification.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span>${message}</span>
                    <button style="background: none; border: none; color: white; font-size: 18px; margin-left: 8px; cursor: pointer;">&times;</button>
                </div>
            `;

            document.body.appendChild(notification);

            // Animate in
            setTimeout(() => {
                notification.style.transform = 'translateX(0)';
            }, 10);

            // Auto remove
            const removeNotification = () => {
                notification.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    if (notification.parentNode) {
                        notification.remove();
                    }
                }, 300);
            };

            // Click to dismiss
            notification.addEventListener('click', removeNotification);

            // Auto dismiss
            setTimeout(removeNotification, type === 'error' ? 8000 : 4000);
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.LMS.ErrorHandler.init();
        });
    } else {
        window.LMS.ErrorHandler.init();
    }

    // Make methods globally available for backwards compatibility
    window.showError = (message) => window.LMS.ErrorHandler.showError(message);
    window.showSuccess = (message) => window.LMS.ErrorHandler.showSuccess(message);
    window.showWarning = (message) => window.LMS.ErrorHandler.showWarning(message);
    window.showInfo = (message) => window.LMS.ErrorHandler.showInfo(message);
    
    // Enhanced fetch for global use
    window.LMSFetch = (url, options) => window.LMS.ErrorHandler.fetch(url, options);
    
    // Enhanced form submission
    window.submitLMSForm = (form, options) => window.LMS.ErrorHandler.submitForm(form, options);

})();
