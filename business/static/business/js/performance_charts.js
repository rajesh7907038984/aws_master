/**
 * Business Performance Charts Management
 * Reusable JavaScript utilities for managing performance charts and statistics
 */

class PerformanceChartManager {
    constructor() {
        this.charts = {};
        this.defaultColors = {
            primary: '#667eea',
            secondary: '#764ba2',
            success: '#28a745',
            warning: '#ffc107',
            danger: '#dc3545',
            info: '#17a2b8',
            light: '#f8f9fa',
            dark: '#343a40'
        };
        this.chartDefaults = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    enabled: true,
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        display: false
                    }
                },
                y: {
                    display: true,
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0,0,0,0.1)'
                    }
                }
            }
        };
    }

    /**
     * Create a line chart
     */
    createLineChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
            console.error(`Canvas with id '${canvasId}' not found`);
            return null;
        }

        const config = {
            type: 'line',
            data: data,
            options: { ...this.chartDefaults, ...options }
        };

        const chart = new Chart(ctx, config);
        this.charts[canvasId] = chart;
        return chart;
    }

    /**
     * Create a bar chart
     */
    createBarChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
            console.error(`Canvas with id '${canvasId}' not found`);
            return null;
        }

        const config = {
            type: 'bar',
            data: data,
            options: { ...this.chartDefaults, ...options }
        };

        const chart = new Chart(ctx, config);
        this.charts[canvasId] = chart;
        return chart;
    }

    /**
     * Create a pie chart
     */
    createPieChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
            console.error(`Canvas with id '${canvasId}' not found`);
            return null;
        }

        const config = {
            type: 'pie',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom'
                    },
                    tooltip: {
                        enabled: true
                    }
                },
                ...options
            }
        };

        const chart = new Chart(ctx, config);
        this.charts[canvasId] = chart;
        return chart;
    }

    /**
     * Create a doughnut chart
     */
    createDoughnutChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
            console.error(`Canvas with id '${canvasId}' not found`);
            return null;
        }

        const config = {
            type: 'doughnut',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom'
                    },
                    tooltip: {
                        enabled: true
                    }
                },
                cutout: '60%',
                ...options
            }
        };

        const chart = new Chart(ctx, config);
        this.charts[canvasId] = chart;
        return chart;
    }

    /**
     * Update chart data
     */
    updateChart(canvasId, newData) {
        const chart = this.charts[canvasId];
        if (chart) {
            chart.data = newData;
            chart.update();
        } else {
            console.error(`Chart with id '${canvasId}' not found`);
        }
    }

    /**
     * Destroy a chart
     */
    destroyChart(canvasId) {
        const chart = this.charts[canvasId];
        if (chart) {
            chart.destroy();
            delete this.charts[canvasId];
        }
    }

    /**
     * Destroy all charts
     */
    destroyAllCharts() {
        Object.keys(this.charts).forEach(canvasId => {
            this.destroyChart(canvasId);
        });
    }

    /**
     * Get chart data for login trends
     */
    getLoginTrendData(labels, loginCounts, options = {}) {
        return {
            labels: labels,
            datasets: [{
                label: 'Logins',
                data: loginCounts,
                borderColor: options.borderColor || this.defaultColors.primary,
                backgroundColor: options.backgroundColor || this.hexToRgba(this.defaultColors.primary, 0.1),
                tension: options.tension || 0.1,
                fill: options.fill || true
            }]
        };
    }

    /**
     * Get chart data for completion trends
     */
    getCompletionTrendData(labels, completionCounts, options = {}) {
        return {
            labels: labels,
            datasets: [{
                label: 'Course Completions',
                data: completionCounts,
                borderColor: options.borderColor || this.defaultColors.success,
                backgroundColor: options.backgroundColor || this.hexToRgba(this.defaultColors.success, 0.1),
                tension: options.tension || 0.1,
                fill: options.fill || true
            }]
        };
    }

    /**
     * Get chart data for business comparison
     */
    getBusinessComparisonData(businesses, metric = 'completion_rate', options = {}) {
        return {
            labels: businesses.map(b => b.business_name),
            datasets: [{
                label: this.getMetricLabel(metric),
                data: businesses.map(b => b[metric]),
                backgroundColor: options.backgroundColor || this.generateColors(businesses.length),
                borderColor: options.borderColor || this.defaultColors.primary,
                borderWidth: options.borderWidth || 1
            }]
        };
    }

    /**
     * Get chart data for progress distribution
     */
    getProgressDistributionData(completed, inProgress, notStarted, options = {}) {
        return {
            labels: ['Completed', 'In Progress', 'Not Started'],
            datasets: [{
                data: [completed, inProgress, notStarted],
                backgroundColor: options.backgroundColor || [
                    this.defaultColors.success,
                    this.defaultColors.warning,
                    this.defaultColors.light
                ],
                borderColor: options.borderColor || [
                    this.defaultColors.success,
                    this.defaultColors.warning,
                    this.defaultColors.dark
                ],
                borderWidth: options.borderWidth || 2
            }]
        };
    }

    /**
     * Generate random colors for charts
     */
    generateColors(count) {
        const colors = [];
        for (let i = 0; i < count; i++) {
            colors.push(this.getRandomColor());
        }
        return colors;
    }

    /**
     * Get a random color
     */
    getRandomColor() {
        const hue = Math.floor(Math.random() * 360);
        return `hsl(${hue}, 70%, 50%)`;
    }

    /**
     * Convert hex color to rgba
     */
    hexToRgba(hex, alpha) {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    /**
     * Get metric label for display
     */
    getMetricLabel(metric) {
        const labels = {
            'completion_rate': 'Completion Rate (%)',
            'total_users': 'Total Users',
            'active_users': 'Active Users',
            'total_courses': 'Total Courses',
            'total_branches': 'Total Branches'
        };
        return labels[metric] || metric;
    }

    /**
     * Update progress ring
     */
    updateProgressRing(elementId, percentage) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Element with id '${elementId}' not found`);
            return;
        }

        const circle = element.querySelector('.progress');
        if (circle) {
            const circumference = 2 * Math.PI * 45; // radius = 45
            const offset = circumference - (percentage / 100) * circumference;
            circle.style.strokeDashoffset = offset;
        }
    }

    /**
     * Animate progress ring
     */
    animateProgressRing(elementId, percentage, duration = 1000) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Element with id '${elementId}' not found`);
            return;
        }

        const circle = element.querySelector('.progress');
        if (circle) {
            const circumference = 2 * Math.PI * 45; // radius = 45
            const offset = circumference - (percentage / 100) * circumference;
            
            circle.style.strokeDashoffset = circumference;
            circle.style.transition = `stroke-dashoffset ${duration}ms ease-in-out`;
            
            setTimeout(() => {
                circle.style.strokeDashoffset = offset;
            }, 100);
        }
    }

    /**
     * Create responsive chart container
     */
    createResponsiveChart(canvasId, chartType, data, options = {}) {
        const container = document.createElement('div');
        container.className = 'chart-container';
        container.style.position = 'relative';
        container.style.height = options.height || '300px';
        
        const canvas = document.createElement('canvas');
        canvas.id = canvasId;
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        
        container.appendChild(canvas);
        
        // Create chart based on type
        let chart;
        switch (chartType) {
            case 'line':
                chart = this.createLineChart(canvasId, data, options);
                break;
            case 'bar':
                chart = this.createBarChart(canvasId, data, options);
                break;
            case 'pie':
                chart = this.createPieChart(canvasId, data, options);
                break;
            case 'doughnut':
                chart = this.createDoughnutChart(canvasId, data, options);
                break;
            default:
                console.error(`Unknown chart type: ${chartType}`);
                return null;
        }
        
        return { container, chart };
    }

    /**
     * Export chart as image
     */
    exportChart(canvasId, filename = 'chart.png') {
        const chart = this.charts[canvasId];
        if (chart) {
            const url = chart.toBase64Image();
            const link = document.createElement('a');
            link.download = filename;
            link.href = url;
            link.click();
        } else {
            console.error(`Chart with id '${canvasId}' not found`);
        }
    }

    /**
     * Print chart
     */
    printChart(canvasId) {
        const chart = this.charts[canvasId];
        if (chart) {
            const printWindow = window.open('', '_blank');
            printWindow.document.write(`
                <html>
                    <head>
                        <title>Chart Print</title>
                    </head>
                    <body>
                        <img src="${chart.toBase64Image()}" style="width: 100%; height: auto;">
                    </body>
                </html>
            `);
            printWindow.document.close();
            printWindow.print();
        } else {
            console.error(`Chart with id '${canvasId}' not found`);
        }
    }
}

