/**
 * Unified Chart Service
 * Centralized service for all chart operations with robust error handling
 */
class UnifiedChartService {
    constructor() {
        this.httpService = window.chartHttpService;
        this.charts = new Map();
        this.canvasRegistry = new Map(); // Track which canvases are in use
        this.defaultConfig = {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: {
                    top: 20,
                    right: 20,
                    bottom: 20,
                    left: 20
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        padding: 20,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                },
                tooltip: {
                    enabled: true,
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#ffffff',
                    bodyColor: '#ffffff',
                    borderColor: '#ffffff',
                    borderWidth: 1,
                    cornerRadius: 6,
                    displayColors: true
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 0,
                        padding: 10
                    }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0,0,0,0.1)',
                        drawBorder: false
                    },
                    ticks: {
                        padding: 10,
                        stepSize: 1,
                        callback: function(value) {
                            return Number.isInteger(value) ? value : '';
                        }
                    }
                }
            }
        };
    }

    /**
     * Initialize activity chart with robust error handling
     */
    async initializeActivityChart(canvasId, options = {}) {
        const config = {
            canvasId: canvasId || 'activity-chart',
            apiEndpoint: options.apiEndpoint || '/users/api/dashboard-activity-data/',
            defaultPeriod: options.defaultPeriod || 'month',
            ...options
        };

        try {
            console.log('Initializing activity chart with config:', config);
            
            // Check if Chart.js is available
            if (typeof Chart === 'undefined') {
                throw new Error('Chart.js library not loaded');
            }

            // Check if canvas exists
            const canvas = document.getElementById(config.canvasId);
            if (!canvas) {
                throw new Error(`Canvas element '${config.canvasId}' not found`);
            }

            // Check if there's already a working chart managed by global activity chart
            if (window.globalActivityChart && window.globalActivityChart.canvas && 
                window.globalActivityChart.canvas.id === config.canvasId) {
                console.log(`Canvas ${config.canvasId} already managed by GlobalActivityChart, skipping unified service initialization`);
                return null;
            }

            // Destroy existing chart if present
            if (this.charts.has(config.canvasId)) {
                console.log(`Destroying existing chart for canvas: ${config.canvasId}`);
                this.destroyChart(config.canvasId);
            }
            
            // Check for any Chart.js instances on this canvas
            const existingChart = Chart.getChart(canvas);
            if (existingChart) {
                console.log(`Found existing Chart.js instance on canvas: ${config.canvasId}, destroying...`);
                existingChart.destroy();
            }
            
            // Mark canvas as in use
            this.canvasRegistry.set(config.canvasId, true);

            // Create chart instance
            const chartInstance = new ActivityChartInstance(config, this.httpService);
            await chartInstance.initialize();
            
            this.charts.set(config.canvasId, chartInstance);
            
            console.log('Activity chart initialized successfully');
            return chartInstance;
            
        } catch (error) {
            console.error('Failed to initialize activity chart:', error);
            this.showChartError(config.canvasId, 'Failed to load activity chart: ' + error.message);
            return null;
        }
    }

    /**
     * Initialize courses chart with robust error handling
     */
    async initializeCoursesChart(canvasId, options = {}) {
        const config = {
            canvasId: canvasId || 'courses-chart',
            data: options.data || null,
            ...options
        };

        try {
            console.log('Initializing courses chart with config:', config);
            
            // Check if Chart.js is available
            if (typeof Chart === 'undefined') {
                throw new Error('Chart.js library not loaded');
            }

            // Check if canvas exists
            const canvas = document.getElementById(config.canvasId);
            if (!canvas) {
                throw new Error(`Canvas element '${config.canvasId}' not found`);
            }

            // Destroy existing chart if present
            if (this.charts.has(config.canvasId)) {
                this.destroyChart(config.canvasId);
            }

            // Create chart instance
            const chartInstance = new CoursesChartInstance(config, this.httpService);
            await chartInstance.initialize();
            
            this.charts.set(config.canvasId, chartInstance);
            
            console.log('Courses chart initialized successfully');
            return chartInstance;
            
        } catch (error) {
            console.error('Failed to initialize courses chart:', error);
            this.showChartError(config.canvasId, 'Failed to load courses chart: ' + error.message);
            return null;
        }
    }

    /**
     * Update chart period
     */
    async updateChartPeriod(canvasId, period) {
        const chartInstance = this.charts.get(canvasId);
        if (chartInstance && typeof chartInstance.updatePeriod === 'function') {
            try {
                await chartInstance.updatePeriod(period);
            } catch (error) {
                console.error('Failed to update chart period:', error);
            }
        }
    }

    /**
     * Setup unified period selector for activity charts
     */
    setupActivityPeriodSelector(canvasId) {
        const periodSelector = document.getElementById('activity-period');
        if (periodSelector && this.charts.has(canvasId)) {
            // Check if period selector already has a chart listener
            if (periodSelector.hasAttribute('data-chart-listener-attached')) {
                console.log('Period selector already has event listener, skipping unified service setup');
                return;
            }
            
            console.log(`Setting up unified service period selector for: ${canvasId}`);
            const periodChangeHandler = (event) => {
                const selectedPeriod = event.target.value;
                console.log(`Unified service period changed to: ${selectedPeriod} for chart: ${canvasId}`);
                
                // Prevent multiple simultaneous updates
                if (event.target.hasAttribute('data-updating')) {
                    console.log('Period update already in progress, ignoring unified service update');
                    return;
                }
                
                this.updateChartPeriod(canvasId, selectedPeriod);
            };
            
            periodSelector.addEventListener('change', periodChangeHandler);
            periodSelector.setAttribute('data-chart-listener-attached', 'unified-service');
            
            // Store reference for cleanup
            periodSelector._unifiedServiceHandler = periodChangeHandler;
        }
    }

    /**
     * Destroy chart instance
     */
    destroyChart(canvasId) {
        const chart = this.charts.get(canvasId);
        if (chart) {
            console.log(`Destroying chart for canvas: ${canvasId}`);
            if (typeof chart.destroy === 'function') {
                chart.destroy();
            }
            this.charts.delete(canvasId);
        }
        
        // Clean up period selector event listener if this was an activity chart
        if (canvasId === 'activity-chart') {
            const periodSelector = document.getElementById('activity-period');
            if (periodSelector && periodSelector._unifiedServiceHandler) {
                periodSelector.removeEventListener('change', periodSelector._unifiedServiceHandler);
                periodSelector.removeAttribute('data-chart-listener-attached');
                delete periodSelector._unifiedServiceHandler;
                console.log('Cleaned up unified service period selector event listener');
            }
        }
        
        // Clean up canvas registry
        this.canvasRegistry.delete(canvasId);
    }


    /**
     * Destroy all charts
     */
    destroyAllCharts() {
        for (const [canvasId, chartInstance] of this.charts) {
            chartInstance.destroy();
        }
        this.charts.clear();
        this.canvasRegistry.clear();
    }

    /**
     * Show error message in chart container
     */
    showChartError(canvasId, message) {
        const canvas = document.getElementById(canvasId);
        if (canvas) {
            const container = canvas.parentElement;
            if (container) {
                container.innerHTML = `
                    <div class="chart-error" style="
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        height: 300px;
                        background: #f8f9fa;
                        border: 1px solid #dee2e6;
                        border-radius: 4px;
                        color: #6c757d;
                        text-align: center;
                        padding: 20px;
                    ">
                        <div>
                            <i class="fas fa-exclamation-triangle" style="font-size: 2rem; margin-bottom: 10px; color: #dc3545;"></i>
                            <p style="margin: 0; font-size: 14px;">${message}</p>
                            <button onclick="window.unifiedChartService.retryChart('${canvasId}')" 
                                    style="margin-top: 10px; padding: 5px 15px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer;">
                                Retry
                            </button>
                        </div>
                    </div>
                `;
            }
        }
    }

    /**
     * Retry chart initialization
     */
    async retryChart(canvasId) {
        console.log('Retrying chart initialization for:', canvasId);
        
        // Clear HTTP service cache
        this.httpService.clearCache();
        
        // Try to reinitialize based on chart type
        if (canvasId.includes('activity')) {
            await this.initializeActivityChart(canvasId);
        } else if (canvasId.includes('course')) {
            await this.initializeCoursesChart(canvasId);
        }
    }

    /**
     * Get chart instance
     */
    getChart(canvasId) {
        return this.charts.get(canvasId);
    }

    /**
     * Get service status
     */
    getStatus() {
        return {
            chartsCount: this.charts.size,
            httpServiceStatus: this.httpService.getStatus(),
            chartIds: Array.from(this.charts.keys())
        };
    }
}

