/**
 * Global error handler for the LMS application
 * Catches and logs JavaScript errors without breaking the page
 */

(function() {
    'use strict';

    // Global error handler initialized (production-ready)

    // Store original console methods
    const originalConsoleError = console.error;
    const originalConsoleWarn = console.warn;
    
    // Error count tracking
    let errorCount = 0;
    let warningCount = 0;
    const MAX_ERRORS_TO_SHOW = 10;
    
    // Track seen errors to prevent duplicates - with cleanup mechanism
    var seenErrors = {};
    var seenErrorsCount = 0;
    const MAX_SEEN_ERRORS = 100; // Prevent memory leaks
    
    // Cleanup seen errors when we reach the limit
    function cleanupSeenErrors() {
        if (seenErrorsCount > MAX_SEEN_ERRORS) {
            seenErrors = {};
            seenErrorsCount = 0;
            console.log('Error tracking cache cleared to prevent memory leaks');
        }
    }
    
    // Override console.error to track errors
    console.error = function() {
        // Call original method
        originalConsoleError.apply(console, arguments);
        
        // Track error count
        errorCount++;
        
        // Prevent excessive error logging
        if (errorCount > MAX_ERRORS_TO_SHOW && arguments[0] !== 'Error limit reached') {
            if (errorCount === MAX_ERRORS_TO_SHOW + 1) {
                originalConsoleError.call(console, 'Error limit reached. Some errors will be suppressed.');
            }
            return;
        }
        
        // Skip TinyMCE loading messages and known plugin issues to reduce noise
        if (arguments[0] && typeof arguments[0] === 'string') {
            const errorMsg = arguments[0];
            if (errorMsg.includes('TinyMCE not loaded') || 
                errorMsg.includes('Failed to initialize TinyMCE') ||
                errorMsg.includes('Failed to load plugin: paste') ||
                errorMsg.includes('plugins/paste/plugin.min.js') ||
                errorMsg.includes('Failed to load plugin: media') ||
                errorMsg.includes('plugins/media/plugin.min.js')) {
                return;
            }
        }
        
        // Attempt to log structured error if available
        let errorInfo = '';
        for (let i = 0; i < arguments.length; i++) {
            if (arguments[i] instanceof Error) {
                errorInfo += `${arguments[i].name}: ${arguments[i].message}\n${arguments[i].stack || 'No stack trace'}\n`;
            } else {
                try {
                    errorInfo += (typeof arguments[i] === 'object') 
                        ? JSON.stringify(arguments[i], null, 2) + '\n'
                        : arguments[i] + '\n';
                } catch (e) {
                    errorInfo += '[Object could not be stringified]\n';
                }
            }
        }
        
        // Log to server if enabled (implement server logging endpoint)
        if (window.LMS_CONFIG && window.LMS_CONFIG.enableServerLogging) {
            logToServer('error', errorInfo);
        }
    };
    
    // Override console.warn to track warnings
    console.warn = function() {
        // Call original method
        originalConsoleWarn.apply(console, arguments);
        
        // Track warning count
        warningCount++;
        
        // Prevent excessive warning logging
        if (warningCount > MAX_ERRORS_TO_SHOW && arguments[0] !== 'Warning limit reached') {
            if (warningCount === MAX_ERRORS_TO_SHOW + 1) {
                originalConsoleWarn.call(console, 'Warning limit reached. Some warnings will be suppressed.');
            }
            return;
        }
        
        // Log to server if enabled (implement server logging endpoint)
        if (window.LMS_CONFIG && window.LMS_CONFIG.enableServerLogging) {
            let warningInfo = Array.from(arguments).join(' ');
            logToServer('warning', warningInfo);
        }
    };

    // Enhanced browser compatibility detection
    var isBrowserCompatible = function() {
        // Check for common ES6 features
        var hasArrowFunctions = false;
        var hasConst = false;
        var hasPromise = false;
        
        try {
            // Check arrow functions
            eval('() => {}');
            hasArrowFunctions = true;
        } catch (e) {}
        
        try {
            // Check const keyword
            eval('const x = 1;');
            hasConst = true;
        } catch (e) {}
        
        // Check for Promise
        hasPromise = typeof Promise !== 'undefined';
        
        return {
            isCompatible: hasArrowFunctions && hasConst && hasPromise,
            features: {
                arrowFunctions: hasArrowFunctions,
                constKeyword: hasConst,
                promises: hasPromise
            }
        };
    };
    
    // Check browser compatibility on load
    var compatibility = isBrowserCompatible();
    if (!compatibility.isCompatible) {
        console.warn('Browser compatibility issues detected. Some features may not work correctly.', compatibility.features);
        // Show a warning for users with incompatible browsers
        setTimeout(function() {
            showErrorNotification('Your browser may not support all features. Please consider updating your browser.', 'warning');
        }, 1000);
    }

    // Global error handler
    window.addEventListener('error', function(event) {
        // Prevent the error from completely breaking the page
        event.preventDefault();
        
        // Create a unique error signature to avoid duplicates
        var errorSignature = (event.filename || 'unknown') + ':' + (event.lineno || 0) + ':' + (event.message || 'Error');
        
        // Skip if we've seen this exact error already
        if (seenErrors[errorSignature]) {
            return true;
        }
        
        // Mark this error as seen and cleanup if necessary
        seenErrors[errorSignature] = true;
        seenErrorsCount++;
        cleanupSeenErrors();
        
        // Log the error
        console.error(
            'JavaScript Error:',
            event.error || { message: event.message },
            '\nLocation:', event.filename || 'unknown file',
            'Line:', event.lineno || 'unknown line',
            'Column:', event.colno || 'unknown column'
        );
        
        // Handle TinyMCE specific errors
        if (event.filename && event.filename.includes('tinymce')) {
            fixTinyMCEIssues();
        }
        
        // Handle ES6 syntax errors
        if (event.message && event.message.includes('Unexpected token')) {
            if (event.message.includes("'const'") || event.message.includes("'let'") || 
                event.message.includes("'=>'") || event.message.includes("'...")) {
                console.warn('ES6 syntax not supported in this browser. Consider using ES5 syntax or a transpiler.');
                showErrorNotification('Your browser does not support modern JavaScript features. Please update your browser.', 'warning');
            }
        }
        
        // Show a UI error notification if it's a critical error
        // Disabled to prevent unnecessary user warnings during normal operation
        // if (isCriticalError(event)) {
        //     showErrorNotification('A problem occurred. Please try refreshing the page.');
        // }
        
        return true; // Prevents the browser's default error handling
    });
    
    // Fix TinyMCE issues - improved version with better error handling
    function fixTinyMCEIssues() {
        // Attempt to fix common TinyMCE issues
        if (typeof tinymce !== 'undefined' && tinymce.editors) {
            setTimeout(function() {
                // Filter out broken editors and try to fix them safely
                const brokenEditors = [];
                for (let i = 0; i < tinymce.editors.length; i++) {
                    const editor = tinymce.editors[i];
                    if (editor && !editor.getContainer()) {
                        brokenEditors.push(editor);
                    }
                }
                
                brokenEditors.forEach(function(editor) {
                    try {
                        console.log('Attempting to recover TinyMCE editor:', editor.id);
                        
                        // Safely remove the broken editor
                        if (editor.remove) {
                            editor.remove();
                        }
                        
                        // Check if the element still exists
                        const targetElement = document.getElementById(editor.id);
                        if (targetElement) {
                            // Use simpler configuration to avoid plugin issues
                            tinymce.init({
                                selector: '#' + editor.id,
                                height: 300,
                                menubar: false, // Disable menubar to avoid conflicts
                                plugins: 'lists link code', // Only essential plugins
                                toolbar: 'bold italic underline | bullist numlist | link code',
                                branding: false,
                                promotion: false,
                                statusbar: false,
                                resize: true,
                                setup: function(ed) {
                                    ed.on('init', function() {
                                        console.log('TinyMCE editor recovered successfully:', ed.id);
                                    });
                                    ed.on('error', function(e) {
                                        console.warn('Recovered TinyMCE editor error:', e);
                                    });
                                }
                            });
                        } else {
                            console.warn('Target element not found for TinyMCE recovery:', editor.id);
                        }
                    } catch (e) {
                        console.warn('Failed to recover TinyMCE editor', editor.id, e);
                        
                        // Last resort: try to make the textarea visible again
                        try {
                            const textarea = document.getElementById(editor.id);
                            if (textarea) {
                                textarea.style.display = 'block';
                                textarea.style.visibility = 'visible';
                            }
                        } catch (fallbackError) {
                            console.error('Complete TinyMCE recovery failed:', fallbackError);
                        }
                    }
                });
            }, 2000); // Increased delay to allow page to stabilize
        }
    }
    
    // Unhandled promise rejection handler
    window.addEventListener('unhandledrejection', function(event) {
        console.error('Unhandled Promise Rejection:', event.reason);
        
        // Log to server if enabled
        if (window.LMS_CONFIG && window.LMS_CONFIG.enableServerLogging) {
            logToServer('rejection', event.reason.stack || event.reason.toString());
        }
        
        return false; // Let the browser handle this normally
    });
    
    // Function to determine if an error is critical
    function isCriticalError(event) {
        // Define rules for critical errors that should be shown to the user
        // For example, errors from main application code rather than plugins
        
        // Don't treat common initialization errors as critical
        if (event.message && (
            event.message.includes('Cannot read properties of null') ||
            event.message.includes('Cannot read property') ||
            event.message.includes('is not defined') ||
            event.message.includes('is not a function')
        )) {
            // Only show these if they're from critical core files
            if (event.filename && event.filename.includes('/core/')) {
                return true;
            }
            return false;
        }
        
        // Don't treat course JavaScript initialization errors as critical
        if (event.filename && event.filename.includes('/courses/')) {
            // Only show syntax errors and other serious issues
            if (event.message && (
                event.message.includes('SyntaxError') ||
                event.message.includes('Unexpected token') ||
                event.message.includes('Invalid left-hand side')
            )) {
                return true;
            }
            return false;
        }
        
        if (event.filename && (
            event.filename.includes('/core/') ||
            event.filename.includes('/main.js')
        )) {
            return true;
        }
        
        // Don't treat TinyMCE plugin loading issues as critical
        if (event.message && event.message.includes('Failed to load plugin:')) {
            return false;
        }
        
        // Don't treat ES6 compatibility issues as critical
        if (event.message && event.message.includes('Unexpected token')) {
            if (event.message.includes("'const'") || event.message.includes("'let'") || 
                event.message.includes("'=>'") || event.message.includes("'...")) {
                return false;
            }
        }
        
        return false;
    }
    
    // Function to show error notification to the user
    function showErrorNotification(message, type) {
        // Check if we already have a notification
        let notification = document.getElementById('js-error-notification');
        
        if (!notification) {
            // Create notification element
            notification = document.createElement('div');
            notification.id = 'js-error-notification';
            
            // Set style based on type
            var bgColor = 'bg-red-100';
            var borderColor = 'border-red-500';
            var textColor = 'text-red-700';
            
            if (type === 'warning') {
                bgColor = 'bg-yellow-100';
                borderColor = 'border-yellow-500';
                textColor = 'text-yellow-700';
            }
            
            notification.className = 'fixed bottom-4 right-4 ' + bgColor + ' border-l-4 ' + borderColor + ' ' + textColor + ' p-4 rounded shadow-lg z-50 max-w-md';
            notification.style.display = 'flex';
            notification.style.justifyContent = 'space-between';
            notification.style.alignItems = 'center';
            
            // Add message and close button
            notification.innerHTML = `
                <div class="mr-3">${message}</div>
                <button class="${textColor} hover:text-red-900 focus:outline-none" onclick="this.parentNode.remove()">
                    <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                    </svg>
                </button>
            `;
            
            // Add to document
            document.body.appendChild(notification);
            
            // Remove after 10 seconds
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 10000);
        }
    }
    
    // Function to log errors to server
    function logToServer(level, errorInfo) {
        // Don't proceed if no error info
        if (!errorInfo) return;
        
        // Create a simple payload
        var payload = {
            level: level,
            message: typeof errorInfo === 'string' ? errorInfo : JSON.stringify(errorInfo),
            url: window.location.href,
            userAgent: navigator.userAgent,
            timestamp: new Date().toISOString()
        };
        
        // Send to server error logging endpoint
        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/log-client-error/', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        
        // Try to get CSRF token
        var csrfToken = document.querySelector('meta[name="csrf-token"]');
        if (csrfToken) {
            xhr.setRequestHeader('X-CSRFToken', csrfToken.getAttribute('content'));
        }
        
        // Don't worry about the response
        xhr.send(JSON.stringify(payload));
    }
    
    // Polyfill ES6 features for older browsers
    function polyfillES6Features() {
        // Basic Promise polyfill check
        if (typeof Promise === 'undefined') {
            console.warn('Promise not supported, adding polyfill');
            // This is a simplified Promise polyfill
            window.Promise = function(executor) {
                var callbacks = [];
                var state = 'pending';
                var value;
                
                this.then = function(onFulfilled) {
                    if (state === 'pending') {
                        callbacks.push(onFulfilled);
                        return this;
                    }
                    onFulfilled(value);
                    return this;
                };
                
                function resolve(newValue) {
                    value = newValue;
                    state = 'fulfilled';
                    callbacks.forEach(function(callback) {
                        callback(value);
                    });
                }
                
                executor(resolve);
            };
        }
    }
    
    // Try to polyfill ES6 features
    polyfillES6Features();
    
    // Cleanup function for page unload to prevent memory leaks
    window.addEventListener('beforeunload', function() {
        // Clear error tracking to prevent memory leaks
        seenErrors = {};
        seenErrorsCount = 0;
        errorCount = 0;
        warningCount = 0;
    });
    
    // Initialize error tracking
    console.log('Error handler initialized. Tracking JavaScript errors.');
})(); 