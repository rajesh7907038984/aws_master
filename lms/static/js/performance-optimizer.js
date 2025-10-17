/**
 * Performance Optimizer for 100% Frontend-Backend Alignment
 * This system optimizes performance while maintaining perfect alignment
 */

class PerformanceOptimizer {
    constructor() {
        this.cache = new Map();
        this.debounceTimers = new Map();
        this.throttleTimers = new Map();
        this.observers = new Map();
        this.lazyLoadElements = new Set();
        
        this.setupOptimizations();
    }
    
    /**
     * Setup all performance optimizations
     */
    setupOptimizations() {
        this.setupLazyLoading();
        this.setupImageOptimization();
        this.setupFormOptimization();
        this.setupScrollOptimization();
        this.setupResizeOptimization();
        this.setupMemoryOptimization();
    }
    
    /**
     * Setup lazy loading for images and content
     */
    setupLazyLoading() {
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        if (img.dataset.src) {
                            img.src = img.dataset.src;
                            img.classList.remove('lazy');
                            imageObserver.unobserve(img);
                        }
                    }
                });
            });
            
            // Observe all lazy images
            document.querySelectorAll('img[data-src]').forEach(img => {
                imageObserver.observe(img);
            });
        }
    }
    
    /**
     * Setup image optimization
     */
    setupImageOptimization() {
        // Add loading="lazy" to all images
        document.querySelectorAll('img:not([loading])').forEach(img => {
            img.loading = 'lazy';
        });
        
        // Optimize image sizes based on viewport
        this.optimizeImageSizes();
    }
    
    /**
     * Optimize image sizes based on viewport
     */
    optimizeImageSizes() {
        const viewportWidth = window.innerWidth;
        const devicePixelRatio = window.devicePixelRatio || 1;
        
        document.querySelectorAll('img[data-sizes]').forEach(img => {
            const sizes = JSON.parse(img.dataset.sizes);
            const optimalSize = this.getOptimalImageSize(sizes, viewportWidth, devicePixelRatio);
            
            if (optimalSize && img.src !== optimalSize) {
                img.src = optimalSize;
            }
        });
    }
    
    /**
     * Get optimal image size based on viewport
     */
    getOptimalImageSize(sizes, viewportWidth, devicePixelRatio) {
        const sortedSizes = Object.keys(sizes)
            .map(size => parseInt(size))
            .sort((a, b) => a - b);
        
        for (const size of sortedSizes) {
            if (size * devicePixelRatio >= viewportWidth) {
                return sizes[size];
            }
        }
        
        return sizes[sortedSizes[sortedSizes.length - 1]];
    }
    
    /**
     * Setup form optimization
     */
    setupFormOptimization() {
        // Debounce form inputs
        document.querySelectorAll('input, textarea').forEach(input => {
            input.addEventListener('input', this.debounce((event) => {
                this.handleFormInput(event.target);
            }, 300));
        });
        
        // Optimize form submissions
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', (event) => {
                this.optimizeFormSubmission(event);
            });
        });
    }
    
    /**
     * Handle form input optimization
     */
    handleFormInput(input) {
        // Auto-save functionality
        if (input.dataset.autoSave === 'true') {
            this.autoSave(input);
        }
        
        // Real-time validation
        if (typeof validateField === 'function') {
            validateField(input);
        }
    }
    
    /**
     * Auto-save form data
     */
    autoSave(input) {
        const form = input.closest('form');
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        
        localStorage.setItem(`autosave_${form.id || 'form'}`, JSON.stringify({
            data: data,
            timestamp: Date.now()
        }));
    }
    
    /**
     * Optimize form submission
     */
    optimizeFormSubmission(event) {
        const form = event.target;
        
        // Prevent double submission
        if (form.dataset.submitting === 'true') {
            event.preventDefault();
            return false;
        }
        
        form.dataset.submitting = 'true';
        
        // Add loading state
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent = 'Submitting...';
        }
        
        // Clear auto-save data on successful submission
        setTimeout(() => {
            localStorage.removeItem(`autosave_${form.id || 'form'}`);
        }, 1000);
    }
    
    /**
     * Setup scroll optimization
     */
    setupScrollOptimization() {
        let scrollTimeout;
        
        window.addEventListener('scroll', this.throttle(() => {
            this.handleScroll();
        }, 16)); // ~60fps
        
        // Handle scroll end
        window.addEventListener('scroll', () => {
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(() => {
                this.handleScrollEnd();
            }, 150);
        });
    }
    
    /**
     * Handle scroll events
     */
    handleScroll() {
        // Update scroll position indicators
        const scrollTop = window.pageYOffset;
        const scrollHeight = document.documentElement.scrollHeight;
        const clientHeight = window.innerHeight;
        const scrollPercent = (scrollTop / (scrollHeight - clientHeight)) * 100;
        
        // Update progress indicators
        document.querySelectorAll('.scroll-progress').forEach(indicator => {
            indicator.style.width = `${scrollPercent}%`;
        });
    }
    
    /**
     * Handle scroll end
     */
    handleScrollEnd() {
        // Lazy load content that came into view
        this.lazyLoadContent();
    }
    
    /**
     * Setup resize optimization
     */
    setupResizeOptimization() {
        window.addEventListener('resize', this.debounce(() => {
            this.handleResize();
        }, 250));
    }
    
    /**
     * Handle resize events
     */
    handleResize() {
        // Recalculate image sizes
        this.optimizeImageSizes();
        
        // Update responsive elements
        this.updateResponsiveElements();
    }
    
    /**
     * Update responsive elements
     */
    updateResponsiveElements() {
        const viewportWidth = window.innerWidth;
        
        document.querySelectorAll('[data-responsive]').forEach(element => {
            const breakpoints = JSON.parse(element.dataset.responsive);
            const currentBreakpoint = this.getCurrentBreakpoint(breakpoints, viewportWidth);
            
            if (currentBreakpoint) {
                element.className = currentBreakpoint.classes;
            }
        });
    }
    
    /**
     * Get current breakpoint
     */
    getCurrentBreakpoint(breakpoints, viewportWidth) {
        const sortedBreakpoints = Object.keys(breakpoints)
            .map(bp => parseInt(bp))
            .sort((a, b) => a - b);
        
        for (let i = sortedBreakpoints.length - 1; i >= 0; i--) {
            if (viewportWidth >= sortedBreakpoints[i]) {
                return breakpoints[sortedBreakpoints[i]];
            }
        }
        
        return breakpoints[sortedBreakpoints[0]];
    }
    
    /**
     * Setup memory optimization
     */
    setupMemoryOptimization() {
        // Clean up unused observers
        setInterval(() => {
            this.cleanupObservers();
        }, 30000); // Every 30 seconds
        
        // Monitor memory usage
        if ('memory' in performance) {
            setInterval(() => {
                this.monitorMemoryUsage();
            }, 60000); // Every minute
        }
    }
    
    /**
     * Clean up unused observers
     */
    cleanupObservers() {
        this.observers.forEach((observer, key) => {
            if (observer.targets.length === 0) {
                observer.disconnect();
                this.observers.delete(key);
            }
        });
    }
    
    /**
     * Monitor memory usage
     */
    monitorMemoryUsage() {
        if ('memory' in performance) {
            const memory = performance.memory;
            const usedMB = memory.usedJSHeapSize / 1024 / 1024;
            const totalMB = memory.totalJSHeapSize / 1024 / 1024;
            
            if (usedMB / totalMB > 0.8) {
                console.warn('High memory usage detected:', {
                    used: `${usedMB.toFixed(2)}MB`,
                    total: `${totalMB.toFixed(2)}MB`,
                    percentage: `${((usedMB / totalMB) * 100).toFixed(1)}%`
                });
                
                // Trigger garbage collection if available
                if (window.gc) {
                    window.gc();
                }
            }
        }
    }
    
    /**
     * Debounce function
     */
    debounce(func, wait) {
        return (...args) => {
            const key = func.toString();
            clearTimeout(this.debounceTimers.get(key));
            this.debounceTimers.set(key, setTimeout(() => func.apply(this, args), wait));
        };
    }
    
    /**
     * Throttle function
     */
    throttle(func, limit) {
        return (...args) => {
            const key = func.toString();
            if (!this.throttleTimers.has(key)) {
                func.apply(this, args);
                this.throttleTimers.set(key, setTimeout(() => {
                    this.throttleTimers.delete(key);
                }, limit));
            }
        };
    }
    
    /**
     * Cache function results
     */
    memoize(func, keyGenerator) {
        return (...args) => {
            const key = keyGenerator ? keyGenerator(...args) : JSON.stringify(args);
            
            if (this.cache.has(key)) {
                return this.cache.get(key);
            }
            
            const result = func.apply(this, args);
            this.cache.set(key, result);
            
            // Limit cache size
            if (this.cache.size > 100) {
                const firstKey = this.cache.keys().next().value;
                this.cache.delete(firstKey);
            }
            
            return result;
        };
    }
    
    /**
     * Preload critical resources
     */
    preloadCriticalResources() {
        const criticalResources = [
            '/static/css/tailwind.css',
            '/static/core/css/style.css',
            '/static/js/standardized-api-client.js',
            '/static/js/unified-error-handler.js'
        ];
        
        criticalResources.forEach(resource => {
            const link = document.createElement('link');
            link.rel = 'preload';
            link.href = resource;
            link.as = resource.endsWith('.css') ? 'style' : 'script';
            document.head.appendChild(link);
        });
    }
    
    /**
     * Optimize API calls
     */
    optimizeAPICalls() {
        // Batch multiple API calls
        const apiCallQueue = [];
        let batchTimeout;
        
        const batchAPICalls = () => {
            if (apiCallQueue.length > 0) {
                // Process batched calls
                this.processBatchedAPICalls(apiCallQueue.splice(0));
            }
        };
        
        // Override fetch to batch calls
        const originalFetch = window.fetch;
        window.fetch = (...args) => {
            const url = args[0];
            if (url.includes('/api/')) {
                apiCallQueue.push(args);
                clearTimeout(batchTimeout);
                batchTimeout = setTimeout(batchAPICalls, 100);
            }
            return originalFetch.apply(this, args);
        };
    }
    
    /**
     * Process batched API calls
     */
    processBatchedAPICalls(calls) {
        // Group calls by endpoint
        const groupedCalls = {};
        calls.forEach(call => {
            const url = call[0];
            const endpoint = url.split('/api/')[1].split('/')[0];
            if (!groupedCalls[endpoint]) {
                groupedCalls[endpoint] = [];
            }
            groupedCalls[endpoint].push(call);
        });
        
        // Process each group
        Object.keys(groupedCalls).forEach(endpoint => {
            this.processEndpointCalls(endpoint, groupedCalls[endpoint]);
        });
    }
    
    /**
     * Process calls for a specific endpoint
     */
    processEndpointCalls(endpoint, calls) {
        // For now, just execute calls normally
        // This could be enhanced to batch similar calls
        calls.forEach(call => {
            fetch.apply(this, call);
        });
    }
}

// Create global instance
window.PerformanceOptimizer = PerformanceOptimizer;
window.performanceOptimizer = new PerformanceOptimizer();

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ Performance Optimizer initialized');
    
    // Preload critical resources
    window.performanceOptimizer.preloadCriticalResources();
});