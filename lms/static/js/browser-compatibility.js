/**
 * Browser Compatibility Utilities
 * Provides polyfills and compatibility checks for older browsers
 */

(function() {
    'use strict';
    
    // Browser detection
    const browserInfo = {
        isIE: /MSIE|Trident/.test(navigator.userAgent),
        isEdge: /Edge/.test(navigator.userAgent),
        isFirefox: /Firefox/.test(navigator.userAgent),
        isChrome: /Chrome/.test(navigator.userAgent) && !/Edge/.test(navigator.userAgent),
        isSafari: /Safari/.test(navigator.userAgent) && !/Chrome/.test(navigator.userAgent),
        version: parseFloat(navigator.userAgent.match(/(\d+\.\d+)/)?.[1] || '0')
    };
    
    // Compatibility issues detected
    const compatibilityIssues = [];
    
    /**
     * Check if a feature is supported
     * @param {string} feature Feature name
     * @returns {boolean} True if supported
     */
    function isFeatureSupported(feature) {
        const features = {
            'MutationObserver': typeof MutationObserver !== 'undefined',
            'Promise': typeof Promise !== 'undefined',
            'fetch': typeof fetch !== 'undefined',
            'localStorage': typeof localStorage !== 'undefined',
            'sessionStorage': typeof sessionStorage !== 'undefined',
            'addEventListener': typeof document.addEventListener !== 'undefined',
            'querySelector': typeof document.querySelector !== 'undefined',
            'classList': typeof document.createElement('div').classList !== 'undefined',
            'dataset': typeof document.createElement('div').dataset !== 'undefined',
            'arrowFunctions': (function() { 
                try { 
                    // CSP-safe arrow function test without eval
                    return typeof (() => {}) === 'function';
                } catch(e) { 
                    console.warn('Arrow function test failed:', e);
                    return false; 
                } 
            })(),
            'templateLiterals': (function() { 
                try { 
                    // CSP-safe template literal test without eval
                    return typeof `test` === 'string';
                } catch(e) { 
                    console.warn('Template literal test failed:', e);
                    return false; 
                } 
            })(),
            'constLet': (function() { 
                try { 
                    // CSP-safe const/let test without eval
                    return typeof (function() { const test = 1; let test2 = 2; return test + test2; })() === 'number';
                } catch(e) { 
                    console.warn('Const/let test failed:', e);
                    return false; 
                } 
            })()
        };
        
        return features[feature] || false;
    }
    
    /**
     * Add polyfills for missing features
     */
    function addPolyfills() {
        // Promise polyfill for IE
        if (!isFeatureSupported('Promise')) {
            compatibilityIssues.push('Promise not supported - using polyfill');
            // Simple Promise polyfill
            window.Promise = window.Promise || function(executor) {
                const self = this;
                self.state = 'pending';
                self.value = undefined;
                self.handlers = [];
                
                function resolve(result) {
                    if (self.state === 'pending') {
                        self.state = 'fulfilled';
                        self.value = result;
                        self.handlers.forEach(handle);
                        self.handlers = null;
                    }
                }
                
                function reject(error) {
                    if (self.state === 'pending') {
                        self.state = 'rejected';
                        self.value = error;
                        self.handlers.forEach(handle);
                        self.handlers = null;
                    }
                }
                
                function handle(handler) {
                    if (self.state === 'pending') {
                        self.handlers.push(handler);
                    } else {
                        if (self.state === 'fulfilled' && typeof handler.onFulfilled === 'function') {
                            handler.onFulfilled(self.value);
                        }
                        if (self.state === 'rejected' && typeof handler.onRejected === 'function') {
                            handler.onRejected(self.value);
                        }
                    }
                }
                
                this.then = function(onFulfilled, onRejected) {
                    return new Promise(function(resolve, reject) {
                        handle({
                            onFulfilled: function(result) {
                                try {
                                    resolve(onFulfilled ? onFulfilled(result) : result);
                                } catch (ex) {
                                    reject(ex);
                                }
                            },
                            onRejected: function(error) {
                                try {
                                    resolve(onRejected ? onRejected(error) : error);
                                } catch (ex) {
                                    reject(ex);
                                }
                            }
                        });
                    });
                };
                
                this.catch = function(onRejected) {
                    return this.then(null, onRejected);
                };
                
                try {
                    executor(resolve, reject);
                } catch (ex) {
                    reject(ex);
                }
            };
        }
        
        // Fetch polyfill for older browsers
        if (!isFeatureSupported('fetch')) {
            compatibilityIssues.push('fetch not supported - using XMLHttpRequest fallback');
            window.fetch = function(url, options = {}) {
                return new Promise(function(resolve, reject) {
                    const xhr = new XMLHttpRequest();
                    xhr.open(options.method || 'GET', url);
                    
                    // Set headers
                    if (options.headers) {
                        Object.keys(options.headers).forEach(function(key) {
                            xhr.setRequestHeader(key, options.headers[key]);
                        });
                    }
                    
                    xhr.onload = function() {
                        resolve({
                            ok: xhr.status >= 200 && xhr.status < 300,
                            status: xhr.status,
                            statusText: xhr.statusText,
                            text: function() { return Promise.resolve(xhr.responseText); },
                            json: function() { return Promise.resolve(JSON.parse(xhr.responseText)); }
                        });
                    };
                    
                    xhr.onerror = function() {
                        reject(new Error('Network error'));
                    };
                    
                    xhr.send(options.body);
                });
            };
        }
        
        // Array.from polyfill for IE
        if (!Array.from) {
            compatibilityIssues.push('Array.from not supported - using polyfill');
            Array.from = function(arrayLike) {
                return Array.prototype.slice.call(arrayLike);
            };
        }
        
        // Object.assign polyfill for IE
        if (!Object.assign) {
            compatibilityIssues.push('Object.assign not supported - using polyfill');
            Object.assign = function(target) {
                for (let i = 1; i < arguments.length; i++) {
                    const source = arguments[i];
                    for (let key in source) {
                        if (source.hasOwnProperty(key)) {
                            target[key] = source[key];
                        }
                    }
                }
                return target;
            };
        }
        
        // String.includes polyfill for IE
        if (!String.prototype.includes) {
            compatibilityIssues.push('String.includes not supported - using polyfill');
            String.prototype.includes = function(search, start) {
                if (typeof start !== 'number') {
                    start = 0;
                }
                if (start + search.length > this.length) {
                    return false;
                } else {
                    return this.indexOf(search, start) !== -1;
                }
            };
        }
        
        // Array.includes polyfill for IE
        if (!Array.prototype.includes) {
            compatibilityIssues.push('Array.includes not supported - using polyfill');
            Array.prototype.includes = function(searchElement, fromIndex) {
                if (this === null || this === undefined) {
                    throw new TypeError('Array.prototype.includes called on null or undefined');
                }
                var O = Object(this);
                var len = parseInt(O.length) || 0;
                if (len === 0) {
                    return false;
                }
                var n = parseInt(fromIndex) || 0;
                var k = n >= 0 ? n : Math.max(len + n, 0);
                while (k < len) {
                    if (O[k] === searchElement) {
                        return true;
                    }
                    k++;
                }
                return false;
            };
        }
    }
    
    /**
     * Safe MutationObserver wrapper
     * @param {function} callback Mutation callback
     * @returns {object|null} MutationObserver or null
     */
    function createSafeMutationObserver(callback) {
        if (!isFeatureSupported('MutationObserver')) {
            compatibilityIssues.push('MutationObserver not supported');
            return null;
        }
        
        try {
            return new MutationObserver(callback);
        } catch (error) {
            ProductionLogger.warn('MutationObserver creation failed:', error);
            return null;
        }
    }
    
    /**
     * Safe element observation
     * @param {object} observer MutationObserver instance
     * @param {Element} target Target element
     * @param {object} options Observer options
     * @returns {boolean} True if successful
     */
    function safeObserve(observer, target, options) {
        if (!observer || !target) {
            ProductionLogger.warn('Invalid observer or target');
            return false;
        }
        
        if (target.nodeType !== 1) { // Element node
            ProductionLogger.warn('Target is not an element node');
            return false;
        }
        
        try {
            observer.observe(target, options);
            return true;
        } catch (error) {
            ProductionLogger.warn('Observer setup failed:', error);
            return false;
        }
    }
    
    /**
     * Enhanced addEventListener with fallback
     * @param {Element} element Target element
     * @param {string} event Event name
     * @param {function} handler Event handler
     * @param {boolean|object} options Event options
     */
    function safeAddEventListener(element, event, handler, options) {
        if (!element || typeof element.addEventListener !== 'function') {
            ProductionLogger.warn('Invalid element for addEventListener');
            return;
        }
        
        try {
            element.addEventListener(event, handler, options);
        } catch (error) {
            ProductionLogger.warn('addEventListener failed, using fallback:', error);
            // Fallback for older browsers
            if (element.attachEvent) {
                element.attachEvent('on' + event, handler);
            }
        }
    }
    
    /**
     * Safe querySelector with fallback
     * @param {string} selector CSS selector
     * @param {Element} context Context element (default: document)
     * @returns {Element|null} Found element or null
     */
    function safeQuerySelector(selector, context) {
        context = context || document;
        
        if (!context.querySelector) {
            ProductionLogger.warn('querySelector not supported');
            return null;
        }
        
        try {
            return context.querySelector(selector);
        } catch (error) {
            ProductionLogger.warn('querySelector failed:', error);
            return null;
        }
    }
    
    /**
     * Initialize browser compatibility
     */
    function initializeCompatibility() {
        addPolyfills();
        
        // Log compatibility issues
        if (compatibilityIssues.length > 0) {
            ProductionLogger.warn('Browser compatibility issues detected:', compatibilityIssues);
        }
        
        // Set up global compatibility utilities
        window.BrowserCompatibility = {
            info: browserInfo,
            isSupported: isFeatureSupported,
            createObserver: createSafeMutationObserver,
            safeObserve: safeObserve,
            addEventListener: safeAddEventListener,
            querySelector: safeQuerySelector,
            issues: compatibilityIssues
        };
    }
    
    // Initialize immediately
    initializeCompatibility();
    
    // Also initialize on DOM ready for any DOM-dependent features
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeCompatibility);
    }
    
})();
