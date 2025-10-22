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
            // Track form submissions
            document.addEventListener('submit', function(e) {
                console.log('Form submitted:', e.target.action || 'unknown');
            });
            
            // Track navigation clicks
            document.addEventListener('click', function(e) {
                if (e.target.tagName === 'A') {
                    console.log('Link clicked:', e.target.href || 'unknown');
                }
            });
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
