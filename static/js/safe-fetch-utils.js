/**
 * Safe Fetch Utilities for LMS
 * 
 * This file provides safe fetch utilities to handle JSON responses
 * and prevent the common issues with response.json() calls.
 */

/**
 * Safely parse JSON response with proper error handling
 * @param {Response} response - The fetch response object
 * @returns {Promise<Object>} - Parsed JSON data or error object
 */
async function safeJsonResponse(response) {
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status} - ${response.statusText}`);
    }

    const contentType = response.headers.get('Content-Type');
    
    // Check if response is JSON
    if (!contentType || !contentType.includes('application/json')) {
        // Try to get text response for debugging
        const text = await response.text();
        console.error('Non-JSON response received:', {
            status: response.status,
            statusText: response.statusText,
            contentType: contentType,
            responseText: text.substring(0, 500) // Limit text for logging
        });
        throw new Error('Server returned non-JSON response. Check console for details.');
    }

    try {
        return await response.json();
    } catch (error) {
        console.error('JSON parsing error:', error);
        throw new Error('Failed to parse JSON response from server');
    }
}

/**
 * Safe fetch wrapper that handles common issues
 * @param {string} url - The URL to fetch
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} - Parsed JSON data
 */
async function safeFetch(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                ...options.headers
            }
        });
        
        return await safeJsonResponse(response);
    } catch (error) {
        console.error('Safe fetch error:', error);
        throw error;
    }
}

/**
 * Safe fetch for DELETE requests
 * @param {string} url - The URL to delete
 * @param {Object} options - Additional options
 * @returns {Promise<Object>} - Parsed JSON data
 */
async function safeDelete(url, options = {}) {
    return safeFetch(url, {
        method: 'DELETE',
        ...options
    });
}

/**
 * Safe fetch for POST requests
 * @param {string} url - The URL to post to
 * @param {Object} data - Data to send
 * @param {Object} options - Additional options
 * @returns {Promise<Object>} - Parsed JSON data
 */
async function safePost(url, data, options = {}) {
    return safeFetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        body: JSON.stringify(data),
        ...options
    });
}

/**
 * Safe fetch for PUT requests
 * @param {string} url - The URL to put to
 * @param {Object} data - Data to send
 * @param {Object} options - Additional options
 * @returns {Promise<Object>} - Parsed JSON data
 */
async function safePut(url, data, options = {}) {
    return safeFetch(url, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        body: JSON.stringify(data),
        ...options
    });
}

/**
 * Get CSRF token from the page
 * @returns {string} - CSRF token
 */
function getCSRFToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    if (token) {
        return token.value;
    }
    
    const metaToken = document.querySelector('meta[name="csrf-token"]');
    if (metaToken) {
        return metaToken.getAttribute('content');
    }
    
    console.warn('CSRF token not found');
    return '';
}

/**
 * Safe fetch with CSRF token
 * @param {string} url - The URL to fetch
 * @param {Object} options - Fetch options
 * @returns {Promise<Object>} - Parsed JSON data
 */
async function safeFetchWithCSRF(url, options = {}) {
    const csrfToken = getCSRFToken();
    
    return safeFetch(url, {
        ...options,
        headers: {
            'X-CSRFToken': csrfToken,
            ...options.headers
        }
    });
}

// Expose to global scope
window.safeJsonResponse = safeJsonResponse;
window.safeFetch = safeFetch;
window.safeDelete = safeDelete;
window.safePost = safePost;
window.safePut = safePut;
window.getCSRFToken = getCSRFToken;
window.safeFetchWithCSRF = safeFetchWithCSRF;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        safeJsonResponse,
        safeFetch,
        safeDelete,
        safePost,
        safePut,
        getCSRFToken,
        safeFetchWithCSRF
    };
}
