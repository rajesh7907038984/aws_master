/**
 * Robust Global Activity Chart Component
 * Uses the unified chart service for reliable HTTP handling
 */

class GlobalActivityChartRobust {
    constructor(options = {}) {
        this.canvasId = options.canvasId || 'activity-chart';
        this.apiEndpoint = options.apiEndpoint || '/users/api/dashboard-activity-data/';
        this.defaultPeriod = options.defaultPeriod || 'month';
        this.contextData = options.contextData || null;
        this.chartInstance = null;
        
        this.init();
    }

    async init() {
        try {
            
            // Wait for unified chart service to be available
            await this.waitForUnifiedService();
            
            // Initialize using unified service
            this.chartInstance = await window.unifiedChartService.initializeActivityChart(this.canvasId, {
                apiEndpoint: this.apiEndpoint,
                defaultPeriod: this.defaultPeriod,
                contextData: this.contextData
            });
            
            if (this.chartInstance) {
                // Set up period selector after chart is ready
                setTimeout(() => {
                    this.setupPeriodSelector();
                }, 100);
            } else {
            }
            
        } catch (error) {
            this.showFallbackChart();
        }
    }

    async waitForUnifiedService(maxAttempts = 50) {
        for (let i = 0; i < maxAttempts; i++) {
            if (typeof window.unifiedChartService !== 'undefined') {
                return;
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        throw new Error('Unified chart service not available after waiting');
    }

    // Period selector removed - now using fixed month period
    setupPeriodSelector() {
        // No period selector setup needed
    }

    async updatePeriod(period) {
        if (this.chartInstance) {
            try {
                await this.chartInstance.updatePeriod(period);
            } catch (error) {
            }
        } else {
        }
    }

    // Method to check if chart is ready
    isReady() {
        return !!(this.chartInstance && this.chartInstance.chart);
    }

    // Method to wait for chart to be ready
    async waitForReady(maxAttempts = 50) {
        for (let i = 0; i < maxAttempts; i++) {
            if (this.isReady()) {
                return true;
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        return false;
    }

    showFallbackChart() {
        const canvas = document.getElementById(this.canvasId);
        if (canvas) {
            const container = canvas.parentElement;
            if (container) {
                container.innerHTML = `
                    <div class="chart-fallback" style="
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
                            <i class="fas fa-chart-line" style="font-size: 2rem; margin-bottom: 10px; color: #6c757d;"></i>
                            <p style="margin: 0; font-size: 14px;">Activity chart will load shortly...</p>
                        </div>
                    </div>
                `;
            }
        }
    }

    destroy() {
        if (this.chartInstance) {
            this.chartInstance.destroy();
            this.chartInstance = null;
        }
    }

    // Legacy compatibility methods
    async loadData(period = null) {
        if (this.chartInstance) {
            await this.chartInstance.loadData(period);
        }
    }

    renderChart(data) {
        if (this.chartInstance) {
            this.chartInstance.renderChart(data);
        }
    }

    showLoading() {
        // Handled by unified service
    }

    showError(message) {
        // Handled by unified service
    }

    showEmptyChart() {
        // Handled by unified service
    }
}

// Create a compatibility wrapper for existing code
if (typeof window.GlobalActivityChart === 'undefined') {
    class GlobalActivityChart extends GlobalActivityChartRobust {
        constructor(options = {}) {
            super(options);
        }
    }

    // Export for global use
    window.GlobalActivityChart = GlobalActivityChart;
    window.GlobalActivityChartRobust = GlobalActivityChartRobust;
} else {
}
