/**
 * Global Error Handler for LMS
 * ============================
 * 
 * This module provides centralized error handling and recovery
 * for JavaScript errors, AJAX failures, and network issues.
 */

class GlobalErrorHandler {
    constructor() {
        this.maxRetries = 3;
        this.retryDelay = 1000; // 1 second
        this.errors = [];
        this.lastNotification = null;
        this.notificationTimeout = null;
        this.enableNotifications = false; // Disable notifications for development
        
        this.init();
    }

    init() {
        // Handle unhandled JavaScript errors
        window.addEventListener('error', (event) => {
            this.handleJSError(event.error, event.filename, event.lineno);
        });

        // Handle unhandled promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            this.handlePromiseRejection(event.reason);
            event.preventDefault(); // Prevent console spam
        });

        // Handle network connectivity issues
        window.addEventListener('online', () => {
            this.handleNetworkRestore();
        });

        window.addEventListener('offline', () => {
            this.handleNetworkLoss();
        });

        // Add AJAX error handling to jQuery if available
        if (typeof $ !== 'undefined') {
            $(document).ajaxError((event, jqXHR, ajaxSettings, thrownError) => {
                this.handleAjaxError(jqXHR, ajaxSettings, thrownError);
            });
        }
    }

    /**
     * Handle JavaScript runtime errors
     * @param {Error} error 
     * @param {string} filename 
     * @param {number} lineno 
     */
    handleJSError(error, filename, lineno) {
        const errorInfo = {
            type: 'javascript',
            message: error.message || 'Unknown JavaScript error',
            filename: filename || 'unknown',
            lineno: lineno || 0,
            stack: error.stack,
            timestamp: new Date().toISOString(),
            url: window.location.href
        };

        this.logError(errorInfo);

        // Try to recover from common errors
        if (error.message && error.message.includes('CSRF')) {
            this.handleCSRFError();
        } else if (error.message && error.message.includes('Network')) {
            this.handleNetworkError();
        }
    }

    /**
     * Handle unhandled promise rejections
     * @param {*} reason 
     */
    handlePromiseRejection(reason) {
        const errorInfo = {
            type: 'promise_rejection',
            message: reason?.message || String(reason) || 'Promise rejection',
            timestamp: new Date().toISOString(),
            url: window.location.href
        };

        this.logError(errorInfo);

        // Try to recover from fetch errors
        if (reason?.name === 'TypeError' && reason?.message?.includes('fetch')) {
            this.handleNetworkError();
        }
    }

    /**
     * Handle AJAX errors
     * @param {Object} jqXHR 
     * @param {Object} ajaxSettings 
     * @param {string} thrownError 
     */
    handleAjaxError(jqXHR, ajaxSettings, thrownError) {
        const errorInfo = {
            type: 'ajax',
            status: jqXHR.status,
            statusText: jqXHR.statusText,
            url: ajaxSettings.url,
            method: ajaxSettings.type,
            error: thrownError,
            timestamp: new Date().toISOString()
        };

        this.logError(errorInfo);

        // Handle specific status codes
        if (jqXHR.status === 403) {
            this.handleCSRFError();
        } else if (jqXHR.status === 404) {
            this.handleNotFoundError(ajaxSettings.url);
        } else if (jqXHR.status >= 500) {
            this.handleServerError();
        } else if (jqXHR.status === 0) {
            this.handleNetworkError();
        }
    }

    /**
     * Handle CSRF token errors
     */
    handleCSRFError() {
        this.showNotification(
            'Session expired. Refreshing page...', 
            'warning',
            () => {
                // Try to refresh CSRF token if manager is available
                if (window.csrfManager) {
                    window.csrfManager.refresh();
                    this.showNotification('Session refreshed. Please try again.', 'info');
                } else {
                    // Fallback: reload page
                    setTimeout(() => window.location.reload(), 2000);
                }
            }
        );
    }

    /**
     * Handle 404 errors for AJAX requests
     * @param {string} url 
     */
    handleNotFoundError(url) {
        this.showNotification(
            'The requested resource was not found. Please check the URL or contact support.',
            'error'
        );
        console.warn(`404 error for URL: ${url}`);
    }

    /**
     * Handle server errors (500+)
     */
    handleServerError() {
        this.showNotification(
            'Server error occurred. Please try again in a moment.',
            'error'
        );
    }

    /**
     * Handle network connectivity errors
     */
    handleNetworkError() {
        if (navigator.onLine === false) {
            this.showNotification(
                'No internet connection. Please check your network.',
                'warning'
            );
        } else {
            this.showNotification(
                'Network error occurred. Retrying...',
                'warning'
            );
        }
    }

    /**
     * Handle network restoration
     */
    handleNetworkRestore() {
        this.showNotification(
            'Internet connection restored.',
            'success'
        );
    }

    /**
     * Handle network loss
     */
    handleNetworkLoss() {
        this.showNotification(
            'Internet connection lost. Some features may not work.',
            'warning'
        );
    }

    /**
     * Log error information
     * @param {Object} errorInfo 
     */
    logError(errorInfo) {
        this.errors.push(errorInfo);
        
        // Keep only last 50 errors
        if (this.errors.length > 50) {
            this.errors = this.errors.slice(-50);
        }

        console.error('LMS Error:', errorInfo);

        // Send to server if endpoint is available (optional)
        this.sendErrorToServer(errorInfo);
    }

    /**
     * Send error to server for logging
     * @param {Object} errorInfo 
     */
    async sendErrorToServer(errorInfo) {
        try {
            // Only send critical errors to avoid spam
            if (errorInfo.type === 'javascript' && 
                !errorInfo.message.includes('Script error') &&
                !errorInfo.message.includes('Non-Error promise rejection')) {
                
                const response = await fetch('/api/log-client-error/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify(errorInfo)
                });

                // Don't log if the logging endpoint fails
                if (!response.ok) {
                    console.warn('Failed to log error to server');
                }
            }
        } catch (e) {
            // Silently fail if we can't log to server
            console.warn('Error logging failed:', e.message);
        }
    }

    /**
     * Show user notification
     * @param {string} message 
     * @param {string} type 
     * @param {Function} action 
     */
    showNotification(message, type = 'info', action = null) {
        // Check if notifications are enabled
        if (!this.enableNotifications) {
            return;
        }
        
        // Clear previous notification timeout
        if (this.notificationTimeout) {
            clearTimeout(this.notificationTimeout);
        }

        // Remove existing notification
        if (this.lastNotification) {
            this.lastNotification.remove();
        }

        // Create new notification
        const notification = document.createElement('div');
        notification.className = `lms-notification lms-notification-${type}`;
        notification.innerHTML = `
            <div class="lms-notification-content">
                <span class="lms-notification-message">${message}</span>
                <button class="lms-notification-close" onclick="this.parentElement.parentElement.remove()">&times;</button>
            </div>
        `;

        // Add styles
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            max-width: 400px;
            padding: 16px;
            border-radius: 8px;
            color: white;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 14px;
            line-height: 1.4;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            z-index: 10000;
            animation: slideIn 0.3s ease-out;
        `;

        // Set background color based on type
        const colors = {
            info: '#3b82f6',
            success: '#10b981',
            warning: '#f59e0b',
            error: '#ef4444'
        };
        notification.style.backgroundColor = colors[type] || colors.info;

        // Add animation styles
        if (!document.querySelector('#lms-notification-styles')) {
            const styles = document.createElement('style');
            styles.id = 'lms-notification-styles';
            styles.textContent = `
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                .lms-notification-content {
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                }
                .lms-notification-close {
                    background: none;
                    border: none;
                    color: white;
                    cursor: pointer;
                    font-size: 20px;
                    line-height: 1;
                    margin-left: 12px;
                    padding: 0;
                }
                .lms-notification-close:hover {
                    opacity: 0.8;
                }
            `;
            document.head.appendChild(styles);
        }

        document.body.appendChild(notification);
        this.lastNotification = notification;

        // Execute action if provided
        if (action && typeof action === 'function') {
            setTimeout(action, 1000);
        }

        // Auto-remove after delay
        this.notificationTimeout = setTimeout(() => {
            if (notification.parentElement) {
                notification.style.animation = 'slideOut 0.3s ease-in forwards';
                notification.addEventListener('animationend', () => {
                    if (notification.parentElement) {
                        notification.remove();
                    }
                });
            }
        }, type === 'error' ? 8000 : 5000);
    }

    /**
     * Enhanced fetch with retry mechanism
     * @param {string} url 
     * @param {Object} options 
     * @param {number} retryCount 
     * @returns {Promise<Response>}
     */
    async safeFetch(url, options = {}, retryCount = 0) {
        try {
            // Add CSRF token if available
            if (window.csrfManager) {
                options = window.csrfManager.prepareFetchOptions(options);
            }

            const response = await fetch(url, options);

            // Handle specific error cases
            if (!response.ok) {
                if (response.status === 403 && retryCount < this.maxRetries) {
                    // CSRF error - refresh token and retry
                    if (window.csrfManager) {
                        window.csrfManager.refresh();
                        await new Promise(resolve => setTimeout(resolve, this.retryDelay));
                        return this.safeFetch(url, options, retryCount + 1);
                    }
                } else if (response.status >= 500 && retryCount < this.maxRetries) {
                    // Server error - retry with backoff
                    const delay = this.retryDelay * Math.pow(2, retryCount);
                    await new Promise(resolve => setTimeout(resolve, delay));
                    return this.safeFetch(url, options, retryCount + 1);
                }
            }

            return response;
        } catch (error) {
            if (retryCount < this.maxRetries) {
                const delay = this.retryDelay * Math.pow(2, retryCount);
                await new Promise(resolve => setTimeout(resolve, delay));
                return this.safeFetch(url, options, retryCount + 1);
            }
            throw error;
        }
    }

    /**
     * Get error statistics
     * @returns {Object}
     */
    getErrorStats() {
        const stats = {
            total: this.errors.length,
            byType: {},
            recent: this.errors.slice(-10)
        };

        this.errors.forEach(error => {
            stats.byType[error.type] = (stats.byType[error.type] || 0) + 1;
        });

        return stats;
    }

    /**
     * Clear error history
     */
    clearErrors() {
        this.errors = [];
    }
}

// Create global instance
window.globalErrorHandler = new GlobalErrorHandler();

// Export safe fetch function
window.safeFetch = (url, options) => window.globalErrorHandler.safeFetch(url, options);

// Add notification styles
const notificationStyles = `
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;

if (!document.querySelector('#lms-notification-animations')) {
    const styles = document.createElement('style');
    styles.id = 'lms-notification-animations';
    styles.textContent = notificationStyles;
    document.head.appendChild(styles);
}
