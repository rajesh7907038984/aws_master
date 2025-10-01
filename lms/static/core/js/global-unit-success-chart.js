/**
 * Global Unit Success Chart Component
 * Reusable component for unit success rate charts across all pages
 * Handles data loading and doughnut chart rendering
 */

class GlobalUnitSuccessChart {
    constructor(options = {}) {
        this.canvasId = options.canvasId || 'unit-success-chart';
        this.passedCount = parseInt(options.passedCount) || 0;
        this.notPassedCount = parseInt(options.notPassedCount) || 0;
        this.totalAttempts = parseInt(options.totalAttempts) || 0;
        this.chart = null;
        
        // Chart configuration
        this.chartConfig = {
            type: 'doughnut',
            data: {
                labels: ['Passed', 'Not Passed'],
                datasets: [{
                    data: [this.passedCount, this.notPassedCount],
                    backgroundColor: ['#10b981', '#ef4444'], // Green, Red
                    borderWidth: 2,
                    borderColor: '#ffffff',
                    hoverBorderWidth: 3,
                    cutout: '70%'
                }]
            },
            options: {
                responsive: false,
                maintainAspectRatio: true,
                devicePixelRatio: window.devicePixelRatio || 1,
                plugins: {
                    legend: {
                        display: false // Custom legend below
                    },
                    tooltip: {
                        enabled: true,
                        callbacks: {
                            label: (context) => {
                                const label = context.label;
                                const value = context.raw;
                                if (this.totalAttempts === 0) return `${label}: ${value}`;
                                const percentage = Math.round((value / this.totalAttempts) * 100);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                },
                animation: {
                    animateRotate: true,
                    duration: 800,
                    easing: 'easeOutQuart'
                }
            }
        };
        
        this.init();
    }
    
    init() {
        console.log('🎯 Initializing Global Unit Success Chart...');
        console.log('📊 Chart data:', {
            passed: this.passedCount,
            notPassed: this.notPassedCount,
            total: this.totalAttempts
        });
        
        // Wait for Chart.js to be available
        this.waitForChart(() => {
            this.createChart();
        });
    }
    
    waitForChart(callback, retryCount = 0) {
        const maxRetries = 25; // 5 seconds max
        
        if (typeof Chart === 'undefined') {
            if (retryCount >= maxRetries) {
                console.error('❌ Chart.js library not available for Unit Success Chart');
                this.showError('Chart library not loaded');
                return;
            }
            console.log(`⏳ Waiting for Chart.js... (${retryCount + 1}/${maxRetries})`);
            setTimeout(() => this.waitForChart(callback, retryCount + 1), 200);
            return;
        }
        
        const canvas = document.getElementById(this.canvasId);
        if (!canvas) {
            if (retryCount >= maxRetries) {
                console.error('❌ Canvas not found for Unit Success Chart');
                this.showError('Canvas element not found');
                return;
            }
            console.log(`⏳ Waiting for canvas... (${retryCount + 1}/${maxRetries})`);
            setTimeout(() => this.waitForChart(callback, retryCount + 1), 200);
            return;
        }
        
        // All ready
        callback();
    }
    
    createChart() {
        const canvas = document.getElementById(this.canvasId);
        if (!canvas) {
            this.showError('Canvas not found');
            return;
        }
        
        // Handle empty data case
        if (this.totalAttempts === 0) {
            this.showEmptyState();
            return;
        }
        
        try {
            const ctx = canvas.getContext('2d');
            
            // Update chart data
            this.chartConfig.data.datasets[0].data = [this.passedCount, this.notPassedCount];
            
            // Create the chart
            this.chart = new Chart(ctx, this.chartConfig);
            
            console.log('✅ Global Unit Success Chart created successfully');
            this.hideStatus();
            
        } catch (error) {
            console.error('❌ Failed to create Global Unit Success Chart:', error);
            this.showError('Chart creation failed: ' + error.message);
        }
    }
    
    showEmptyState() {
        console.log('📊 No data available for unit success chart');
        const statusDiv = document.getElementById('unit-success-status');
        if (statusDiv) {
            statusDiv.className = 'text-center text-sm text-gray-400 mt-4';
            statusDiv.innerHTML = '<div>No data available</div>';
        }
        this.hideCanvas();
    }
    
    showError(message) {
        console.error('Unit Success Chart Error:', message);
        const statusDiv = document.getElementById('unit-success-status');
        if (statusDiv) {
            statusDiv.className = 'text-center text-sm text-red-500 mt-4';
            statusDiv.innerHTML = `<div>❌ ${message}</div>`;
        }
    }
    
    hideStatus() {
        const statusDiv = document.getElementById('unit-success-status');
        if (statusDiv) {
            statusDiv.className = 'hidden';
        }
    }
    
    hideCanvas() {
        const canvas = document.getElementById(this.canvasId);
        if (canvas) {
            canvas.style.display = 'none';
        }
    }
    
    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }
    
    updateData(passedCount, notPassedCount, totalAttempts) {
        this.passedCount = parseInt(passedCount) || 0;
        this.notPassedCount = parseInt(notPassedCount) || 0;
        this.totalAttempts = parseInt(totalAttempts) || 0;
        
        if (this.chart) {
            this.chart.data.datasets[0].data = [this.passedCount, this.notPassedCount];
            this.chart.update();
        } else {
            this.init();
        }
    }
}

// Make available globally
window.GlobalUnitSuccessChart = GlobalUnitSuccessChart;