/**
 * Activity Chart Instance
 */
class ActivityChartInstance {
    constructor(config, httpService) {
        this.config = config;
        this.httpService = httpService;
        this.chart = null;
        this.canvas = null;
    }

    async initialize() {
        this.canvas = document.getElementById(this.config.canvasId);
        if (!this.canvas) {
            throw new Error(`Canvas not found: ${this.config.canvasId}`);
        }

        // Load initial data
        await this.loadData(this.config.defaultPeriod);
    }

    async loadData(period = null) {
        const selectedPeriod = period || this.config.defaultPeriod;
        
        try {
            console.log(`Loading activity data for period: ${selectedPeriod}`);
            console.log(`API endpoint: ${this.config.apiEndpoint}`);
            
            const url = `${this.config.apiEndpoint}?period=${selectedPeriod}`;
            console.log(`Making request to: ${url}`);
            
            const data = await this.httpService.makeRequest(url);
            console.log('Received data:', data);
            console.log('Data.fallback value:', data.fallback);
            console.log('Data.labels:', data.labels);
            console.log('Data.logins:', data.logins);
            console.log('Data.completions:', data.completions);
            
            // Check if the API returned fallback data - only if explicitly marked as fallback
            if (data.fallback === true) {
                console.warn('API returned fallback data:', data.error || 'No specific error message');
                // Add period to fallback data URL for proper fallback generation
                const fallbackUrl = `${url}&fallback=true`;
                const periodAwareFallback = this.httpService.getFallbackData(fallbackUrl);
                console.log('Using period-aware fallback:', periodAwareFallback);
                this.renderChart(periodAwareFallback);
            } else {
                // This is real data from the API
                console.log('Rendering real data from API');
                this.renderChart(data);
            }
            
        } catch (error) {
            console.error('Failed to load activity data:', error);
            console.error('Error details:', {
                message: error.message,
                status: error.status,
                stack: error.stack
            });
            
            // Generate period-aware fallback data
            const fallbackUrl = `${this.config.apiEndpoint}?period=${selectedPeriod}&fallback=true`;
            const fallbackData = this.httpService.getFallbackData(fallbackUrl);
            fallbackData.error = `API Error: ${error.message}`;
            fallbackData.fallback = true;
            console.log('Using fallback data due to API error:', fallbackData);
            this.renderChart(fallbackData);
        }
    }

