/**
 * Unified Error Handler for 100% Frontend-Backend Alignment
 * This system ensures consistent error handling across the entire LMS
 */

class UnifiedErrorHandler {
    constructor() {
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
        
        this.setupGlobalErrorHandling();
    }
    
    /**
     * Setup global error handling
     */
    setupGlobalErrorHandling() {
        // Handle unhandled promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            this.handleError(event.reason, 'Unhandled Promise Rejection');
            event.preventDefault();
        });
        
        // Handle global JavaScript errors
        window.addEventListener('error', (event) => {
            this.handleError(event.error, 'Global JavaScript Error');
        });
        
        // Handle fetch errors
        this.interceptFetch();
    }
    
    /**
     * Intercept fetch requests for error handling
     */
    interceptFetch() {
        const originalFetch = window.fetch;
        const self = this;
        
        window.fetch = async function(...args) {
            try {
                const response = await originalFetch.apply(this, args);
                
                // Check for HTTP errors
                if (!response.ok) {
                    const error = new Error(`HTTP ${response.status}: ${response.statusText}`);
                    error.status = response.status;
                    error.response = response;
                    throw error;
                }
                
                return response;
            } catch (error) {
                self.handleError(error, 'Fetch Request');
                throw error;
            }
        };
    }
    
    /**
     * Handle errors with unified approach
     */
    handleError(error, context = 'Unknown') {
        // Create error key for cooldown check
        const errorKey = `${context}-${error.message || error.name}`;
        const now = Date.now();
        const lastError = this.errorCooldown.get(errorKey);
        
        // Skip if same error occurred within last 5 seconds
        if (lastError && (now - lastError) < 5000) {
            return;
        }
        
        // Update cooldown
        this.errorCooldown.set(errorKey, now);
        
        console.error(`[${context}] Error:`, error);
        
        // Categorize error
        const category = this.categorizeError(error);
        
        // Get user-friendly message
        const message = this.getUserFriendlyMessage(error, category);
        
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
     * Show user notification - Console logging only, no browser popups
     */
    showUserNotification(message, category) {
        // Only log to console - no browser popups or notifications
        console.warn(`[${category}] ${message}`);
    }
    
    /**
     * Get notification type based on error category
     */
    getNotificationType(category) {
        const typeMap = {
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
        const errorDetails = {
            context: context,
            category: category,
            name: error.name || 'Unknown',
            message: error.message || 'No message',
            stack: error.stack || 'No stack trace',
            timestamp: new Date().toISOString(),
            url: window.location.href,
            userAgent: navigator.userAgent
        };
        
        // Store in localStorage for debugging
        try {
            const recentErrors = JSON.parse(localStorage.getItem('lms_recent_errors') || '[]');
            recentErrors.push(errorDetails);
            
            // Keep only last 20 errors
            if (recentErrors.length > 20) {
                recentErrors.shift();
            }
            
            localStorage.setItem('lms_recent_errors', JSON.stringify(recentErrors));
        } catch (e) {
            console.warn('Failed to store error in localStorage:', e);
        }
        
        // Log to console with details
        console.group(`🚨 ${category} Error in ${context}`);
        console.error('Error Details:', errorDetails);
        console.error('Original Error:', error);
        console.groupEnd();
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
            case 'VALIDATION':
                this.handleValidationError(error);
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
     * Handle validation errors
     */
    handleValidationError(error) {
        // Focus on first form field with error
        if (error instanceof StandardizedAPIError && error.errors) {
            const firstField = Object.keys(error.errors)[0];
            if (firstField && firstField !== 'non_field_errors') {
                const fieldElement = document.querySelector(`[name="${firstField}"]`);
                if (fieldElement) {
                    fieldElement.focus();
                    fieldElement.classList.add('error');
                }
            }
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
        localStorage.removeItem('lms_recent_errors');
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
            const fieldElement = document.querySelector(`[name="${field}"]`);
            if (fieldElement) {
                fieldElement.classList.add('error');
                
                // Show field-specific error message
                const errorMessage = Array.isArray(errors[field]) ? errors[field][0] : errors[field];
                this.showFieldError(fieldElement, errorMessage);
            }
        });
    }
    
    /**
     * Show field-specific error message
     */
    showFieldError(fieldElement, message) {
        // Remove existing error message
        const existingError = fieldElement.parentNode.querySelector('.field-error');
        if (existingError) {
            existingError.remove();
        }
        
        // Add new error message
        const errorDiv = document.createElement('div');
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
    console.log('✅ Unified Error Handler initialized');
});
