/**
 * Standardized API Client for 100% Frontend-Backend Alignment
 * This client ensures perfect alignment with backend API responses
 */

class StandardizedAPIClient {
    constructor() {
        this.baseURL = '';
        this.defaultHeaders = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        };
        this.timeout = 30000; // 30 seconds
        this.retryAttempts = 3;
        this.retryDelay = 1000; // 1 second
    }

    /**
     * Get CSRF token from multiple sources
     */
    getCSRFToken() {
        const sources = [
            () => document.querySelector('meta[name="csrf-token"]')?.getAttribute('content'),
            () => document.querySelector('input[name="csrfmiddlewaretoken"]')?.value,
            () => window.CSRF_TOKEN,
            () => document.cookie.match(/csrftoken=([^;]+)/)?.[1]
        ];

        for (let source of sources) {
            try {
                const token = source();
                if (token && token.length > 0 && /^[a-zA-Z0-9]+$/.test(token)) {
                    return token;
                }
            } catch (e) {
                continue;
            }
        }
        return null;
    }

    /**
     * Get standardized headers for requests
     */
    getHeaders(customHeaders = {}) {
        const headers = { ...this.defaultHeaders, ...customHeaders };
        
        // Add CSRF token for non-GET requests
        const csrfToken = this.getCSRFToken();
        if (csrfToken) {
            headers['X-CSRFToken'] = csrfToken;
        }
        
        return headers;
    }

    /**
     * Validate API response format
     */
    validateResponse(response) {
        if (!response || typeof response !== 'object') {
            throw new Error('Invalid response format: Response is not an object');
        }

        const requiredFields = ['success', 'status', 'message', 'timestamp', 'version'];
        const missingFields = requiredFields.filter(field => !(field in response));
        
        if (missingFields.length > 0) {
            throw new Error(`Invalid response format: Missing fields: ${missingFields.join(', ')}`);
        }

        if (typeof response.success !== 'boolean') {
            throw new Error('Invalid response format: success field must be boolean');
        }

        if (!['success', 'error'].includes(response.status)) {
            throw new Error('Invalid response format: status must be "success" or "error"');
        }

        return true;
    }

    /**
     * Handle API response with standardized format
     */
    handleResponse(response) {
        try {
            this.validateResponse(response);
            
            if (response.success) {
                return {
                    success: true,
                    data: response.data,
                    message: response.message,
                    meta: response.meta || {},
                    timestamp: response.timestamp,
                    version: response.version
                };
            } else {
                throw new StandardizedAPIError(
                    response.message,
                    response.errors || {},
                    response.error_code,
                    response.details
                );
            }
        } catch (error) {
            if (error instanceof StandardizedAPIError) {
                throw error;
            }
            throw new StandardizedAPIError(
                'Invalid API response format',
                { response: 'Response format does not match API specification' },
                'INVALID_RESPONSE_FORMAT'
            );
        }
    }

    /**
     * Make HTTP request with retry logic
     */
    async makeRequest(url, options = {}, attempt = 1) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        try {
            const response = await fetch(url, {
                ...options,
                headers: this.getHeaders(options.headers),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('Content-Type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                throw new Error(`Expected JSON response, got: ${contentType}. Response: ${text.substring(0, 200)}`);
            }

            const data = await response.json();
            return this.handleResponse(data);

        } catch (error) {
            clearTimeout(timeoutId);

            // Retry logic for network errors
            if (attempt < this.retryAttempts && 
                (error.name === 'AbortError' || error.message.includes('Failed to fetch'))) {
                
                console.warn(`API request failed (attempt ${attempt}/${this.retryAttempts}), retrying...`, error.message);
                await new Promise(resolve => setTimeout(resolve, this.retryDelay * attempt));
                return this.makeRequest(url, options, attempt + 1);
            }

            throw error;
        }
    }

    /**
     * GET request
     */
    async get(url, params = {}, options = {}) {
        const queryString = new URLSearchParams(params).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;
        
        return this.makeRequest(fullUrl, {
            method: 'GET',
            ...options
        });
    }

    /**
     * POST request
     */
    async post(url, data = {}, options = {}) {
        return this.makeRequest(url, {
            method: 'POST',
            body: JSON.stringify(data),
            ...options
        });
    }

    /**
     * PUT request
     */
    async put(url, data = {}, options = {}) {
        return this.makeRequest(url, {
            method: 'PUT',
            body: JSON.stringify(data),
            ...options
        });
    }

    /**
     * PATCH request
     */
    async patch(url, data = {}, options = {}) {
        return this.makeRequest(url, {
            method: 'PATCH',
            body: JSON.stringify(data),
            ...options
        });
    }

    /**
     * DELETE request
     */
    async delete(url, options = {}) {
        return this.makeRequest(url, {
            method: 'DELETE',
            ...options
        });
    }

    /**
     * Upload file with FormData
     */
    async upload(url, formData, options = {}) {
        const headers = this.getHeaders();
        delete headers['Content-Type']; // Let browser set content-type for FormData

        return this.makeRequest(url, {
            method: 'POST',
            body: formData,
            headers,
            ...options
        });
    }
}