    renderChart(data) {
        // Destroy existing chart and clear canvas
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
        
        // Clear any existing Chart.js instances on this canvas
        const existingChart = Chart.getChart(this.canvas);
        if (existingChart) {
            existingChart.destroy();
        }
        
        // Clear canvas content
        const ctx = this.canvas.getContext('2d');
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        const chartConfig = {
            type: 'line',
            data: {
                labels: data.labels || [],
                datasets: [
                    {
                        label: 'Logins',
                        data: data.logins || [],
                        borderColor: '#60a5fa', // Light blue color
                        backgroundColor: 'rgba(96, 165, 250, 0.05)', // Very light blue background
                        borderWidth: 2,
                        pointBackgroundColor: '#60a5fa',
                        pointBorderColor: '#60a5fa',
                        pointBorderWidth: 0,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        tension: 0.4, // Smoother curves
                        fill: false // No fill to match the clean look
                    },
                    {
                        label: 'Course Completions',
                        data: data.completions || [],
                        borderColor: '#14b8a6', // Teal/mint green color
                        backgroundColor: 'rgba(20, 184, 166, 0.05)', // Very light teal background
                        borderWidth: 2,
                        pointBackgroundColor: '#14b8a6',
                        pointBorderColor: '#14b8a6',
                        pointBorderWidth: 0,
                        pointRadius: 5,
                        pointHoverRadius: 7,
                        tension: 0.4, // Smoother curves
                        fill: false // No fill to match the clean look
                    }
                ]
            },
            options: {
                ...window.unifiedChartService.defaultConfig,
                layout: {
                    padding: {
                        top: 10,
                        right: 20,
                        bottom: 10,
                        left: 20
                    }
                },
                plugins: {
                    ...window.unifiedChartService.defaultConfig.plugins,
                    title: {
                        display: false // Remove duplicate title - section title is already visible
                    },
                    legend: {
                        display: true,
                        position: 'bottom',
                        align: 'center',
                        labels: {
                            padding: 15,
                            usePointStyle: true,
                            pointStyle: 'circle',
                            boxWidth: 8,
                            boxHeight: 8,
                            font: {
                                size: 12,
                                weight: '500'
                            },
                            color: '#374151'
                        }
                    },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleColor: '#ffffff',
                        bodyColor: '#ffffff',
                        borderColor: '#ffffff',
                        borderWidth: 1,
                        cornerRadius: 6,
                        displayColors: true,
                        callbacks: {
                            title: function(context) {
                                return context[0].label;
                            },
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                return `${label}: ${value}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        display: true,
                        grid: {
                            display: false, // No vertical grid lines
                            drawBorder: false
                        },
                        ticks: {
                            maxRotation: 0,
                            minRotation: 0,
                            padding: 15,
                            font: {
                                size: 12,
                                color: '#6b7280' // Dark gray text
                            },
                            color: '#6b7280'
                        }
                    },
                    y: {
                        display: false, // Hide Y-axis labels to match the clean look
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0,0,0,0.05)', // Very faint horizontal grid lines
                            drawBorder: false,
                            lineWidth: 1
                        },
                        ticks: {
                            display: false // Hide Y-axis tick labels
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                responsive: true,
                maintainAspectRatio: false,
                resizeDelay: 0
            }
        };

        this.chart = new Chart(this.canvas, chartConfig);
    }

    /**
     * Get appropriate chart title based on data and errors
     */
    getChartTitle(data) {
        // Only show fallback titles if explicitly marked as fallback
        if (data.fallback === true) {
            if (data.error && data.error.includes('Loading')) {
                return 'Activity Data (Loading...)';
            } else if (data.error && data.error.includes('Error')) {
                return 'Activity Data (Error - Using Fallback)';
            } else {
                return 'Activity Data (No Data Available)';
            }
        }
        
        // This is real data from the API - check if there's any activity
        const hasData = (data.logins && data.logins.some(val => val > 0)) || 
                       (data.completions && data.completions.some(val => val > 0));
        
        if (!hasData) {
            return 'Activity Data (No Activity in Period)';
        }
        
        // Real data with activity
        return 'Activity Data';
    }

    async updatePeriod(period) {
        console.log('ActivityChartInstance.updatePeriod called with period:', period);
        console.log('Current config:', this.config);
        await this.loadData(period);
    }

    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
        
        // Also clear any Chart.js instance that might still be attached
        const existingChart = Chart.getChart(this.canvas);
        if (existingChart) {
            existingChart.destroy();
        }
        
        // Clear canvas content
        if (this.canvas) {
            const ctx = this.canvas.getContext('2d');
            ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }
    }
}

/**
 * Courses Chart Instance
 */
class CoursesChartInstance {
    constructor(config, httpService) {
        this.config = config;
        this.httpService = httpService;
        this.chart = null;
        this.canvas = null;
    }

    async initialize() {
        this.canvas = document.getElementById(this.config.canvasId);
        if (!this.canvas) {
            throw new Error(`Canvas not found: ${this.config.canvasId}`);
        }

        // Use provided data or load from API
        if (this.config.data) {
            this.renderChart(this.config.data);
        } else {
            await this.loadData();
        }
    }

    async loadData() {
        try {
            // This would be implemented based on your specific API endpoint
            console.log('Loading courses data...');
            // const data = await this.httpService.makeRequest('/api/courses-data/');
            // this.renderChart(data);
        } catch (error) {
            console.error('Failed to load courses data:', error);
            this.renderChart(this.httpService.getFallbackData('/api/courses-data/'));
        }
    }

    renderChart(data) {
        if (this.chart) {
            this.chart.destroy();
        }

        const chartConfig = {
            type: 'doughnut',
            data: {
                labels: ['Completed', 'In Progress', 'Not Started', 'Not Passed'],
                datasets: [{
                    data: [
                        data.completed || 0,
                        data.inProgress || 0,
                        data.notStarted || 0,
                        data.notPassed || 0
                    ],
                    backgroundColor: [
                        '#10B981',  // Green for completed
                        '#F59E0B',  // Orange for in progress
                        '#9CA3AF',  // Gray for not started
                        '#EF4444'   // Red for not passed
                    ],
                    borderColor: [
                        '#10B981',
                        '#F59E0B',
                        '#9CA3AF',
                        '#EF4444'
                    ],
                    borderWidth: 2,
                    cutout: '70%'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false  // Hide legend since it's shown in the template
                    },
                    title: {
                        display: false  // Hide title since it's shown in the template
                    },
                    tooltip: {
                        enabled: true,
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.parsed;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        };

        this.chart = new Chart(this.canvas, chartConfig);
    }

    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }
}

// Create global instance
window.unifiedChartService = new UnifiedChartService();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { UnifiedChartService, ActivityChartInstance, CoursesChartInstance };
}
