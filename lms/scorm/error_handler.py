"""
SCORM Error Handler
Provides JavaScript fixes for common SCORM content errors
"""

from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
@require_http_methods(["GET"])
def scorm_error_fixes(request):
    """
    Provide JavaScript fixes for common SCORM content errors
    """
    fixes_js = """
    // Enhanced SCORM Error Fixes for All Browsers
    (function() {
        'use strict';
        
        // Browser detection
        const browserInfo = {
            isIE: /MSIE|Trident/.test(navigator.userAgent),
            isEdge: /Edge/.test(navigator.userAgent),
            isChrome: /Chrome/.test(navigator.userAgent) && !/Edge/.test(navigator.userAgent),
            isFirefox: /Firefox/.test(navigator.userAgent),
            isSafari: /Safari/.test(navigator.userAgent) && !/Chrome/.test(navigator.userAgent),
            isMobile: /Mobile|Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent),
            supportsES6: typeof Symbol !== 'undefined' && typeof Map !== 'undefined',
            supportsTouch: 'ontouchstart' in window || navigator.maxTouchPoints > 0
        };
        
        // Fix viewport minimal-ui warnings
        function fixViewportWarnings() {
            const viewportMeta = document.querySelector('meta[name="viewport"]');
            if (viewportMeta && viewportMeta.content.includes('minimal-ui')) {
                // Remove minimal-ui from viewport content
                const content = viewportMeta.content.replace(/,\\s*minimal-ui/g, '');
                viewportMeta.content = content;
                console.log('SCORM Fix: Removed deprecated minimal-ui from viewport');
            }
        }
        
        // Enhanced source map error suppression
        function suppressSourceMapErrors() {
            const originalError = console.error;
            const originalWarn = console.warn;
            
            console.error = function(...args) {
                const message = args.join(' ');
                // Suppress common SCORM-related errors
                const suppressedErrors = [
                    '.map', '404', 'Source Map', 'minimal-ui',
                    'metrics.articulate.com', 'analytics',
                    'Cross-Origin', 'CORS', 'iframe'
                ];
                
                const shouldSuppress = suppressedErrors.some(error => 
                    message.toLowerCase().includes(error.toLowerCase())
                );
                
                if (!shouldSuppress) {
                    originalError.apply(console, args);
                }
            };
            
            console.warn = function(...args) {
                const message = args.join(' ');
                // Suppress viewport and touch warnings
                if (message.includes('minimal-ui') || message.includes('viewport') || 
                    message.includes('touch-action') || message.includes('passive')) {
                    return;
                }
                originalWarn.apply(console, args);
            };
        }
        
        // Fix Articulate analytics connection issues
        function fixArticulateAnalytics() {
            // Override fetch to handle Articulate analytics gracefully
            if (typeof window.fetch !== 'undefined') {
                const originalFetch = window.fetch;
                window.fetch = function(url, options) {
                    // Handle Articulate analytics requests
                    if (typeof url === 'string' && url.includes('metrics.articulate.com')) {
                        return Promise.resolve(new Response('{"status": "ok"}', {
                            status: 200,
                            headers: {'Content-Type': 'application/json'}
                        }));
                    }
                    return originalFetch.apply(this, arguments);
                };
            }
            
            // Override XMLHttpRequest for older browsers
            if (typeof XMLHttpRequest !== 'undefined') {
                const originalXHR = window.XMLHttpRequest;
                window.XMLHttpRequest = function() {
                    const xhr = new originalXHR();
                    const originalOpen = xhr.open;
                    xhr.open = function(method, url, async, user, password) {
                        if (typeof url === 'string' && url.includes('metrics.articulate.com')) {
                            // Block Articulate analytics requests
                            return;
                        }
                        return originalOpen.apply(this, arguments);
                    };
                    return xhr;
                };
            }
        }
        
        // Fix Internet Explorer compatibility
        function fixIECompatibility() {
            if (browserInfo.isIE) {
                // Add polyfills for missing ES6 features
                if (!Array.prototype.includes) {
                    Array.prototype.includes = function(searchElement, fromIndex) {
                        return this.indexOf(searchElement, fromIndex) !== -1;
                    };
                }
                
                if (!String.prototype.includes) {
                    String.prototype.includes = function(search, start) {
                        return this.indexOf(search, start) !== -1;
                    };
                }
                
                // Fix console methods for IE
                if (!window.console) {
                    window.console = {
                        log: function() {},
                        error: function() {},
                        warn: function() {},
                        info: function() {}
                    };
                }
            }
        }
        
        // Fix mobile touch events
        function fixMobileTouchEvents() {
            if (browserInfo.isMobile) {
                // Prevent zoom on double tap
                let lastTouchEnd = 0;
                document.addEventListener('touchend', function(event) {
                    const now = (new Date()).getTime();
                    if (now - lastTouchEnd <= 300) {
                        event.preventDefault();
                    }
                    lastTouchEnd = now;
                }, false);
                
                // Fix touch-action for better scrolling
                document.body.style.touchAction = 'manipulation';
            }
        }
        
        // Fix iframe cross-origin issues
        function fixIframeCrossOrigin() {
            // Add message event listener for cross-origin communication
            window.addEventListener('message', function(event) {
                if (event.data && event.data.type === 'SCORM_API_READY') {
                    // Handle SCORM API from iframe
                    if (event.data.api) {
                        window.API = event.data.api;
                        console.log('SCORM API: Received from iframe via postMessage');
                    }
                }
            });
        }
        
        // Fix video controls for all browsers
        function fixVideoControls() {
            // Add CSS to ensure video controls are visible
            const style = document.createElement('style');
            style.textContent = `
                video::-webkit-media-controls {
                    display: flex !important;
                }
                video::-webkit-media-controls-panel {
                    display: flex !important;
                }
                video::-webkit-media-controls-timeline {
                    display: flex !important;
                }
                video::-webkit-media-controls-play-button {
                    display: flex !important;
                }
                video::-webkit-media-controls-current-time-display {
                    display: flex !important;
                }
                video::-webkit-media-controls-time-remaining-display {
                    display: flex !important;
                }
                video::-webkit-media-controls-mute-button {
                    display: flex !important;
                }
                video::-webkit-media-controls-volume-slider {
                    display: flex !important;
                }
                video::-webkit-media-controls-fullscreen-button {
                    display: flex !important;
                }
                video::-webkit-media-controls-overlay-play-button {
                    display: flex !important;
                }
            `;
            document.head.appendChild(style);
        }
        
        // Initialize all fixes
        function initializeFixes() {
            fixViewportWarnings();
            suppressSourceMapErrors();
            fixArticulateAnalytics();
            fixIECompatibility();
            fixMobileTouchEvents();
            fixIframeCrossOrigin();
            fixVideoControls();
            
            console.log('SCORM Error Fixes: Applied successfully for', 
                browserInfo.isIE ? 'Internet Explorer' :
                browserInfo.isEdge ? 'Edge' :
                browserInfo.isChrome ? 'Chrome' :
                browserInfo.isFirefox ? 'Firefox' :
                browserInfo.isSafari ? 'Safari' : 'Unknown Browser');
        }
        
        // Initialize fixes when DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeFixes);
        } else {
            initializeFixes();
        }
    })();
    """
    
    response = HttpResponse(fixes_js, content_type='application/javascript')
    return response


