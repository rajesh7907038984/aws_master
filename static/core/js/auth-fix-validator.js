/**
 * Authentication Fix Validator for LMS
 * 
 * This file provides authentication validation utilities to prevent
 * common authentication issues and improve user experience.
 */

/**
 * Validate authentication state and handle common issues
 */
class AuthFixValidator {
    constructor() {
        this.isValidating = false;
        this.retryCount = 0;
        this.maxRetries = 3;
        this.init();
    }

    init() {
        // Check authentication state on page load
        this.validateAuthState();
        
        // Set up periodic validation
        setInterval(() => {
            this.validateAuthState();
        }, 30000); // Check every 30 seconds
        
        // Listen for authentication events
        this.setupEventListeners();
    }

    validateAuthState() {
        if (this.isValidating) return;
        
        this.isValidating = true;
        
        try {
            // Check if user is authenticated
            const authElements = document.querySelectorAll('[data-auth-required]');
            const isAuthenticated = this.checkAuthenticationStatus();
            
            if (!isAuthenticated && authElements.length > 0) {
                this.handleAuthFailure();
            } else {
                this.handleAuthSuccess();
            }
        } catch (error) {
            console.error('Auth validation error:', error);
            this.handleAuthError(error);
        } finally {
            this.isValidating = false;
        }
    }

    checkAuthenticationStatus() {
        // Check for authentication indicators
        const authToken = this.getAuthToken();
        const userSession = this.getUserSession();
        const csrfToken = this.getCSRFToken();
        
        return !!(authToken || userSession || csrfToken);
    }

    getAuthToken() {
        // Check localStorage for auth token
        const token = localStorage.getItem('auth_token');
        if (token) {
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                const now = Math.floor(Date.now() / 1000);
                return payload.exp > now ? token : null;
            } catch (error) {
                console.warn('Invalid auth token format');
                return null;
            }
        }
        return null;
    }

    getUserSession() {
        // Check for user session indicators
        const userElements = document.querySelectorAll('[data-user-id]');
        const sessionElements = document.querySelectorAll('[data-session-id]');
        
        return userElements.length > 0 || sessionElements.length > 0;
    }

    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        if (token) {
            return token.value;
        }
        
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        if (metaToken) {
            return metaToken.getAttribute('content');
        }
        
        return null;
    }

    handleAuthFailure() {
        console.warn('Authentication validation failed');
        
        // Show user-friendly message
        if (window.showNotification) {
            window.showNotification('Your session has expired. Please log in again.', 'warning', 8000);
        }
        
        // Redirect to login after a delay
        setTimeout(() => {
            window.location.href = '/login/';
        }, 2000);
    }

    handleAuthSuccess() {
        // Reset retry count on successful validation
        this.retryCount = 0;
    }

    handleAuthError(error) {
        console.error('Authentication validation error:', error);
        
        this.retryCount++;
        
        if (this.retryCount >= this.maxRetries) {
            console.error('Max authentication validation retries reached');
            
            if (window.showNotification) {
                window.showNotification('Authentication validation failed. Please refresh the page.', 'error', 10000);
            }
        }
    }

    setupEventListeners() {
        // Listen for authentication-related events
        document.addEventListener('auth:login', () => {
            this.validateAuthState();
        });
        
        document.addEventListener('auth:logout', () => {
            this.clearAuthData();
        });
        
        // Listen for network errors that might indicate auth issues
        window.addEventListener('error', (event) => {
            if (event.message && event.message.includes('401')) {
                this.handleAuthFailure();
            }
        });
    }

    clearAuthData() {
        // Clear authentication data
        localStorage.removeItem('auth_token');
        sessionStorage.clear();
        
        // Clear any cached user data
        const userDataElements = document.querySelectorAll('[data-user-cache]');
        userDataElements.forEach(element => {
            element.removeAttribute('data-user-cache');
        });
    }

    /**
     * Validate form authentication before submission
     * @param {HTMLFormElement} form - The form to validate
     * @returns {boolean} - Whether the form is valid for submission
     */
    validateFormAuth(form) {
        if (!form) return false;
        
        const csrfToken = this.getCSRFToken();
        if (!csrfToken) {
            console.error('CSRF token not found');
            if (window.showNotification) {
                window.showNotification('Security token missing. Please refresh the page.', 'error');
            }
            return false;
        }
        
        // Ensure CSRF token is in the form
        let csrfInput = form.querySelector('[name=csrfmiddlewaretoken]');
        if (!csrfInput) {
            csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = csrfToken;
            form.appendChild(csrfInput);
        } else {
            csrfInput.value = csrfToken;
        }
        
        return true;
    }

    /**
     * Validate API request authentication
     * @param {string} url - The API URL
     * @param {Object} options - Request options
     * @returns {Object} - Enhanced options with auth headers
     */
    validateApiAuth(url, options = {}) {
        const csrfToken = this.getCSRFToken();
        const authToken = this.getAuthToken();
        
        const headers = {
            'X-Requested-With': 'XMLHttpRequest',
            ...options.headers
        };
        
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }
        
        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }
        
        return {
            ...options,
            headers
        };
    }
}

// Create global instance
const authFixValidator = new AuthFixValidator();

// Global functions for backward compatibility
function validateAuth() {
    return authFixValidator.validateAuthState();
}

function validateFormAuth(form) {
    return authFixValidator.validateFormAuth(form);
}

function validateApiAuth(url, options) {
    return authFixValidator.validateApiAuth(url, options);
}

// Expose to global scope
window.authFixValidator = authFixValidator;
window.validateAuth = validateAuth;
window.validateFormAuth = validateFormAuth;
window.validateApiAuth = validateApiAuth;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        AuthFixValidator,
        validateAuth,
        validateFormAuth,
        validateApiAuth
    };
}
