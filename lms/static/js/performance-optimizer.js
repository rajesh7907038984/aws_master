/**
 * Performance Optimizer for LMS
 * Optimizes page performance and resource loading
 */

(function() {
    'use strict';

    const PerformanceOptimizer = {
        init: function() {
            this.optimizeImages();
            this.optimizeScripts();
            this.optimizeCSS();
            this.setupLazyLoading();
            this.setupScrollHandler();
        },
        
        optimizeImages: function() {
            // Add loading="lazy" to images below the fold
            const images = document.querySelectorAll('img:not([loading])');
            images.forEach((img, index) => {
                if (index > 3) { // Skip first 4 images
                    img.setAttribute('loading', 'lazy');
                }
            });
        },
        
        optimizeScripts: function() {
            // Add defer to non-critical scripts
            const scripts = document.querySelectorAll('script:not([defer]):not([async])');
            scripts.forEach(script => {
                if (!script.src.includes('critical') && !script.src.includes('jquery')) {
                    script.defer = true;
                }
            });
        },
        
        optimizeCSS: function() {
            // Preload critical CSS
            const criticalCSS = document.querySelector('link[rel="stylesheet"][href*="critical"]');
            if (criticalCSS) {
                const preloadLink = document.createElement('link');
                preloadLink.rel = 'preload';
                preloadLink.href = criticalCSS.href;
                preloadLink.as = 'style';
                document.head.insertBefore(preloadLink, criticalCSS);
            }
        },
        
        setupLazyLoading: function() {
            // Intersection Observer for lazy loading
            if ('IntersectionObserver' in window) {
                const observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const img = entry.target;
                            if (img.dataset.src) {
                                img.src = img.dataset.src;
                                img.removeAttribute('data-src');
                                observer.unobserve(img);
                            }
                        }
                    });
                });
                
                document.querySelectorAll('img[data-src]').forEach(img => {
                    observer.observe(img);
                });
            }
        },
        
        setupScrollHandler: function() {
            // Add scroll event listener with proper context binding
            const self = this;
            window.addEventListener('scroll', this.throttle(function() {
                self.handleScrollEnd();
            }, 100));
        },
        
        debounce: function(func, wait) {
            let timeout = null;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },
        
        throttle: function(func, limit) {
            let inThrottle = false;
            return function() {
                const args = arguments;
                const context = this;
                if (!inThrottle) {
                    func.apply(context, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        },
        
        lazyLoadContent: function() {
            // Lazy load content when scrolling
            const contentElements = document.querySelectorAll('[data-lazy-content]');
            contentElements.forEach(element => {
                if (element.getBoundingClientRect().top < window.innerHeight) {
                    const content = element.dataset.lazyContent;
                    if (content) {
                        // Use textContent for security - content should be pre-sanitized
                        element.textContent = content;
                        element.removeAttribute('data-lazy-content');
                    }
                }
            });
        },
        
        handleScrollEnd: function() {
            // Lazy load content when scrolling
            const contentElements = document.querySelectorAll('[data-lazy-content]');
            contentElements.forEach(element => {
                if (element.getBoundingClientRect().top < window.innerHeight) {
                    const content = element.dataset.lazyContent;
                    if (content) {
                        // Use textContent for security - content should be pre-sanitized
                        element.textContent = content;
                        element.removeAttribute('data-lazy-content');
                    }
                }
            });
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            PerformanceOptimizer.init();
        });
    } else {
        PerformanceOptimizer.init();
    }

    // Export to global scope
    window.PerformanceOptimizer = PerformanceOptimizer;
})();