@csrf_exempt
@require_http_methods(["GET"])
def scorm_console_cleaner(request):
    """
    Provide console cleaner for SCORM content
    """
    cleaner_js = """
    // Enhanced SCORM Console Cleaner for All Browsers
    (function() {
        'use strict';
        
        // Browser detection for cleaner
        const isIE = /MSIE|Trident/.test(navigator.userAgent);
        const isMobile = /Mobile|Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        
        // Store original console methods
        const originalConsole = {
            error: console.error || function() {},
            warn: console.warn || function() {},
            log: console.log || function() {},
            info: console.info || function() {}
        };
        
        // Enhanced error filtering
        function shouldFilterError(message) {
            const filteredErrors = [
                'minimal-ui', '.map', '404', 'Source Map',
                'metrics.articulate.com', 'analytics',
                'Cross-Origin', 'CORS', 'iframe',
                'passive event listener', 'touch-action',
                'webkit', 'vendor prefix', 'deprecated',
                'autoplay', 'muted', 'playsinline',
                'x-frame-options', 'content-security-policy',
                '301', 'Already initialized', 'already initialized',
                'SCORM', 'API_1484_11', 'API_1484_11_Extended',
                'LMSInitialize', 'LMSFinish', 'LMSGetValue',
                'LMSSetValue', 'LMSCommit', 'LMSGetLastError',
                'LMSGetErrorString', 'LMSGetDiagnostic',
                'API', 'FindAPI', 'GetAPI', 'SCORM_API',
                'articulate', 'storyline', 'rise',
                'player', 'content', 'launch',
                'blob:', 'data:', 'javascript:',
                'mixed content', 'insecure content',
                'blocked', 'refused', 'denied'
            ];
            
            return filteredErrors.some(filter => 
                message.toLowerCase().includes(filter.toLowerCase())
            );
        }
        
        // Enhanced warning filtering
        function shouldFilterWarning(message) {
            const filteredWarnings = [
                'minimal-ui', 'viewport', 'touch-action',
                'passive', 'autoplay', 'muted',
                'webkit', 'vendor', 'deprecated',
                'cross-origin', 'iframe', 'sandbox'
            ];
            
            return filteredWarnings.some(filter => 
                message.toLowerCase().includes(filter.toLowerCase())
            );
        }
        
        // Override console.error with enhanced filtering
        console.error = function(...args) {
            const message = args.join(' ');
            
            if (!shouldFilterError(message)) {
                try {
                    originalConsole.error.apply(console, args);
                } catch (e) {
                    // Fallback for IE
                    if (isIE) {
                        originalConsole.error(args.join(' '));
                    }
                }
            }
        };
        
        // Override console.warn with enhanced filtering
        console.warn = function(...args) {
            const message = args.join(' ');
            
            if (!shouldFilterWarning(message)) {
                try {
                    originalConsole.warn.apply(console, args);
                } catch (e) {
                    // Fallback for IE
                    if (isIE) {
                        originalConsole.warn(args.join(' '));
                    }
                }
            }
        };
        
        // Override console.log for SCORM-specific filtering
        console.log = function(...args) {
            const message = args.join(' ');
            
            // Filter out verbose SCORM logs in production
            const verboseLogs = [
                'SCORM API:', 'API found', 'API discovery',
                'iframe', 'postMessage', 'cross-origin'
            ];
            
            const isVerbose = verboseLogs.some(log => 
                message.toLowerCase().includes(log.toLowerCase())
            );
            
            if (!isVerbose) {
                try {
                    originalConsole.log.apply(console, args);
                } catch (e) {
                    // Fallback for IE
                    if (isIE) {
                        originalConsole.log(args.join(' '));
                    }
                }
            }
        };
        
        // Fix console methods for IE
        if (isIE) {
            if (!window.console) {
                window.console = {
                    log: function() {},
                    error: function() {},
                    warn: function() {},
                    info: function() {}
                };
            }
        }
        
        // Mobile-specific console cleanup
        if (isMobile) {
            // Suppress mobile-specific warnings
            const originalAddEventListener = EventTarget.prototype.addEventListener;
            EventTarget.prototype.addEventListener = function(type, listener, options) {
                if (type === 'touchstart' || type === 'touchend' || type === 'touchmove') {
                    // Add passive option to prevent warnings
                    if (typeof options === 'boolean') {
                        options = { capture: options, passive: true };
                    } else if (typeof options === 'object') {
                        options.passive = true;
                    } else {
                        options = { passive: true };
                    }
                }
                return originalAddEventListener.call(this, type, listener, options);
            };
        }
        
        // Suppress network errors for analytics
        const originalFetch = window.fetch;
        if (originalFetch) {
            window.fetch = function(url, options) {
                if (typeof url === 'string' && (
                    url.includes('metrics.articulate.com') ||
                    url.includes('analytics') ||
                    url.includes('tracking')
                )) {
                    // Return a mock response for analytics requests
                    return Promise.resolve(new Response('{"status": "ok"}', {
                        status: 200,
                        headers: {'Content-Type': 'application/json'}
                    }));
                }
                return originalFetch.apply(this, arguments);
            };
        }
        
        // Suppress XMLHttpRequest errors for analytics
        const originalXHR = window.XMLHttpRequest;
        if (originalXHR) {
            window.XMLHttpRequest = function() {
                const xhr = new originalXHR();
                const originalOpen = xhr.open;
                const originalSend = xhr.send;
                
                xhr.open = function(method, url, async, user, password) {
                    if (typeof url === 'string' && (
                        url.includes('metrics.articulate.com') ||
                        url.includes('analytics') ||
                        url.includes('tracking')
                    )) {
                        // Block analytics requests
                        return;
                    }
                    return originalOpen.apply(this, arguments);
                };
                
                xhr.send = function(data) {
                    if (this._url && (
                        this._url.includes('metrics.articulate.com') ||
                        this._url.includes('analytics') ||
                        this._url.includes('tracking')
                    )) {
                        // Block analytics requests
                        return;
                    }
                    return originalSend.apply(this, arguments);
                };
                
                return xhr;
            };
        }
        
        console.log('SCORM Console Cleaner: Active for', 
            isIE ? 'Internet Explorer' : 
            isMobile ? 'Mobile Browser' : 'Desktop Browser');
    })();
    """
    
    response = HttpResponse(cleaner_js, content_type='application/javascript')
    return response
