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
    // SCORM Error Fixes
    (function() {
        'use strict';
        
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
        
        // Suppress source map errors
        function suppressSourceMapErrors() {
            const originalError = console.error;
            console.error = function(...args) {
                const message = args.join(' ');
                // Suppress source map 404 errors
                if (message.includes('.map') && message.includes('404')) {
                    return; // Don't log source map errors
                }
                originalError.apply(console, args);
            };
        }
        
        // Fix Articulate analytics connection issues
        function fixArticulateAnalytics() {
            // Override fetch to handle Articulate analytics gracefully
            const originalFetch = window.fetch;
            window.fetch = function(url, options) {
                // Handle Articulate analytics requests
                if (url.includes('metrics.articulate.com')) {
                    return Promise.resolve(new Response('{"status": "ok"}', {
                        status: 200,
                        headers: {'Content-Type': 'application/json'}
                    }));
                }
                return originalFetch.apply(this, arguments);
            };
        }
        
        // Initialize fixes when DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                fixViewportWarnings();
                suppressSourceMapErrors();
                fixArticulateAnalytics();
            });
        } else {
            fixViewportWarnings();
            suppressSourceMapErrors();
            fixArticulateAnalytics();
        }
        
        console.log('SCORM Error Fixes: Applied successfully');
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
    // SCORM Console Cleaner
    (function() {
        'use strict';
        
        // Store original console methods
        const originalConsole = {
            error: console.error,
            warn: console.warn,
            log: console.log
        };
        
        // Override console.error to filter SCORM-related errors
        console.error = function(...args) {
            const message = args.join(' ');
            
            // Filter out common SCORM errors that don't affect functionality
            const filteredErrors = [
                'minimal-ui',
                '.map',
                '404',
                'metrics.articulate.com',
                'Source Map'
            ];
            
            const shouldFilter = filteredErrors.some(filter => 
                message.toLowerCase().includes(filter.toLowerCase())
            );
            
            if (!shouldFilter) {
                originalConsole.error.apply(console, args);
            }
        };
        
        // Override console.warn for viewport warnings
        console.warn = function(...args) {
            const message = args.join(' ');
            
            if (message.includes('minimal-ui') || message.includes('viewport')) {
                return; // Don't show viewport warnings
            }
            
            originalConsole.warn.apply(console, args);
        };
        
        console.log('SCORM Console Cleaner: Active');
    })();
    """
    
    response = HttpResponse(cleaner_js, content_type='application/javascript')
    return response
