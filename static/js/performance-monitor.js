/**
 * Performance Monitor - Tracks page performance metrics
 */
(function() {
    'use strict';
    
    const PerformanceMonitor = {
        metrics: {},
        
        init: function() {
            this.trackPageLoad();
            this.trackUserInteractions();
        },
        
        trackPageLoad: function() {
            if (window.performance && window.performance.timing) {
                const timing = window.performance.timing;
                this.metrics.loadTime = timing.loadEventEnd - timing.navigationStart;
                this.metrics.domReady = timing.domContentLoadedEventEnd - timing.navigationStart;
                this.metrics.firstByte = timing.responseStart - timing.navigationStart;
            }
        },
        
        trackUserInteractions: function() {
            try {
                // Track form submissions
                document.addEventListener('submit', function(e) {
                    try {
                        // Track form submission metrics
                        // Debug logging removed for production
                    } catch (error) {
                        console.error('Error tracking form submission:', error);
                    }
                });
                
                // Track navigation clicks
                document.addEventListener('click', function(e) {
                    try {
                        if (e.target.tagName === 'A') {
                            // Track navigation metrics
                            if (window.DEBUG_MODE) {
                                // Debug logging removed for production
                            }
                        }
                    } catch (error) {
                        console.error('Error tracking navigation click:', error);
                    }
                });
            } catch (error) {
                console.error('Error setting up user interaction tracking:', error);
            }
        },
        
        getMetrics: function() {
            return this.metrics;
        }
    };
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            PerformanceMonitor.init();
        });
    } else {
        PerformanceMonitor.init();
    }
    
    // Export to global scope
    window.PerformanceMonitor = PerformanceMonitor;
})();
