/**
 * Production Error Handler
 * ========================
 * 
 * Enhanced error handling specifically for production environment.
 * Provides better error messages, retry logic, and user feedback.
 */

(function() {
    'use strict';

    // Production Error Handler Configuration
    const ProductionErrorHandler = {
        config: {
            maxRetries: 3,
            baseDelay: 1000,
            maxDelay: 8000,
            timeoutDuration: 30000,
            enableDetailedLogging: true,
            enableUserNotifications: true // Enable notifications for better user feedback
        },

        // Initialize the production error handler
        init: function() {
            this.setupGlobalErrorHandling();
            this.setupNetworkMonitoring();
            this.setupAPIErrorHandling();
            console.log('Production Error Handler initialized');
        },

        // Setup global error handling for production
        setupGlobalErrorHandling: function() {
            // Override console.error to include more context in production
            const originalConsoleError = console.error;
            console.error = function(...args) {
                const timestamp = new Date().toISOString();
                const context = {
                    timestamp: timestamp,
                    url: window.location.href,
                    userAgent: navigator.userAgent,
                    args: args
                };
                
                // Log to console with context
                originalConsoleError.call(console, `[${timestamp}]`, ...args);
                
                // In production, you might want to send this to a logging service
                // Disabled for development - only log to server in true production
                if (false) {
                    this.logToServer('error', context);
                }
            }.bind(this);
        },

        // Setup network monitoring
        setupNetworkMonitoring: function() {
            let isOnline = navigator.onLine;
            let reconnectAttempts = 0;
            const maxReconnectAttempts = 5;

            window.addEventListener('online', () => {
                isOnline = true;
                reconnectAttempts = 0;
                this.showNotification('Connection restored', 'success');
                this.retryFailedRequests();
            });

            window.addEventListener('offline', () => {
                isOnline = false;
                this.showNotification('Connection lost. Please check your internet connection.', 'warning');
            });

            // Periodic connection check
            setInterval(() => {
                if (!isOnline && navigator.onLine) {
                    isOnline = true;
                    reconnectAttempts = 0;
                    this.showNotification('Connection restored', 'success');
                    this.retryFailedRequests();
                }
            }, 5000);
        },

        // Setup enhanced API error handling
        setupAPIErrorHandling: function() {
            const originalFetch = window.fetch;
            const self = this;

            window.fetch = function(url, options = {}) {
                return self.enhancedFetch(url, options, originalFetch);
            };
        },

        // Enhanced fetch with production-specific error handling
        enhancedFetch: function(url, options, originalFetch) {
            const startTime = Date.now();
            const retryCount = options.retryCount || 0;
            const maxRetries = options.maxRetries || this.config.maxRetries;

            // Add production-specific headers
            options.headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                ...options.headers
            };

            // Set timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.config.timeoutDuration);
            options.signal = controller.signal;

            return originalFetch(url, options)
                .then(response => {
                    clearTimeout(timeoutId);
                    const duration = Date.now() - startTime;
                    
                    // Log successful requests in production
                    if (this.config.enableDetailedLogging) {
                        console.log(`API call successful: ${url} (${duration}ms)`);
                    }

                    return this.handleResponse(response, url, options);
                })
                .catch(error => {
                    clearTimeout(timeoutId);
                    const duration = Date.now() - startTime;
                    
                    // Log error with context
                    console.error(`API call failed: ${url} (${duration}ms)`, error);

                    return this.handleError(error, url, options, retryCount, maxRetries, originalFetch);
                });
        },

        // Handle API response
        handleResponse: function(response, url, options) {
            if (!response.ok) {
                const error = new Error(`HTTP ${response.status}: ${response.statusText}`);
                error.status = response.status;
                error.url = url;
                throw error;
            }

            // Return the response object as-is to preserve proper HTTP response structure
            // Let the calling code handle JSON parsing if needed
            return response;
        },

        // Handle API errors with retry logic
        handleError: function(error, url, options, retryCount, maxRetries, originalFetch) {
            const isRetryable = this.isRetryableError(error);
            
            if (retryCount < maxRetries && isRetryable) {
                const delay = this.calculateRetryDelay(retryCount);
                
                console.warn(`Retrying API call (${retryCount + 1}/${maxRetries}) after ${delay}ms: ${url}`);
                
                return new Promise(resolve => {
                    setTimeout(() => {
                        const retryOptions = { ...options, retryCount: retryCount + 1 };
                        resolve(this.enhancedFetch(url, retryOptions, originalFetch));
                    }, delay);
                });
            }

            // Final error - show user-friendly message
            this.showUserFriendlyError(error, url);
            throw error;
        },

        // Check if error is retryable
        isRetryableError: function(error) {
            const retryableErrors = [
                'TypeError',
                'NetworkError',
                'TimeoutError',
                'AbortError'
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

            return retryableErrors.some(type => error.name === type) ||
                   retryableMessages.some(msg => 
                       error.message.toLowerCase().includes(msg.toLowerCase())
                   ) ||
                   (error.status >= 500 && error.status < 600);
        },

        // Calculate retry delay with exponential backoff
        calculateRetryDelay: function(retryCount) {
            const delay = this.config.baseDelay * Math.pow(2, retryCount);
            const jitter = Math.random() * 1000; // Add jitter
            return Math.min(delay + jitter, this.config.maxDelay);
        },

        // Show user-friendly error message
        showUserFriendlyError: function(error, url) {
            let message = 'An error occurred. Please try again.';
            
            if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
                message = 'Unable to connect to the server. Please check your internet connection.';
            } else if (error.name === 'AbortError') {
                message = 'Request timed out. Please try again.';
            } else if (error.status === 403) {
                message = 'Permission denied. Please refresh the page and try again.';
            } else if (error.status === 404) {
                // Don't show 404 errors automatically - they might be expected (e.g., optional resources)
                // Only log to console for debugging
                console.warn('Resource not found:', url);
                return; // Don't show notification
            } else if (error.status >= 500) {
                message = 'Server error. Please try again in a few moments.';
            }

            this.showNotification(message, 'error');
        },

        // Show notification to user
        showNotification: function(message, type = 'info') {
            if (!this.config.enableUserNotifications) return;

            // Create notification element
            const notification = document.createElement('div');
            notification.className = `production-notification production-notification-${type}`;
            notification.innerHTML = `
                <div class="notification-content">
                    <span class="notification-message">${message}</span>
                    <button class="notification-close">&times;</button>
                </div>
            `;

            // Add styles
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: ${type === 'error' ? '#f8d7da' : type === 'warning' ? '#fff3cd' : '#d1ecf1'};
                color: ${type === 'error' ? '#721c24' : type === 'warning' ? '#856404' : '#0c5460'};
                border: 1px solid ${type === 'error' ? '#f5c6cb' : type === 'warning' ? '#ffeaa7' : '#bee5eb'};
                border-radius: 4px;
                padding: 12px 16px;
                max-width: 400px;
                z-index: 10000;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 14px;
            `;

            // Add to page
            document.body.appendChild(notification);

            // Auto-remove after 5 seconds
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 5000);

            // Close button functionality
            const closeBtn = notification.querySelector('.notification-close');
            closeBtn.addEventListener('click', () => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            });
        },

        // Retry failed requests when connection is restored
        retryFailedRequests: function() {
            // This would be implemented to retry any queued failed requests
            console.log('Retrying failed requests...');
        },

        // Log to server (placeholder for production logging service)
        logToServer: function(level, data) {
            // In a real production environment, you would send this to your logging service
            // For now, we'll just log to console
            console.log(`[${level.toUpperCase()}]`, data);
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            ProductionErrorHandler.init();
        });
    } else {
        ProductionErrorHandler.init();
    }

    // Make it globally available
    window.ProductionErrorHandler = ProductionErrorHandler;

})();
