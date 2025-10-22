/**
 * Robust HTTP Service for Chart Components
 * Handles all chart-related HTTP requests with retry logic, circuit breaker, and fallback data
 */
class ChartHttpService {
    constructor() {
        this.circuitBreaker = {
            failures: 0,
            threshold: 3,
            timeout: 30000, // 30 seconds
            state: 'CLOSED' // CLOSED, OPEN, HALF_OPEN
        };
        
        this.retryConfig = {
            maxRetries: 3,
            baseDelay: 1000,
            maxDelay: 8000,
            jitter: true
        };
        
        this.cache = new Map();
        this.cacheTimeout = 300000; // 5 minutes
        
        // Fallback data for different chart types - will be dynamically generated
        this.fallbackData = {
            courses: {
                completed: 0,
                inProgress: 0,
                notStarted: 0,
                notPassed: 0,
                fallback: true
            }
        };
    }

    /**
     * Main method to make HTTP requests with all robustness features
     */
    async makeRequest(url, options = {}) {
        const cacheKey = this.getCacheKey(url, options);
        
        // Check cache first
        if (this.cache.has(cacheKey)) {
            const cached = this.cache.get(cacheKey);
            if (Date.now() - cached.timestamp < this.cacheTimeout) {
                console.log('Using cached data for:', url);
                return cached.data;
            }
            this.cache.delete(cacheKey);
        }

        // Check circuit breaker
        if (this.circuitBreaker.state === 'OPEN') {
            if (Date.now() - this.circuitBreaker.lastFailure < this.circuitBreaker.timeout) {
                console.warn('Circuit breaker OPEN - using fallback data');
                return this.getFallbackData(url);
            } else {
                this.circuitBreaker.state = 'HALF_OPEN';
                console.log('Circuit breaker moving to HALF_OPEN state');
            }
        }

        try {
            const result = await this.executeWithRetry(url, options);
            
            // Reset circuit breaker on success
            this.circuitBreaker.failures = 0;
            this.circuitBreaker.state = 'CLOSED';
            
            // Cache successful result
            this.cache.set(cacheKey, {
                data: result,
                timestamp: Date.now()
            });
            
            return result;
            
        } catch (error) {
            this.handleCircuitBreakerFailure();
            console.error('All retry attempts failed for:', url, error);
            return this.getFallbackData(url);
        }
    }

    /**
     * Execute request with exponential backoff retry
     */
    async executeWithRetry(url, options, attempt = 0) {
        const { maxRetries, baseDelay, maxDelay, jitter } = this.retryConfig;
        
        try {
            return await this.executeRequest(url, options);
        } catch (error) {
            if (attempt >= maxRetries || !this.isRetryableError(error)) {
                throw error;
            }
            
            const delay = this.calculateDelay(attempt, baseDelay, maxDelay, jitter);
            console.warn(`Request failed (attempt ${attempt + 1}/${maxRetries + 1}), retrying in ${delay}ms:`, error.message);
            
            await this.sleep(delay);
            return this.executeWithRetry(url, options, attempt + 1);
        }
    }

