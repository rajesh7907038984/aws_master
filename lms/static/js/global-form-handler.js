/**
 * Global Form Handler - Comprehensive Submit Button Error Fix
 * This script fixes common form submission errors across the LMS
 */

(function() {
    'use strict';

    // Global error tracking
    window.LMSFormHandler = {
        debugMode: false,
        
        // Add global error logging
        logError: function(error, context = 'Unknown') {
            const errorDetails = {
                context: context,
                name: error.name || 'Unknown',
                message: error.message || 'No message',
                stack: error.stack?.substring(0, 300) || 'No stack trace',
                url: window.location.href,
                userAgent: navigator.userAgent,
                timestamp: new Date().toISOString(),
                online: navigator.onLine
            };
            
            console.error('LMS Error Details:', errorDetails);
            
            // Store recent errors in localStorage for debugging
            try {
                const recentErrors = TypeSafety.safeJsonParse(localStorage.getItem('lms_recent_errors'), []);
                recentErrors.push(errorDetails);
                // Keep only last 10 errors
                if (recentErrors.length > 10) {
                    recentErrors.shift();
                }
                localStorage.setItem('lms_recent_errors', JSON.stringify(recentErrors));
            } catch (storageError) {
                console.warn('Could not store error in localStorage:', storageError);
            }
            
            return errorDetails;
        },
        
        // Initialize the form handler
        init: function() {
            this.setupCSRFHandling();
            this.setupGlobalFormHandlers();
            this.setupErrorHandling();
            this.fixCommonSubmitIssues();
            console.log('LMS Form Handler initialized');
        },

        // Enhanced CSRF token handling with validation
        setupCSRFHandling: function() {
            // Get CSRF token from multiple sources with validation
            const getCSRFToken = function() {
                // Priority order for CSRF token sources
                const sources = [
                    () => document.querySelector('meta[name="csrf-token"]')?.getAttribute('content'),
                    () => document.querySelector('input[name="csrfmiddlewaretoken"]')?.value,
                    () => window.CSRF_TOKEN,
                    () => document.cookie.match(/csrftoken=([^;]+)/)?.[1]
                ];

                for (let source of sources) {
                    try {
                        const token = source();
                        if (token && token.length > 0) {
                            // Validate token format (should be alphanumeric)
                            if (/^[a-zA-Z0-9]+$/.test(token)) {
                                return token;
                            }
                        }
                    } catch (e) {
                        console.warn('CSRF token source failed:', e);
                        // Continue to next source
                    }
                }
                
                console.error('No valid CSRF token found from any source');
                return null;
            };

            // Make CSRF token globally available
            window.getCSRFToken = getCSRFToken;
            
            // Validate CSRF token on page load
            const token = getCSRFToken();
            if (!token) {
                console.error('CRITICAL: No CSRF token available - forms will fail to submit');
                this.showGlobalError('Security token missing. Please refresh the page and try again.');
            }

            // Add CSRF token to all forms with enhanced error handling
            document.addEventListener('DOMContentLoaded', function() {
                const token = getCSRFToken();
                if (!token) {
                    console.error('No CSRF token available for forms');
                    LMSFormHandler.showGlobalError('Security token missing. Please refresh the page and try again.');
                    return;
                }

                // Add CSRF token only to forms that need it (POST/PUT/PATCH/DELETE)
                const forms = document.querySelectorAll('form');
                let formsUpdated = 0;
                
                forms.forEach(form => {
                    const method = (form.getAttribute('method') || 'GET').toUpperCase();
                    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && !form.querySelector('input[name="csrfmiddlewaretoken"]')) {
                        const csrfInput = document.createElement('input');
                        csrfInput.type = 'hidden';
                        csrfInput.name = 'csrfmiddlewaretoken';
                        csrfInput.value = token;
                        form.appendChild(csrfInput);
                        formsUpdated++;
                    }
                });
                
                if (formsUpdated > 0) {
                    console.log(`Added CSRF token to ${formsUpdated} forms`);
                }
            });
        },

        // Setup global form submission handlers with enhanced error handling
        setupGlobalFormHandlers: function() {
            document.addEventListener('submit', function(event) {
                const form = event.target;
                if (!form.tagName || form.tagName.toLowerCase() !== 'form') return;

                // Skip if form has its own handler
                if (form.hasAttribute('data-custom-handler')) return;

                // Validate CSRF token before submission
                const csrfToken = getCSRFToken();
                if (!csrfToken) {
                    event.preventDefault();
                    LMSFormHandler.showGlobalError('Security token missing. Please refresh the page and try again.');
                    return;
                }

                // Prevent double submission
                if (form.hasAttribute('data-submitting')) {
                    event.preventDefault();
                    return;
                }

                form.setAttribute('data-submitting', 'true');
                
                // Add loading state
                const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = true;
                    const originalText = submitBtn.textContent || submitBtn.value;
                    submitBtn.setAttribute('data-original-text', originalText);
                    
                    if (submitBtn.tagName.toLowerCase() === 'button') {
                        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
                    } else {
                        submitBtn.value = 'Processing...';
                    }
                }

                // Validate CSRF token only for non-GET requests
                const method = (form.getAttribute('method') || 'GET').toUpperCase();
                if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
                    const token = form.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
                    if (!token) {
                        event.preventDefault();
                        this.showError(form, 'Security token missing. Please refresh the page and try again.');
                        this.resetForm(form);
                        return;
                    }
                }

                // Set timeout to reset form if submission takes too long
                setTimeout(() => {
                    if (form.hasAttribute('data-submitting')) {
                        this.resetForm(form);
                        this.showError(form, 'Request timed out. Please try again.');
                    }
                }, 30000);
            }.bind(this));

            // Handle form response errors
            window.addEventListener('beforeunload', function() {
                document.querySelectorAll('form[data-submitting]').forEach(form => {
                    LMSFormHandler.resetForm(form);
                });
            });
        },

        // Enhanced error handling
        setupErrorHandling: function() {
            // Handle AJAX form submissions
            const originalFetch = window.fetch;
            window.fetch = function(url, options = {}) {
                // Add CSRF token for POST requests
                if (options.method && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(options.method.toUpperCase())) {
                    options.headers = options.headers || {};
                    if (!options.headers['X-CSRFToken']) {
                        const token = window.getCSRFToken();
                        if (token) {
                            options.headers['X-CSRFToken'] = token;
                        }
                    }
                }

                return originalFetch(url, options)
                    .then(response => {
                        // Handle common error responses - but only for user-initiated actions
                        // Don't show errors for background requests or optional resources
                        const isUserInitiated = options.userInitiated === true;
                        
                        if (response.status === 403 && isUserInitiated) {
                            LMSFormHandler.showGlobalError('Permission denied. Please refresh the page and try again.');
                        } else if (response.status === 404 && isUserInitiated) {
                            // Only show 404 errors for user-initiated requests
                            console.warn('Resource not found:', url);
                            // Don't show automatic error notification for 404s
                        } else if (response.status >= 500 && isUserInitiated) {
                            LMSFormHandler.showGlobalError('Server error. Please try again in a few moments.');
                        } else if (!response.ok) {
                            // Log other errors to console for debugging
                            console.warn(`HTTP ${response.status}: ${response.statusText} for ${url}`);
                        }
                        return response;
                    })
                    .catch(error => {
                        // Enhanced error handling for production with more specific messages
                        // ONLY show errors for user-initiated actions
                        const isUserInitiated = options.userInitiated === true;
                        
                        LMSFormHandler.logError(error, 'Fetch request failed');
                        
                        // Only show error notifications for user-initiated requests
                        if (isUserInitiated) {
                            let errorMessage = 'Request failed. Please try again.';
                            
                            if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
                                errorMessage = 'Unable to connect to the server. Please check your internet connection and try again.';
                            } else if (error.name === 'AbortError') {
                                errorMessage = 'Request timed out. Please try again.';
                            } else if (error.message.includes('CORS')) {
                                errorMessage = 'Security error. Please refresh the page and try again.';
                            } else if (error.message.includes('403')) {
                                errorMessage = 'Permission denied. Please refresh the page and try again.';
                            } else if (error.message.includes('500')) {
                                errorMessage = 'Server error. Please try again in a few moments.';
                            } else if (error.message.includes('404')) {
                                // Don't show 404 errors automatically - just log them
                                console.warn('Resource not found:', url);
                                throw error; // Let the caller handle it
                            } else if (error.message.includes('CSRF')) {
                                errorMessage = 'Security token expired. Please refresh the page and try again.';
                            } else if (error.name === 'SyntaxError') {
                                errorMessage = 'Server response format error. Please contact support if this persists.';
                            } else if (navigator.onLine === false) {
                                errorMessage = 'No internet connection detected. Please check your connection and try again.';
                            }
                            
                            LMSFormHandler.showGlobalError(errorMessage);
                        } else {
                            // For non-user-initiated requests, just log to console
                            console.warn('Fetch error (non-user-initiated):', error.message, url);
                        }
                        
                        throw error;
                    });
            };
        },

        // Fix common submit button issues
        fixCommonSubmitIssues: function() {
            document.addEventListener('DOMContentLoaded', function() {
                // Fix forms with missing action attributes
                document.querySelectorAll('form:not([action])').forEach(form => {
                    form.action = window.location.href;
                });

                // Fix submit buttons that might be outside forms
                document.querySelectorAll('button[type="submit"]').forEach(button => {
                    if (!button.form && !button.closest('form')) {
                        const nearestForm = document.querySelector('form');
                        if (nearestForm) {
                            button.setAttribute('form', nearestForm.id || 'main-form');
                            if (!nearestForm.id) {
                                nearestForm.id = 'main-form';
                            }
                        }
                    }
                });

                // Add click handlers for problematic submit buttons
                document.querySelectorAll('[data-submit-form]').forEach(button => {
                    button.addEventListener('click', function(e) {
                        e.preventDefault();
                        const formId = this.getAttribute('data-submit-form');
                        const form = document.getElementById(formId);
                        if (form) {
                            form.submit();
                        }
                    });
                });
            });
        },

        // Reset form state
        resetForm: function(form) {
            form.removeAttribute('data-submitting');
            
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (submitBtn && submitBtn.hasAttribute('data-original-text')) {
                submitBtn.disabled = false;
                const originalText = submitBtn.getAttribute('data-original-text');
                
                if (submitBtn.tagName.toLowerCase() === 'button') {
                    submitBtn.innerHTML = originalText;
                } else {
                    submitBtn.value = originalText;
                }
                
                submitBtn.removeAttribute('data-original-text');
            }
        },

        // Show form-specific error
        showError: function(form, message) {
            // Remove existing error messages
            form.querySelectorAll('.lms-form-error').forEach(el => el.remove());

            // Create error element
            const errorDiv = document.createElement('div');
            errorDiv.className = 'lms-form-error alert alert-danger';
            errorDiv.style.cssText = `
                margin: 10px 0;
                padding: 10px;
                background-color: #f8d7da;
                border: 1px solid #f5c6cb;
                color: #721c24;
                border-radius: 4px;
            `;
            errorDiv.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${message}`;

            // Insert at top of form
            form.insertBefore(errorDiv, form.firstChild);

            // Auto-remove after 10 seconds
            setTimeout(() => {
                if (errorDiv.parentNode) {
                    errorDiv.remove();
                }
            }, 10000);
        },

        // Show global error message
        showGlobalError: function(message) {
            // Check if Django messages framework is available
            if (typeof django !== 'undefined' && django.messages) {
                django.messages.error(message);
            } else {
                // Fallback to alert or custom notification
                console.error('Form Error:', message);
                
                // Try to show in existing message container
                let messageContainer = document.querySelector('.messages, .alert-container, #messages');
                if (!messageContainer) {
                    messageContainer = document.createElement('div');
                    messageContainer.className = 'lms-global-messages';
                    messageContainer.style.cssText = `
                        position: fixed;
                        top: 20px;
                        right: 20px;
                        z-index: 9999;
                        max-width: 400px;
                    `;
                    document.body.appendChild(messageContainer);
                }

                const messageDiv = document.createElement('div');
                messageDiv.className = 'alert alert-danger lms-auto-message';
                messageDiv.style.cssText = `
                    margin-bottom: 10px;
                    padding: 10px;
                    background-color: #f8d7da;
                    border: 1px solid #f5c6cb;
                    color: #721c24;
                    border-radius: 4px;
                `;
                messageDiv.innerHTML = `
                    <button type="button" class="close" style="float: right; border: none; background: none; font-size: 18px;">&times;</button>
                    <i class="fas fa-exclamation-triangle"></i> ${message}
                `;

                messageContainer.appendChild(messageDiv);

                // Add close button functionality
                messageDiv.querySelector('.close').addEventListener('click', function() {
                    messageDiv.remove();
                });

                // Auto-remove after 8 seconds
                setTimeout(() => {
                    if (messageDiv.parentNode) {
                        messageDiv.remove();
                    }
                }, 8000);
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            window.LMSFormHandler.init();
        });
    } else {
        window.LMSFormHandler.init();
    }
})();
