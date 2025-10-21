/**
 * Performance Charts JavaScript
 * Handles all performance-related charts and metrics
 */

class PerformanceCharts {
    constructor() {
        this.charts = {};
        this.currentTimeframe = 'month';
        this.isInitialized = false;
    }

    async initialize() {
        if (this.isInitialized) {
            return;
        }

        try {
            // Initialize Chart.js if available
            if (typeof Chart !== 'undefined') {
                await this.initializeCharts();
            } else {
                console.warn('Chart.js not loaded - charts will not be available');
            }

            this.isInitialized = true;
            return true;
        } catch (error) {
            console.error('Error initializing performance charts:', error);
            return false;
        }
    }

    async initializeCharts() {
        // User Activity Chart
        this.initializeUserActivityChart();
        
        // Course Performance Chart
        this.initializeCoursePerformanceChart();
        
        // Learning Progress Chart
        this.initializeLearningProgressChart();
        
        // Quiz Performance Chart
        this.initializeQuizPerformanceChart();
        
        // Engagement Chart
        this.initializeEngagementChart();
        
        // System Metrics Chart
        this.initializeSystemMetricsChart();
    }

    initializeUserActivityChart() {
        const ctx = document.getElementById('user-activity-chart');
        if (!ctx) return;

        this.charts.userActivity = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Active Users',
                    data: [],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    initializeCoursePerformanceChart() {
        const ctx = document.getElementById('course-performance-chart');
        if (!ctx) return;

        this.charts.coursePerformance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Completed', 'In Progress', 'Not Started'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: ['#10b981', '#f59e0b', '#ef4444']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    initializeLearningProgressChart() {
        const ctx = document.getElementById('learning-progress-chart');
        if (!ctx) return;

        this.charts.learningProgress = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Progress',
                    data: [],
                    backgroundColor: '#8b5cf6'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100
                    }
                }
            }
        });
    }

    initializeQuizPerformanceChart() {
        const ctx = document.getElementById('quiz-performance-chart');
        if (!ctx) return;

        this.charts.quizPerformance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Average Score',
                    data: [],
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100
                    }
                }
            }
        });
    }

    initializeEngagementChart() {
        const ctx = document.getElementById('engagement-chart');
        if (!ctx) return;

        this.charts.engagement = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Engagement',
                    data: [],
                    backgroundColor: '#ec4899'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    initializeSystemMetricsChart() {
        const ctx = document.getElementById('system-metrics-chart');
        if (!ctx) return;

        this.charts.systemMetrics = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: ['Performance', 'Reliability', 'Usability', 'Efficiency', 'Maintainability'],
                datasets: [{
                    label: 'System Health',
                    data: [0, 0, 0, 0, 0],
                    backgroundColor: 'rgba(16, 185, 129, 0.2)',
                    borderColor: '#10b981',
                    pointBackgroundColor: '#10b981'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    r: {
                        beginAtZero: true,
                        max: 100
                    }
                }
            }
        });
    }

    async loadPerformanceData() {
        try {
            const response = await fetch(`/api/performance/data/?timeframe=${this.currentTimeframe}`, {
                credentials: 'same-origin',
                headers: {
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('Error loading performance data:', error);
            return this.getDefaultData();
        }
    }

    getDefaultData() {
        return {
            user_activity: {
                total_users: 0,
                active_users: 0,
                new_users: 0,
                activity_rate: 0
            },
            course_performance: {
                total_courses: 0,
                overall_completion_rate: 0,
                avg_completion_time_days: 0
            },
            learning_progress: {
                total_enrollments: 0,
                completed: 0,
                learning_velocity: 0
            },
            quiz_performance: {
                total_attempts: 0,
                pass_rate: 0,
                avg_score: 0
            },
            engagement_metrics: {
                daily_active_users: [],
                total_logins: 0,
                engagement_score: 0
            },
            system_performance: {
                content_utilization: 0,
                user_engagement: 0,
                avg_enrollments_per_course: 0
            }
        };
    }

    async updateTimeframe(timeframe) {
        this.currentTimeframe = timeframe;
        
        try {
            const data = await this.loadPerformanceData();
            this.updateCharts(data);
            return data;
        } catch (error) {
            console.error('Error updating timeframe:', error);
            return this.getDefaultData();
        }
    }

    updateCharts(data) {
        // Update user activity chart
        if (this.charts.userActivity && data.user_activity) {
            this.charts.userActivity.data.labels = data.user_activity.labels || [];
            this.charts.userActivity.data.datasets[0].data = data.user_activity.data || [];
            this.charts.userActivity.update();
        }

        // Update course performance chart
        if (this.charts.coursePerformance && data.course_performance) {
            this.charts.coursePerformance.data.datasets[0].data = [
                data.course_performance.completed || 0,
                data.course_performance.in_progress || 0,
                data.course_performance.not_started || 0
            ];
            this.charts.coursePerformance.update();
        }

        // Update learning progress chart
        if (this.charts.learningProgress && data.learning_progress) {
            this.charts.learningProgress.data.labels = data.learning_progress.labels || [];
            this.charts.learningProgress.data.datasets[0].data = data.learning_progress.data || [];
            this.charts.learningProgress.update();
        }

        // Update quiz performance chart
        if (this.charts.quizPerformance && data.quiz_performance) {
            this.charts.quizPerformance.data.labels = data.quiz_performance.labels || [];
            this.charts.quizPerformance.data.datasets[0].data = data.quiz_performance.data || [];
            this.charts.quizPerformance.update();
        }

        // Update engagement chart
        if (this.charts.engagement && data.engagement_metrics) {
            this.charts.engagement.data.labels = data.engagement_metrics.labels || [];
            this.charts.engagement.data.datasets[0].data = data.engagement_metrics.data || [];
            this.charts.engagement.update();
        }

        // Update system metrics chart
        if (this.charts.systemMetrics && data.system_performance) {
            this.charts.systemMetrics.data.datasets[0].data = [
                data.system_performance.performance || 0,
                data.system_performance.reliability || 0,
                data.system_performance.usability || 0,
                data.system_performance.efficiency || 0,
                data.system_performance.maintainability || 0
            ];
            this.charts.systemMetrics.update();
        }
    }

    destroy() {
        Object.values(this.charts).forEach(chart => {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        });
        this.charts = {};
        this.isInitialized = false;
    }
}

// Initialize performance charts when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (typeof window.performanceCharts === 'undefined') {
        window.performanceCharts = new PerformanceCharts();
        window.performanceCharts.initialize();
    }
});

// Export for global access
window.PerformanceCharts = PerformanceCharts;