    /**
     * Execute a single HTTP request
     */
    async executeRequest(url, options = {}) {
        const defaultOptions = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            },
            credentials: 'same-origin',
            signal: AbortSignal.timeout(30000) // 30 second timeout
        };

        const requestOptions = { ...defaultOptions, ...options };
        
        console.log('Making HTTP request to:', url);
        
        const response = await fetch(url, requestOptions);
        
        console.log('Response received:', {
            status: response.status,
            statusText: response.statusText,
            ok: response.ok,
            url: response.url
        });
        
        if (!response.ok) {
            const status = response.status || 'Unknown';
            const statusText = response.statusText || 'Unknown Error';
            const error = new Error(`HTTP ${status}: ${statusText}`);
            error.status = response.status;
            error.response = response;
            console.error('HTTP request failed:', error);
            throw error;
        }

        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            // Check if it's an HTML redirect (login page)
            const text = await response.text();
            if (text.trim().startsWith('<!DOCTYPE html') || text.includes('<html')) {
                const error = new Error('Authentication required');
                error.status = 401;
                error.isAuthError = true;
                throw error;
            }
            throw new Error('Response is not JSON');
        }

        return await response.json();
    }

    /**
     * Check if error is retryable
     */
    isRetryableError(error) {
        if (error.isAuthError) return false;
        
        const retryableStatuses = [408, 429, 500, 502, 503, 504];
        const retryableErrors = [
            'TypeError',
            'AbortError',
            'NetworkError',
            'Failed to fetch'
        ];
        
        return retryableStatuses.includes(error.status) || 
               retryableErrors.some(errType => 
                   error.name === errType || 
                   error.message.includes(errType)
               );
    }

    /**
     * Calculate delay with exponential backoff and jitter
     */
    calculateDelay(attempt, baseDelay, maxDelay, jitter) {
        let delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);
        if (jitter) {
            delay += Math.random() * 1000; // Add up to 1 second jitter
        }
        return Math.floor(delay);
    }

    /**
     * Handle circuit breaker failure
     */
    handleCircuitBreakerFailure() {
        this.circuitBreaker.failures++;
        this.circuitBreaker.lastFailure = Date.now();
        
        if (this.circuitBreaker.failures >= this.circuitBreaker.threshold) {
            this.circuitBreaker.state = 'OPEN';
            console.warn('Circuit breaker OPEN - too many failures');
        }
    }

    /**
     * Get fallback data based on URL pattern and period
     */
    getFallbackData(url) {
        if (url.includes('activity-data')) {
            return this.generateActivityFallbackData(url);
        } else if (url.includes('course') || url.includes('progress')) {
            return this.fallbackData.courses;
        }
        
        // Generic fallback
        return {
            labels: [],
            data: [],
            fallback: true,
            error: 'Service temporarily unavailable'
        };
    }

    /**
     * Generate period-appropriate fallback data for activity charts
     */
    generateActivityFallbackData(url) {
        // Extract period from URL
        const urlParams = new URLSearchParams(url.split('?')[1] || '');
        const period = urlParams.get('period') || 'month';
        
        let labels = [];
        
        if (period === 'week') {
            // Current week days
            const today = new Date();
            const daysSinceMonday = (today.getDay() + 6) % 7; // Convert Sunday=0 to Monday=0
            const monday = new Date(today);
            monday.setDate(today.getDate() - daysSinceMonday);
            
            for (let i = 0; i < 7; i++) {
                const day = new Date(monday);
                day.setDate(monday.getDate() + i);
                labels.push(`${day.toLocaleDateString('en', {weekday: 'short'})} ${day.getDate()}`);
            }
        } else if (period === 'year') {
            // Current year months
            labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        } else {
            // Current month days (month period)
            const today = new Date();
            const currentDay = today.getDate();
            for (let i = 1; i <= currentDay; i++) {
                labels.push(i.toString());
            }
        }
        
        return {
            labels: labels,
            logins: new Array(labels.length).fill(0),
            completions: new Array(labels.length).fill(0),
            fallback: true,
            error: 'No data available for this period'
        };
    }

    /**
     * Get CSRF token from page
     */
    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (!token) {
            console.warn('CSRF token not found');
        }
        return token || '';
    }

    /**
     * Generate cache key
     */
    getCacheKey(url, options) {
        const params = new URLSearchParams(options.params || {});
        return `${url}?${params.toString()}`;
    }

    /**
     * Sleep utility
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Clear cache
     */
    clearCache() {
        this.cache.clear();
        console.log('Chart HTTP service cache cleared');
    }

    /**
     * Get service status
     */
    getStatus() {
        return {
            circuitBreaker: this.circuitBreaker,
            cacheSize: this.cache.size,
            retryConfig: this.retryConfig
        };
    }
}

// Create global instance
window.chartHttpService = new ChartHttpService();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChartHttpService;
}
