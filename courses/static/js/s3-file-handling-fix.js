/**
 * S3 File Handling Fix for LMS
 * Version: 2025-09-26
 * 
 * This script provides comprehensive S3 error handling and retry logic
 * for file uploads, downloads, and other S3 operations throughout the LMS.
 * 
 * Issues Fixed:
 * 1. S3 permission errors (403 Forbidden)
 * 2. File upload timeout and retry logic
 * 3. Better error messaging for S3 issues
 * 4. CSRF token handling for file operations
 * 5. Network error recovery for file operations
 */

console.log(' Loading S3 File Handling Fix...');

/**
 * Enhanced S3 Error Handler
 */
window.S3FileHandler = {
    
    // Configuration
    config: {
        maxRetries: 3,
        retryDelay: 2000,
        timeout: 30000
    },
    
    /**
     * Check if error is S3 related
     */
    isS3Error: function(error) {
        const errorStr = error.toString().toLowerCase();
        return errorStr.includes('s3') || 
               errorStr.includes('403') || 
               errorStr.includes('forbidden') || 
               errorStr.includes('permission') ||
               errorStr.includes('headobject');
    },
    
    /**
     * Check if error is network related
     */
    isNetworkError: function(error) {
        return error.name === 'TypeError' || 
               error.message.includes('network') ||
               error.message.includes('fetch');
    },
    
    /**
     * Get CSRF token with multiple fallback methods
     */
    getCSRFToken: function() {
        const methods = [
            () => document.querySelector('[name=csrfmiddlewaretoken]')?.value,
            () => document.querySelector('meta[name=csrf-token]')?.content,
            () => this.getCookie('csrftoken'),
            () => window.CSRF_TOKEN
        ];
        
        for (const method of methods) {
            try {
                const token = method();
                if (token) return token;
            } catch (e) {
                console.debug('CSRF method failed:', e);
            }
        }
        
        console.error(' CSRF token not found');
        return null;
    },
    
    /**
     * Get cookie value
     */
    getCookie: function(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    },
    
    /**
     * Enhanced file upload with S3 error handling and retry logic
     */
    uploadFile: async function(file, endpoint, options = {}) {
        const config = { ...this.config, ...options };
        let lastError = null;
        
        for (let attempt = 1; attempt <= config.maxRetries; attempt++) {
            try {
                console.log(`📤 File upload attempt ${attempt}/${config.maxRetries}`);
                
                const formData = new FormData();
                formData.append('file', file);
                
                // Add any additional form data
                if (options.extraData) {
                    Object.keys(options.extraData).forEach(key => {
                        formData.append(key, options.extraData[key]);
                    });
                }
                
                const csrfToken = this.getCSRFToken();
                if (!csrfToken) {
                    throw new Error('CSRF token not found. Please refresh the page and try again.');
                }
                
                const response = await this.fetchWithTimeout(endpoint, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRFToken': csrfToken,
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                }, config.timeout);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const result = await response.json();
                
                if (result.success) {
                    console.log(' File upload successful');
                    return result;
                } else {
                    throw new Error(result.error || 'Upload failed');
                }
                
            } catch (error) {
                lastError = error;
                console.error(` Upload attempt ${attempt} failed:`, error);
                
                // Check if we should retry
                const shouldRetry = attempt < config.maxRetries && 
                                   (this.isS3Error(error) || this.isNetworkError(error));
                
                if (shouldRetry) {
                    console.log(` Retrying in ${config.retryDelay}ms...`);
                    await this.sleep(config.retryDelay);
                    // Increase delay for next attempt
                    config.retryDelay *= 1.5;
                } else {
                    break;
                }
            }
        }
        
        // All attempts failed
        throw this.createEnhancedError(lastError);
    },
    
    /**
     * Enhanced fetch with timeout
     */
    fetchWithTimeout: function(url, options, timeout = 30000) {
        return Promise.race([
            fetch(url, options),
            new Promise((_, reject) => 
                setTimeout(() => reject(new Error('Request timeout')), timeout)
            )
        ]);
    },
    
    /**
     * Create enhanced error with user-friendly messages
     */
    createEnhancedError: function(originalError) {
        let userMessage = 'File operation failed';
        let technicalMessage = originalError.message;
        
        if (this.isS3Error(originalError)) {
            userMessage = 'Storage permission error. Please contact your administrator.';
        } else if (this.isNetworkError(originalError)) {
            // More specific network error messages
            if (originalError.message.includes('Failed to fetch')) {
                userMessage = 'Unable to connect to the server. Please check your internet connection.';
            } else if (navigator.onLine === false) {
                userMessage = 'No internet connection detected. Please check your connection and try again.';
            } else {
                userMessage = 'Network connection issue. Please try again or contact support if this persists.';
            }
        } else if (originalError.message.includes('timeout')) {
            userMessage = 'Upload timeout. Please try again with a smaller file.';
        } else if (originalError.message.includes('CSRF')) {
            userMessage = 'Security token expired. Please refresh the page and try again.';
        }
        
        const error = new Error(userMessage);
        error.technicalMessage = technicalMessage;
        error.isEnhanced = true;
        return error;
    },
    
    /**
     * Sleep utility for retry delays
     */
    sleep: function(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    },
    
    /**
     * Show user-friendly error notification
     */
    showErrorNotification: function(error, container = null) {
        const message = error.isEnhanced ? error.message : 'An error occurred during file operation';
        
        // Create notification element
        const notification = document.createElement('div');
        notification.className = 's3-error-notification';
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #f87171;
            color: white;
            padding: 12px 16px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 10000;
            max-width: 400px;
            font-size: 14px;
            line-height: 1.4;
        `;
        notification.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 4px;">File Operation Failed</div>
            <div>${message}</div>
            <button onclick="this.parentElement.remove()" style="
                position: absolute;
                top: 8px;
                right: 8px;
                background: none;
                border: none;
                color: white;
                font-size: 16px;
                cursor: pointer;
            ">&times;</button>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 8 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 8000);
    },
    
    /**
     * Initialize S3 file handling for forms
     */
    initializeFormHandling: function() {
        // Enhance all file upload forms
        const fileInputs = document.querySelectorAll('input[type="file"]');
        fileInputs.forEach(input => {
            if (!input.hasAttribute('data-s3-enhanced')) {
                this.enhanceFileInput(input);
                input.setAttribute('data-s3-enhanced', 'true');
            }
        });
        
        console.log(` Enhanced ${fileInputs.length} file inputs for S3 handling`);
    },
    
    /**
     * Enhance individual file input
     */
    enhanceFileInput: function(input) {
        const originalHandler = input.onchange;
        
        input.addEventListener('change', async (event) => {
            if (event.target.files.length > 0) {
                const file = event.target.files[0];
                console.log(`📁 File selected: ${file.name} (${this.formatFileSize(file.size)})`);
                
                // Add visual feedback
                this.showFileProcessingIndicator(input);
                
                // Call original handler if exists
                if (originalHandler) {
                    try {
                        await originalHandler.call(input, event);
                    } catch (error) {
                        console.error('Original handler error:', error);
                        this.showErrorNotification(error);
                    }
                }
                
                this.hideFileProcessingIndicator(input);
            }
        });
    },
    
    /**
     * Show file processing indicator
     */
    showFileProcessingIndicator: function(input) {
        let indicator = input.parentElement.querySelector('.s3-processing-indicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.className = 's3-processing-indicator';
            indicator.style.cssText = `
                display: inline-block;
                margin-left: 8px;
                padding: 4px 8px;
                background: #3b82f6;
                color: white;
                border-radius: 4px;
                font-size: 12px;
            `;
            indicator.textContent = 'Processing...';
            input.parentElement.appendChild(indicator);
        }
        indicator.style.display = 'inline-block';
    },
    
    /**
     * Hide file processing indicator
     */
    hideFileProcessingIndicator: function(input) {
        const indicator = input.parentElement.querySelector('.s3-processing-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
    },
    
    /**
     * Format file size for display
     */
    formatFileSize: function(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    window.S3FileHandler.initializeFormHandling();
    console.log(' S3 File Handling Fix initialized');
});

// Also initialize if DOM is already loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        window.S3FileHandler.initializeFormHandling();
    });
} else {
    window.S3FileHandler.initializeFormHandling();
}

console.log(' S3 File Handling Fix loaded successfully');
