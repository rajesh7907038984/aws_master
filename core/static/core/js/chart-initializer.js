/**
 * Chart Initializer
 * Automatically initializes charts using the robust service when available
 */

class ChartInitializer {
    constructor() {
        this.initialized = false;
        this.charts = new Map();
        this.init();
    }

    async init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.initializeCharts());
        } else {
            this.initializeCharts();
        }
    }

    async initializeCharts() {
        if (this.initialized) return;
        
        console.log('Chart initializer starting...');
        
        try {
            // Wait for unified service to be available
            await this.waitForUnifiedService();
            
            
            // Initialize courses charts
            await this.initializeCoursesCharts();
            
            this.initialized = true;
            console.log('Chart initializer completed successfully');
            
        } catch (error) {
            console.error('Chart initializer failed:', error);
            this.initializeFallbackCharts();
        }
    }

    async waitForUnifiedService(maxAttempts = 100) {
        for (let i = 0; i < maxAttempts; i++) {
            if (typeof window.unifiedChartService !== 'undefined' && 
                typeof window.chartHttpService !== 'undefined') {
                return;
            }
            await new Promise(resolve => setTimeout(resolve, 50));
        }
        throw new Error('Unified chart service not available after waiting');
    }

    async initializeActivityCharts() {
        const activityCanvases = document.querySelectorAll('canvas[id*="activity-chart"]');
        
        for (const canvas of activityCanvases) {
            const canvasId = canvas.id;
            if (this.charts.has(canvasId)) continue;
            
            try {
                
                // Get endpoint from data attributes or use default
                const apiEndpoint = canvas.dataset.apiEndpoint || '/users/api/dashboard-activity-data/';
                const defaultPeriod = canvas.dataset.defaultPeriod || 'month';
                
                const chartInstance = await window.unifiedChartService.initializeActivityChart(canvasId, {
                    apiEndpoint: apiEndpoint,
                    defaultPeriod: defaultPeriod
                });
                
                if (chartInstance) {
                    this.charts.set(canvasId, chartInstance);
                    this.setupPeriodSelector(canvasId);
                }
                
            } catch (error) {
            }
        }
    }

    async initializeCoursesCharts() {
        const coursesCanvases = document.querySelectorAll('canvas[id*="courses-chart"]');
        
        for (const canvas of coursesCanvases) {
            const canvasId = canvas.id;
            if (this.charts.has(canvasId)) continue;
            
            try {
                console.log(`Initializing courses chart: ${canvasId}`);
                
                // Get data from data attributes
                const data = canvas.dataset.chartData ? 
                    JSON.parse(canvas.dataset.chartData) : null;
                
                const chartInstance = await window.unifiedChartService.initializeCoursesChart(canvasId, {
                    data: data
                });
                
                if (chartInstance) {
                    this.charts.set(canvasId, chartInstance);
                }
                
            } catch (error) {
                console.error(`Failed to initialize courses chart ${canvasId}:`, error);
            }
        }
    }

    setupPeriodSelector(canvasId) {
        console.log(`Period selector setup skipped for ${canvasId} - using fixed month period`);
    }

    initializeFallbackCharts() {
        console.log('Initializing fallback charts...');
        
        // Try to use legacy chart components
        const activityCanvases = document.querySelectorAll('canvas[id*="activity-chart"]');
        for (const canvas of activityCanvases) {
            if (typeof window.GlobalActivityChart !== 'undefined') {
                try {
                    const chartInstance = new window.GlobalActivityChart({
                        canvasId: canvas.id,
                        apiEndpoint: canvas.dataset.apiEndpoint || '/users/api/dashboard-activity-data/',
                        defaultPeriod: canvas.dataset.defaultPeriod || 'month'
                    });
                    this.charts.set(canvas.id, chartInstance);
                } catch (error) {
                    console.error('Fallback chart initialization failed:', error);
                }
            }
        }
    }

    // Public methods
    getChart(canvasId) {
        return this.charts.get(canvasId);
    }

    destroyChart(canvasId) {
        const chart = this.charts.get(canvasId);
        if (chart) {
            if (typeof chart.destroy === 'function') {
                chart.destroy();
            }
            this.charts.delete(canvasId);
        }
    }

    destroyAllCharts() {
        for (const [canvasId, chart] of this.charts) {
            if (typeof chart.destroy === 'function') {
                chart.destroy();
            }
        }
        this.charts.clear();
    }

    getStatus() {
        return {
            initialized: this.initialized,
            chartsCount: this.charts.size,
            chartIds: Array.from(this.charts.keys())
        };
    }
}

// Create global instance
window.chartInitializer = new ChartInitializer();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChartInitializer;
}