// Global chart manager instance
window.PerformanceChartManager = new PerformanceChartManager();

// Utility functions for common chart operations
window.createLoginTrendChart = function(canvasId, labels, loginCounts, options = {}) {
    const data = window.PerformanceChartManager.getLoginTrendData(labels, loginCounts, options);
    return window.PerformanceChartManager.createLineChart(canvasId, data, options);
};

window.createCompletionTrendChart = function(canvasId, labels, completionCounts, options = {}) {
    const data = window.PerformanceChartManager.getCompletionTrendData(labels, completionCounts, options);
    return window.PerformanceChartManager.createLineChart(canvasId, data, options);
};

window.createBusinessComparisonChart = function(canvasId, businesses, metric = 'completion_rate', options = {}) {
    const data = window.PerformanceChartManager.getBusinessComparisonData(businesses, metric, options);
    return window.PerformanceChartManager.createBarChart(canvasId, data, options);
};

window.createProgressDistributionChart = function(canvasId, completed, inProgress, notStarted, options = {}) {
    const data = window.PerformanceChartManager.getProgressDistributionData(completed, inProgress, notStarted, options);
    return window.PerformanceChartManager.createDoughnutChart(canvasId, data, options);
};

// Auto-initialize charts when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Initialize any charts with data attributes
    const chartElements = document.querySelectorAll('[data-chart-type]');
    chartElements.forEach(element => {
        const chartType = element.dataset.chartType;
        const canvasId = element.id;
        const data = JSON.parse(element.dataset.chartData || '{}');
        const options = JSON.parse(element.dataset.chartOptions || '{}');
        
        switch (chartType) {
            case 'line':
                window.PerformanceChartManager.createLineChart(canvasId, data, options);
                break;
            case 'bar':
                window.PerformanceChartManager.createBarChart(canvasId, data, options);
                break;
            case 'pie':
                window.PerformanceChartManager.createPieChart(canvasId, data, options);
                break;
            case 'doughnut':
                window.PerformanceChartManager.createDoughnutChart(canvasId, data, options);
                break;
        }
    });
});
