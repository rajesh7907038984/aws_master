/**
 * Courses Chart Fix - Permanent Solution
 * This script ensures the round diagram always renders properly
 */

(function() {
    'use strict';
    
    console.log('🔧 Loading Courses Chart Fix...');
    
    // Wait for DOM and Chart.js to be ready
    function waitForDependencies() {
        return new Promise((resolve) => {
            const checkDependencies = () => {
                if (typeof Chart !== 'undefined' && document.readyState === 'complete') {
                    resolve();
                } else {
                    setTimeout(checkDependencies, 100);
                }
            };
            checkDependencies();
        });
    }
    
    // Initialize courses chart with fallback
    async function initializeCoursesChart() {
        await waitForDependencies();
        
        const canvas = document.getElementById('courses-chart');
        if (!canvas) {
            console.log('⚠️ Courses chart canvas not found');
            return;
        }
        
        // Check if chart already exists
        if (canvas.chart) {
            console.log('✅ Courses chart already initialized');
            return;
        }
        
        try {
            // Get data from canvas data attribute
            const dataAttr = canvas.getAttribute('data-chart-data');
            let chartData = {
                completed: 0,
                inProgress: 0,
                notPassed: 0,
                notStarted: 0
            };
            
            if (dataAttr) {
                try {
                    chartData = JSON.parse(dataAttr);
                } catch (e) {
                    console.warn('Failed to parse chart data, using defaults');
                }
            }
            
            console.log('📊 Initializing courses chart with data:', chartData);
            
            // Create the chart
            const chart = new Chart(canvas, {
                type: 'doughnut',
                data: {
                    labels: ['Completed', 'In Progress', 'Not Passed', 'Not Started'],
                    datasets: [{
                        data: [
                            chartData.completed || 0,
                            chartData.inProgress || 0,
                            chartData.notPassed || 0,
                            chartData.notStarted || 0
                        ],
                        backgroundColor: [
                            '#10B981',  // Green for completed
                            '#F59E0B',  // Orange for in progress
                            '#EF4444',  // Red for not passed
                            '#9CA3AF'   // Gray for not started
                        ],
                        borderColor: [
                            '#10B981',
                            '#F59E0B',
                            '#EF4444',
                            '#9CA3AF'
                        ],
                        borderWidth: 3,
                        cutout: '70%'  // Donut chart with center space
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false  // Hide legend since status cards are shown
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
                    },
                    elements: {
                        arc: {
                            borderWidth: 2
                        }
                    }
                }
            });
            
            // Store chart reference
            canvas.chart = chart;
            
            console.log('✅ Courses chart initialized successfully');
            
        } catch (error) {
            console.error('❌ Failed to initialize courses chart:', error);
            
            // Show error message in the canvas
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#f3f4f6';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#6b7280';
            ctx.font = '14px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('Chart failed to load', canvas.width / 2, canvas.height / 2);
        }
    }
    
    // Force chart re-render
    function forceChartRerender() {
        const canvas = document.getElementById('courses-chart');
        if (canvas && canvas.chart) {
            canvas.chart.resize();
            console.log('🔄 Courses chart re-rendered');
        }
    }
    
    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeCoursesChart);
    } else {
        initializeCoursesChart();
    }
    
    // Re-initialize on window resize
    window.addEventListener('resize', () => {
        setTimeout(forceChartRerender, 100);
    });
    
    // Expose functions globally for manual initialization
    window.coursesChartFix = {
        initialize: initializeCoursesChart,
        rerender: forceChartRerender
    };
    
    console.log('🎉 Courses Chart Fix loaded successfully');
})();
