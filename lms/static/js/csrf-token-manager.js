/**
 * Centralized CSRF Token Management System
 * Provides consistent CSRF token handling across all AJAX requests
 */

class CSRFTokenManager {
    constructor() {
        this.token = null;
        this.tokenElement = null;
        this.init();
    }

    /**
     * Initialize CSRF token manager
     */
    init() {
        this.tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
        this.token = this.tokenElement ? this.tokenElement.value : null;
        
        // Also check meta tag
        if (!this.token) {
            const metaToken = document.querySelector('meta[name=csrf-token]');
            this.token = metaToken ? metaToken.getAttribute('content') : null;
        }

        // Fallback to cookie
        if (!this.token) {
            this.token = this.getCookie('csrftoken');
        }

        if (!this.token) {
            console.warn('CSRF token not found. Some requests may fail.');
        }
    }

    /**
     * Get current CSRF token
     * @returns {string|null} CSRF token or null if not found
     */
    getToken() {
        return this.token;
    }

    /**
     * Refresh CSRF token from server
     * @returns {Promise<string>} New CSRF token
     */
    async refreshToken() {
        try {
            const response = await fetch('/api/csrf/refresh/', {
                method: 'GET',
                credentials: 'same-origin'
            });
            
            if (response.ok) {
                const data = await response.json();
                this.token = data.csrf_token;
                
                // Update token element if it exists
                if (this.tokenElement) {
                    this.tokenElement.value = this.token;
                }
                
                return this.token;
            } else {
                throw new Error('Failed to refresh CSRF token');
            }
        } catch (error) {
            console.error('Error refreshing CSRF token:', error);
            throw error;
        }
    }

    /**
     * Get cookie value by name
     * @param {string} name - Cookie name
     * @returns {string|null} Cookie value or null
     */
    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    }

    /**
     * Add CSRF token to request headers
     * @param {Object} headers - Request headers object
     * @returns {Object} Headers with CSRF token added
     */
    addTokenToHeaders(headers = {}) {
        if (this.token) {
            headers['X-CSRFToken'] = this.token;
        }
        return headers;
    }

    /**
     * Add CSRF token to form data
     * @param {FormData} formData - Form data object
     * @returns {FormData} Form data with CSRF token added
     */
    addTokenToFormData(formData) {
        if (this.token) {
            formData.append('csrfmiddlewaretoken', this.token);
        }
        return formData;
    }

    /**
     * Add CSRF token to JSON data
     * @param {Object} data - JSON data object
     * @returns {Object} Data with CSRF token added
     */
    addTokenToData(data = {}) {
        if (this.token) {
            data.csrfmiddlewaretoken = this.token;
        }
        return data;
    }

    /**
     * Validate CSRF token
     * @returns {Promise<boolean>} True if token is valid
     */
    async validateToken() {
        if (!this.token) {
            return false;
        }

        try {
            const response = await fetch('/api/csrf/validate/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.token
                },
                credentials: 'same-origin'
            });
            
            return response.ok;
        } catch (error) {
            console.error('Error validating CSRF token:', error);
            return false;
        }
    }
}

// Global instance
window.CSRFManager = new CSRFTokenManager();

/**
 * Enhanced fetch function with automatic CSRF token handling
 * @param {string} url - Request URL
 * @param {Object} options - Fetch options
 * @returns {Promise<Response>} Fetch response
 */
window.csrfFetch = async function(url, options = {}) {
    // Add CSRF token to headers for state-changing requests
    if (options.method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(options.method.toUpperCase())) {
        options.headers = options.headers || {};
        options.headers = window.CSRFManager.addTokenToHeaders(options.headers);
    }

    // Add credentials for same-origin requests
    if (!options.credentials) {
        options.credentials = 'same-origin';
    }

    try {
        const response = await fetch(url, options);
        
        // Handle CSRF errors
        if (response.status === 403 && response.headers.get('content-type')?.includes('application/json')) {
            const errorData = await response.json();
            if (errorData.error_type === 'csrf_error') {
                console.warn('CSRF token expired, attempting to refresh...');
                try {
                    await window.CSRFManager.refreshToken();
                    // Retry the request with new token
                    if (options.method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(options.method.toUpperCase())) {
                        options.headers = window.CSRFManager.addTokenToHeaders(options.headers);
                    }
                    return await fetch(url, options);
                } catch (refreshError) {
                    console.error('Failed to refresh CSRF token:', refreshError);
                    throw new Error('Session expired. Please refresh the page.');
                }
            }
        }
        
        return response;
    } catch (error) {
        console.error('Fetch error:', error);
        throw error;
    }
};

/**
 * Enhanced XMLHttpRequest with automatic CSRF token handling
 */
window.csrfXHR = function() {
    const xhr = new XMLHttpRequest();
    const originalOpen = xhr.open;
    const originalSend = xhr.send;
    
    xhr.open = function(method, url, async, user, password) {
        this._method = method;
        this._url = url;
        return originalOpen.call(this, method, url, async, user, password);
    };
    
    xhr.send = function(data) {
        // Add CSRF token for state-changing requests
        if (this._method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(this._method.toUpperCase())) {
            this.setRequestHeader('X-CSRFToken', window.CSRFManager.getToken() || '');
        }
        return originalSend.call(this, data);
    };
    
    return xhr;
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CSRFTokenManager;
}