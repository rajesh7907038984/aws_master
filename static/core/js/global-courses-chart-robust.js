/**
 * Robust Global Courses Chart Component
 * Uses the unified chart service for reliable HTTP handling
 */

class GlobalCoursesChartRobust {
    constructor(options = {}) {
        this.canvasId = options.canvasId || 'courses-chart';
        this.data = options.data || null;
        this.chartInstance = null;
        
        console.log('Initializing robust courses chart with options:', options);
        this.init();
    }

    async init() {
        try {
            // Wait for unified chart service to be available
            await this.waitForUnifiedService();
            
            // Initialize using unified service
            this.chartInstance = await window.unifiedChartService.initializeCoursesChart(this.canvasId, {
                data: this.data
            });
            
            if (this.chartInstance) {
                console.log('Robust courses chart initialized successfully');
            } else {
                console.error('Failed to initialize robust courses chart');
            }
            
        } catch (error) {
            console.error('Error initializing robust courses chart:', error);
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
                            <i class="fas fa-chart-pie" style="font-size: 2rem; margin-bottom: 10px; color: #6c757d;"></i>
                            <p style="margin: 0; font-size: 14px;">Course progress chart will load shortly...</p>
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
    processData() {
        // Handled by unified service
    }

    renderChart() {
        // Handled by unified service
    }

    showEmptyState() {
        // Handled by unified service
    }
}

// Create a compatibility wrapper for existing code
class GlobalCoursesChart extends GlobalCoursesChartRobust {
    constructor(options = {}) {
        console.log('Using robust GlobalCoursesChart implementation');
        super(options);
    }
}

// Export for global use
window.GlobalCoursesChart = GlobalCoursesChart;
window.GlobalCoursesChartRobust = GlobalCoursesChartRobust;
