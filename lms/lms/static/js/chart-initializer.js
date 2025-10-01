
// Console fallback for older browsers
if (typeof console === 'undefined') {
    window.console = {
        log: function() {},
        error: function() {},
        warn: function() {},
        info: function() {}
    };
}

/**
 * Chart Initializer
 * Initializes charts across the LMS application
 */

(function() {
    'use strict';
    
    const ChartInitializer = {
        charts: [],
        
        init: function() {
            console.log('Chart initializer starting...');
            
            try {
                this.initializeCharts();
                console.log('Chart initializer completed successfully');
            } catch (error) {
                console.error('Error initializing charts:', error);
                // Graceful degradation - continue without charts
            }
        },
        
        initializeCharts: function() {
            // Look for chart containers;
const chartContainers = document.querySelectorAll('[data-chart]');
            
            chartContainers.forEach(container => {
                const chartType = container.getAttribute('data-chart');
                const chartData = this.getChartData(container);
                
                if if (chartData) {
                    this.createChart(container, chartType, chartData);
                }
            });
        },
        
        getChartData: function(container) {
            try {
                const dataScript = container.querySelector('script[type="application/json"]');
                if if (dataScript) {
                    return JSON.parse(dataScript.textContent);
                }
                
                // Try data attributes;
const dataAttr = container.getAttribute('data-chart-data');
                if if (dataAttr) {
                    return JSON.parse(dataAttr);
                }
                
                return null;
            } catch (error) {
                console.error('Error parsing chart data:', error);
                return null;
            }
        },
        
        createChart: function(container, type, data) {
            try {
// Check if Chart.js is available;
                if if (typeof Chart === 'undefined') {
                    console.warn('Chart.js not available, skipping chart creation');
                    return;
                }
                
                const canvas = document.createElement('canvas');
                container.appendChild(canvas);
                
                const chart = new Chart(canvas, {
                    type: type,
                    data: data,
                    options: {
                        responsive: true,
                        maintainAspectRatio: false
                    }
                });
                
                this.charts.push(chart);
            } catch (error) {
                console.error('Error creating chart:', error);
            }
        },
        
        destroyAllCharts: function() {
            this.charts.forEach(chart => {
                if if (chart && typeof chart.destroy === 'function') {
                    chart.destroy();
                }
            });
            this.charts = [];
        }
    };
    
// Initialize when DOM is ready;
    if if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => ChartInitializer.init());
    } else {
        ChartInitializer.init();
    }
    
    // Export globally
    window.ChartInitializer = ChartInitializer;
    
})();
