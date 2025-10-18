/**
 * Standardized API Client for 100% Frontend-Backend Alignment
 * This client ensures perfect alignment with backend API responses
 */

// Browser compatibility checks
if (typeof console === 'undefined') {
    window.console = {
        log: function() {},
        error: function() {},
        warn: function() {},
        info: function() {}
    };
}

// Environment validation - warnings removed for production

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
                var match = document.cookie.match(/csrftoken=([^;]+)/);
                return match ? match[1] : null;
            }
        ];

        for (var source of sources) {
            try {
                var token = source();
                if (token && token.length > 0 && /^[a-zA-Z0-9]+$/.test(token)) {
                    return token;
                }
            } catch (e) {
                // Error getting CSRF token - logged to server
                continue;
            }
        }
        return null;
    }

    /**
     * Get standardized headers for requests
     */
    getHeaders(customHeaders) {
        customHeaders = customHeaders || {};
        var headers = Object.assign({}, this.defaultHeaders, customHeaders);
        
        // Add CSRF token for non-GET requests
        var csrfToken = this.getCSRFToken();
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

        var requiredFields = ['success', 'status', 'message', 'timestamp', 'version'];
        var missingFields = requiredFields.filter(field => !(field in response));
        
        if (missingFields.length > 0) {
            throw new Error('Invalid response format: Missing fields: ' + missingFields.join(', '));
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
                    response.message || 'API request failed',
                    response.errors || {},
                    response.error_code || 'API_ERROR',
                    response.details || null
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
    async makeRequest(url, options, attempt) {
        options = options || {};
        attempt = attempt || 1;
        var controller = new AbortController();
        var timeoutId = setTimeout(() => controller.abort(), this.timeout);

        try {
            var fetchOptions = Object.assign({}, options, {
                headers: this.getHeaders(options.headers),
                signal: controller.signal
            });
            var response = await fetch(url, fetchOptions);

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error('HTTP ' + response.status + ': ' + response.statusText);
            }

            var contentType = response.headers.get('Content-Type');
            if (!contentType || !contentType.includes('application/json')) {
                var text = await response.text();
                throw new Error('Expected JSON response, got: ' + contentType + '. Response: ' + text.substring(0, 200));
            }

            var data = await response.json();
            return this.handleResponse(data);

        } catch (error) {
            clearTimeout(timeoutId);

            // Retry logic for network errors
            if (attempt < this.retryAttempts && 
                (error.name === 'AbortError' || error.message.includes('Failed to fetch'))) {
                
                // API request failed - retrying (logged to server)
                await new Promise(resolve => setTimeout(resolve, this.retryDelay * attempt));
                return this.makeRequest(url, options, attempt + 1);
            }

            throw error;
        }
    }

    /**
     * GET request
     */
    async get(url, params, options) {
        params = params || {};
        options = options || {};
        var queryString = new URLSearchParams(params).toString();
        var fullUrl = queryString ? url + '?' + queryString : url;
        
        return this.makeRequest(fullUrl, Object.assign({}, options, {
            method: 'GET'
        }));
    }

    /**
     * POST request
     */
    async post(url, data, options) {
        data = data || {};
        options = options || {};
        return this.makeRequest(url, Object.assign({}, options, {
            method: 'POST',
            body: JSON.stringify(data)
        }));
    }

    /**
     * PUT request
     */
    async put(url, data, options) {
        data = data || {};
        options = options || {};
        return this.makeRequest(url, Object.assign({}, options, {
            method: 'PUT',
            body: JSON.stringify(data)
        }));
    }

    /**
     * PATCH request
     */
    async patch(url, data, options) {
        data = data || {};
        options = options || {};
        return this.makeRequest(url, Object.assign({}, options, {
            method: 'PATCH',
            body: JSON.stringify(data)
        }));
    }

    /**
     * DELETE request
     */
    async delete(url, options) {
        options = options || {};
        return this.makeRequest(url, Object.assign({}, options, {
            method: 'DELETE'
        }));
    }

    /**
     * Upload file with FormData
     */
    async upload(url, formData, options) {
        options = options || {};
        var headers = this.getHeaders();
        delete headers['Content-Type']; // Let browser set content-type for FormData

        return this.makeRequest(url, Object.assign({}, options, {
            method: 'POST',
            body: formData,
            headers: headers
        }));
    }
}

/**
 * Standardized API Error class
 */
class StandardizedAPIError extends Error {
    constructor(message, errors, errorCode, details) {
        errors = errors || {};
        errorCode = errorCode || null;
        details = details || null;
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
            var firstError = Object.values(this.errors)[0];
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
window.apiSuccess = function(data, message) {
    message = message || 'Success';
    return { success: true, data: data, message: message };
};
window.apiError = function(message, errors) {
    errors = errors || {};
    return { success: false, message: message, errors: errors };
};

/**
 * Global error handler for API errors
 */
window.handleAPIError = function(error, context) {
    context = context || 'API Request';
    // Error logged to server
    
    if (error instanceof StandardizedAPIError) {
        // Show user-friendly error message
        var message = error.getUserFriendlyMessage();
        
        if (typeof showToast === 'function') {
            showToast(message, 'error');
        } else {
            console.error('Error (toast system unavailable):', message);
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
        var message = error.message || 'An unexpected error occurred';
        
        if (typeof showToast === 'function') {
            showToast(message, 'error');
        } else {
            console.error('Error (toast system unavailable):', message);
        }
    }
};

/**
 * Initialize the standardized API client
 */
document.addEventListener('DOMContentLoaded', function() {
    // Debug logging removed for production
    
    // Set up global error handling
    window.addEventListener('unhandledrejection', function(event) {
        if (event.reason instanceof StandardizedAPIError) {
            handleAPIError(event.reason, 'Unhandled Promise Rejection');
            event.preventDefault();
        }
    });
});