/**
 * Standardized API Error class
 */
class StandardizedAPIError extends Error {
    constructor(message, errors = {}, errorCode = null, details = null) {
        super(message);
        this.name = 'StandardizedAPIError';
        this.errors = errors;
        this.errorCode = errorCode;
        this.details = details;
        this.timestamp = new Date().toISOString();
    }

    /**
     * Get user-friendly error message
     */
    getUserFriendlyMessage() {
        if (this.errorCode === 'VALIDATION_ERROR' && Object.keys(this.errors).length > 0) {
            const firstError = Object.values(this.errors)[0];
            if (Array.isArray(firstError)) {
                return firstError[0];
            }
            return firstError;
        }
        return this.message;
    }

    /**
     * Get field-specific error
     */
    getFieldError(fieldName) {
        return this.errors[fieldName] || null;
    }

    /**
     * Check if error is validation error
     */
    isValidationError() {
        return this.errorCode === 'VALIDATION_ERROR';
    }

    /**
     * Check if error is authentication error
     */
    isAuthError() {
        return this.errorCode === 'UNAUTHORIZED' || this.errorCode === 'FORBIDDEN';
    }

    /**
     * Check if error is not found error
     */
    isNotFoundError() {
        return this.errorCode === 'NOT_FOUND';
    }
}

/**
 * Global API client instance
 */
window.StandardizedAPIClient = StandardizedAPIClient;
window.StandardizedAPIError = StandardizedAPIError;

// Create global instance
window.api = new StandardizedAPIClient();

/**
 * Convenience functions for common API operations
 */
window.apiSuccess = (data, message = 'Success') => ({ success: true, data, message });
window.apiError = (message, errors = {}) => ({ success: false, message, errors });

/**
 * Global error handler for API errors
 */
window.handleAPIError = function(error, context = 'API Request') {
    console.error(`${context} Error:`, error);
    
    if (error instanceof StandardizedAPIError) {
        // Show user-friendly error message
        const message = error.getUserFriendlyMessage();
        
        if (typeof showToast === 'function') {
            showToast(message, 'error');
        } else {
            alert(message);
        }
        
        // Log detailed error for debugging
        console.error('API Error Details:', {
            message: error.message,
            errors: error.errors,
            errorCode: error.errorCode,
            details: error.details,
            timestamp: error.timestamp
        });
    } else {
        // Handle non-API errors
        const message = error.message || 'An unexpected error occurred';
        
        if (typeof showToast === 'function') {
            showToast(message, 'error');
        } else {
            alert(message);
        }
    }
};

/**
 * Initialize the standardized API client
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ Standardized API Client initialized');
    
    // Set up global error handling
    window.addEventListener('unhandledrejection', function(event) {
        if (event.reason instanceof StandardizedAPIError) {
            handleAPIError(event.reason, 'Unhandled Promise Rejection');
            event.preventDefault();
        }
    });
});
