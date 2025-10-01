/**
 * Enhanced Error Boundary System for LMS
 * Provides comprehensive error handling and recovery mechanisms
 */

(function() {
    'use strict';

    const ErrorBoundary = {
        // Error tracking
        errors: [],
        maxErrors: 50,
        
        // Recovery strategies
        recoveryStrategies: {
            'TinyMCE': this.recoverTinyMCE,
            'Chart': this.recoverCharts,
            'Network': this.recoverNetwork,
            'DOM': this.recoverDOM
        },

        // Initialize error boundary
        init: function() {
            this.setupGlobalErrorHandling();
            this.setupUnhandledRejectionHandling();
            this.setupResourceErrorHandling();
            this.setupRecoveryMechanisms();
            
            console.log('Enhanced Error Boundary initialized');
        },

        // Setup global error handling
        setupGlobalErrorHandling: function() {
            window.addEventListener('error', (event) => {
                this.handleError({
                    type: 'JavaScript Error',
                    message: event.message,
                    filename: event.filename,
                    lineno: event.lineno,
                    colno: event.colno,
                    error: event.error,
                    stack: event.error?.stack
                });
            });
        },

        // Setup unhandled promise rejection handling
        setupUnhandledRejectionHandling: function() {
            window.addEventListener('unhandledrejection', (event) => {
                this.handleError({
                    type: 'Unhandled Promise Rejection',
                    message: event.reason?.message || 'Unknown promise rejection',
                    error: event.reason,
                    stack: event.reason?.stack
                });
            });
        },

        // Setup resource error handling
        setupResourceErrorHandling: function() {
            window.addEventListener('error', (event) => {
                if (event.target !== window) {
                    this.handleError({
                        type: 'Resource Error',
                        message: `Failed to load resource: ${event.target.src || event.target.href}`,
                        filename: event.target.src || event.target.href,
                        tagName: event.target.tagName
                    });
                }
            }, true);
        },

        // Handle errors with categorization and recovery
        handleError: function(errorInfo) {
            // Categorize error
            const category = this.categorizeError(errorInfo);
            
            // Store error
            this.storeError(errorInfo, category);
            
            // Attempt recovery
            this.attemptRecovery(errorInfo, category);
            
            // Log error (but don't show to user unless critical)
            this.logError(errorInfo, category);
        },

        // Categorize errors for appropriate handling
        categorizeError: function(errorInfo) {
            const message = errorInfo.message.toLowerCase();
            const filename = errorInfo.filename || '';
            
            if (message.includes('tinymce') || filename.includes('tinymce')) {
                return 'TinyMCE';
            }
            if (message.includes('chart') || filename.includes('chart')) {
                return 'Chart';
            }
            if (message.includes('network') || message.includes('fetch') || message.includes('xhr')) {
                return 'Network';
            }
            if (message.includes('dom') || message.includes('element')) {
                return 'DOM';
            }
            
            return 'General';
        },

        // Store error with limits
        storeError: function(errorInfo, category) {
            this.errors.push({
                ...errorInfo,
                category,
                timestamp: new Date().toISOString(),
                userAgent: navigator.userAgent,
                url: window.location.href
            });
            
            // Keep only recent errors
            if (this.errors.length > this.maxErrors) {
                this.errors = this.errors.slice(-this.maxErrors);
            }
        },

        // Attempt recovery based on error category
        attemptRecovery: function(errorInfo, category) {
            const strategy = this.recoveryStrategies[category];
            if (strategy && typeof strategy === 'function') {
                try {
                    strategy.call(this, errorInfo);
                } catch (recoveryError) {
                    console.warn('Recovery attempt failed:', recoveryError);
                }
            }
        },

        // TinyMCE recovery strategy
        recoverTinyMCE: function(errorInfo) {
            console.log('Attempting TinyMCE recovery...');
            
            // Wait for DOM to be ready
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => {
                    this.recoverTinyMCE(errorInfo);
                });
                return;
            }
            
            // Check if TinyMCE is available
            if (typeof tinymce === 'undefined') {
                console.log('TinyMCE not available, skipping recovery');
                return;
            }
            
            // Try to reinitialize broken editors
            const editors = tinymce.get();
            editors.forEach(editor => {
                if (!editor.getContainer() || !editor.getBody()) {
                    console.log('Recovering TinyMCE editor:', editor.id);
                    try {
                        editor.remove();
                        // Reinitialize with minimal config
                        tinymce.init({
                            selector: '#' + editor.id,
                            height: 300,
                            menubar: false,
                            plugins: 'lists link code',
                            toolbar: 'bold italic underline | bullist numlist | link code',
                            branding: false,
                            promotion: false,
                            statusbar: false
                        });
                    } catch (e) {
                        console.warn('Failed to recover TinyMCE editor:', e);
                    }
                }
            });
        },

        // Chart recovery strategy
        recoverCharts: function(errorInfo) {
            console.log('Attempting chart recovery...');
            
            // Wait for chart services to be available
            setTimeout(() => {
                if (typeof window.chartInitializer !== 'undefined') {
                    try {
                        window.chartInitializer.initializeCharts();
                    } catch (e) {
                        console.warn('Chart recovery failed:', e);
                    }
                }
            }, 1000);
        },

        // Network recovery strategy
        recoverNetwork: function(errorInfo) {
            console.log('Attempting network recovery...');
            
            // Retry failed requests after a delay
            setTimeout(() => {
                // Trigger a page refresh for critical network failures
                if (errorInfo.message.includes('critical') || errorInfo.message.includes('auth')) {
                    console.log('Critical network error detected, considering page refresh');
                    // Only refresh if multiple network errors occur
                    const networkErrors = this.errors.filter(e => e.category === 'Network');
                    if (networkErrors.length > 3) {
                        console.log('Multiple network errors, refreshing page...');
                        window.location.reload();
                    }
                }
            }, 2000);
        },

        // DOM recovery strategy
        recoverDOM: function(errorInfo) {
            console.log('Attempting DOM recovery...');
            
            // Try to reinitialize critical DOM elements
            const criticalElements = ['#sidebar', '#main-content', 'header'];
            criticalElements.forEach(selector => {
                const element = document.querySelector(selector);
                if (!element) {
                    console.log('Critical DOM element missing:', selector);
                    // Could trigger a page refresh for critical DOM issues
                }
            });
        },

        // Log error with appropriate level
        logError: function(errorInfo, category) {
            const isCritical = this.isCriticalError(errorInfo, category);
            
            if (isCritical) {
                console.error('Critical Error:', errorInfo);
                // Could show user notification for critical errors
                this.showUserNotification('A critical error occurred. Please refresh the page.', 'error');
            } else {
                console.warn('Non-critical Error:', errorInfo);
            }
        },

        // Determine if error is critical
        isCriticalError: function(errorInfo, category) {
            // Critical errors that should be shown to users
            const criticalPatterns = [
                'authentication',
                'authorization',
                'session',
                'critical',
                'fatal'
            ];
            
            const message = errorInfo.message.toLowerCase();
            return criticalPatterns.some(pattern => message.includes(pattern));
        },

        // Show user notification for critical errors
        showUserNotification: function(message, type) {
            // Check if notification system is available
            if (typeof window.showToast === 'function') {
                window.showToast(message, type);
            } else {
                // Fallback notification
                const notification = document.createElement('div');
                notification.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 ${
                    type === 'error' ? 'bg-red-100 text-red-800' : 'bg-blue-100 text-blue-800'
                }`;
                notification.textContent = message;
                document.body.appendChild(notification);
                
                setTimeout(() => {
                    notification.remove();
                }, 5000);
            }
        },

        // Setup recovery mechanisms
        setupRecoveryMechanisms: function() {
            // Periodic health check
            setInterval(() => {
                this.performHealthCheck();
            }, 30000); // Every 30 seconds
            
            // Memory cleanup
            setInterval(() => {
                this.cleanupMemory();
            }, 300000); // Every 5 minutes
        },

        // Perform health check
        performHealthCheck: function() {
            const recentErrors = this.errors.filter(error => {
                const errorTime = new Date(error.timestamp);
                const now = new Date();
                return (now - errorTime) < 60000; // Last minute
            });
            
            if (recentErrors.length > 10) {
                console.warn('High error rate detected:', recentErrors.length, 'errors in the last minute');
                // Could implement circuit breaker pattern here
            }
        },

        // Cleanup memory
        cleanupMemory: function() {
            // Remove old errors
            this.errors = this.errors.slice(-this.maxErrors);
            
            // Force garbage collection if available
            if (window.gc) {
                window.gc();
            }
        },

        // Get error statistics
        getErrorStats: function() {
            const stats = {
                total: this.errors.length,
                byCategory: {},
                recent: this.errors.filter(error => {
                    const errorTime = new Date(error.timestamp);
                    const now = new Date();
                    return (now - errorTime) < 300000; // Last 5 minutes
                }).length
            };
            
            this.errors.forEach(error => {
                stats.byCategory[error.category] = (stats.byCategory[error.category] || 0) + 1;
            });
            
            return stats;
        },

        // Clear errors
        clearErrors: function() {
            this.errors = [];
            console.log('Error history cleared');
        }
    };

    // Initialize error boundary
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            ErrorBoundary.init();
        });
    } else {
        ErrorBoundary.init();
    }

    // Make available globally
    window.ErrorBoundary = ErrorBoundary;

    console.log('Enhanced Error Boundary system loaded');
})();
