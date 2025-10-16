/**
 * TinyMCE ES5 Compatibility Script
 * Provides ES5-compatible polyfills and fixes for TinyMCE to work in older browsers
 */

(function() {
    'use strict';
    
    
    // Add Array.from polyfill for older browsers
    if (!Array.from) {
        Array.from = function(arrayLike) {
            return Array.prototype.slice.call(arrayLike || []);
        };
    }
    
    // Add Object.assign polyfill
    if (typeof Object.assign !== 'function') {
        Object.assign = function(target) {
            if (target === null || target === undefined) {
                throw new TypeError('Cannot convert undefined or null to object');
            }
            
            var to = Object(target);
            
            for (var index = 1; index < arguments.length; index++) {
                var nextSource = arguments[index];
                
                if (nextSource !== null && nextSource !== undefined) {
                    for (var nextKey in nextSource) {
                        if (Object.prototype.hasOwnProperty.call(nextSource, nextKey)) {
                            to[nextKey] = nextSource[nextKey];
                        }
                    }
                }
            }
            
            return to;
        };
    }
    
    // Add String.includes polyfill
    if (!String.prototype.includes) {
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
    
    // Add Array.includes polyfill
    if (!Array.prototype.includes) {
        Array.prototype.includes = function(searchElement, fromIndex) {
            return this.indexOf(searchElement, fromIndex) !== -1;
        };
    }
    
    // TinyMCE specific patches
    function patchTinyMCE() {
        if (typeof tinymce === 'undefined') {
            setTimeout(patchTinyMCE, 500);
            return;
        }
        
        
        // Patch innerWidth issues with null elements
        var originalGetSize = tinymce.DOM.getSize;
        tinymce.DOM.getSize = function(elm, w, h) {
            try {
                if (!elm) return { width: 0, height: 0 };
                return originalGetSize.call(this, elm, w, h);
            } catch (e) {
                return { width: 0, height: 0 };
            }
        };
        
        // Override DOM functions that might use innerWidth
        var originalGetClientWidth = tinymce.DOM.getClientWidth;
        tinymce.DOM.getClientWidth = function() {
            try {
                return originalGetClientWidth.apply(this, arguments);
            } catch (e) {
                return window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth || 800;
            }
        };
        
        var originalGetClientHeight = tinymce.DOM.getClientHeight;
        tinymce.DOM.getClientHeight = function() {
            try {
                return originalGetClientHeight.apply(this, arguments);
            } catch (e) {
                return window.innerHeight || document.documentElement.clientHeight || document.body.clientHeight || 600;
            }
        };
        
        // Patch createElement to handle SVG elements safely
        var originalCreateElement = tinymce.DOM.create;
        tinymce.DOM.create = function(name, attrs, html) {
            try {
                return originalCreateElement.call(this, name, attrs, html);
            } catch (e) {
                var elm = document.createElement(name);
                if (attrs) {
                    for (var key in attrs) {
                        if (attrs.hasOwnProperty(key)) {
                            elm.setAttribute(key, attrs[key]);
                        }
                    }
                }
                if (html) {
                    elm.innerHTML = html;
                }
                return elm;
            }
        };
        
        // Add special handling for TinyMCE plugin loading errors
        var originalLoadScript = tinymce.ScriptLoader.prototype.loadScript;
        if (originalLoadScript) {
            tinymce.ScriptLoader.prototype.loadScript = function(url, callback, scope) {
                try {
                    // Check if this is a plugin URL
                    if (url.indexOf('/plugin.min.js') !== -1 || url.indexOf('/plugins/') !== -1) {
                        var originalCallback = callback;
                        callback = function() {
                            try {
                                if (originalCallback) {
                                    originalCallback.apply(scope || this, arguments);
                                }
                            } catch (e) {
                                // Continue with empty plugin to avoid breaking the editor
                                return;
                            }
                        };
                    }
                    
                    // Set a timeout for loading scripts
                    var scriptTimeout = setTimeout(function() {
                        if (callback) {
                            callback.call(scope || this, null);
                        }
                    }, 10000); // 10 second timeout
                    
                    var originalResult = originalLoadScript.call(this, url, function() {
                        clearTimeout(scriptTimeout);
                        if (callback) {
                            callback.apply(scope || this, arguments);
                        }
                    }, scope);
                    
                    return originalResult;
                } catch (e) {
                    // Try to continue anyway
                    if (callback) {
                        setTimeout(function() {
                            callback.call(scope || this, null);
                        }, 100);
                    }
                }
            };
        }
        
    }
    
    // Try to patch TinyMCE when the page loads
    if (document.readyState === 'complete') {
        patchTinyMCE();
    } else {
        window.addEventListener('load', patchTinyMCE);
    }
    
    // Also try to patch TinyMCE after a delay in case it loads dynamically
    setTimeout(patchTinyMCE, 1000);
    setTimeout(patchTinyMCE, 2000);
    setTimeout(patchTinyMCE, 5000);
})(); 