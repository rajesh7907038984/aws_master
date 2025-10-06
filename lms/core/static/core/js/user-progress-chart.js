/**
 * User Progress Chart Component
 * Reusable component for visualizing user progress data
 * Supports multiple chart types: bar, doughnut, and list view
 */

class UserProgressChart {
    constructor(options = {}) {
        this.canvasId = options.canvasId || 'user-progress-chart';
        this.userData = options.userData || [];
        this.chartTitle = options.chartTitle || 'User Progress';
        this.showExport = options.showExport !== false;
        this.chart = null;
        this.currentChartType = 'doughnut';
        
        // Process the user data
        this.processUserData();
        
        // Initialize the chart
        this.init();
    }
    
    init() {
        console.log('Initializing UserProgressChart...');
        console.log('User data:', this.userData);
        
        if (typeof Chart === 'undefined') {
            console.error('Chart.js library not loaded');
            this.showError('Chart.js library not loaded');
            return;
        }
        
        this.canvas = document.getElementById(this.canvasId);
        if (!this.canvas) {
            console.error(`Canvas element with id '${this.canvasId}' not found!`);
            this.showError(`Canvas element with id '${this.canvasId}' not found!`);
            return;
        }
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Render initial chart
        this.renderChart();
        
        // Update summary stats
        this.updateSummaryStats();
        
        console.log('UserProgressChart initialized successfully');
    }
    
    processUserData() {
        console.log('Processing user data:', this.userData);
        
        this.stats = {
            completed: 0,
            inProgress: 0,
            notPassed: 0,
            notStarted: 0,
            totalUsers: this.userData.length,
            totalScore: 0,
            usersWithScores: 0
        };
        
        this.userData.forEach(user => {
            const progress = user.progress || user;
            
            if (progress.completed) {
                this.stats.completed++;
            } else if (progress.last_accessed && progress.last_score && progress.last_score < 70) {
                this.stats.notPassed++;
            } else if (progress.last_accessed) {
                this.stats.inProgress++;
            } else {
                this.stats.notStarted++;
            }
            
            // Calculate average scores
            if (progress.last_score) {
                this.stats.totalScore += parseFloat(progress.last_score);
                this.stats.usersWithScores++;
            }
        });
        
        console.log('Processed stats:', this.stats);
    }
    
    setupEventListeners() {
        // Chart type selector
        const chartTypeSelect = document.getElementById('chart-type-select');
        if (chartTypeSelect) {
            chartTypeSelect.addEventListener('change', (e) => {
                this.currentChartType = e.target.value;
                this.renderChart();
            });
        }
        
        // Export button
        const exportBtn = document.getElementById('export-chart-btn');
        if (exportBtn && this.showExport) {
            exportBtn.addEventListener('click', () => {
                this.exportChart();
            });
        }
    }
    
    renderChart() {
        const chartContainer = document.getElementById('chart-container');
        const listContainer = document.getElementById('list-view-container');
        const legendContainer = document.getElementById('chart-legend');
        
        if (this.currentChartType === 'list') {
            // Show list view, hide chart
            chartContainer.classList.add('hidden');
            listContainer.classList.remove('hidden');
            legendContainer.classList.add('hidden');
            this.renderListView();
        } else {
            // Show chart, hide list
            chartContainer.classList.remove('hidden');
            listContainer.classList.add('hidden');
            legendContainer.classList.remove('hidden');
            this.renderChartView();
        }
        
        this.updateLegend();
    }
    
    renderChartView() {
        if (this.chart) {
            this.chart.destroy();
        }
        
        const ctx = this.canvas.getContext('2d');
        
        const data = {
            labels: ['Completed', 'In Progress', 'Not Passed', 'Not Started'],
            datasets: [{
                data: [
                    this.stats.completed,
                    this.stats.inProgress,
                    this.stats.notPassed,
                    this.stats.notStarted
                ],
                backgroundColor: [
                    '#10B981', // Green for completed
                    '#F59E0B', // Yellow for in progress
                    '#EF4444', // Red for not passed
                    '#9CA3AF'  // Gray for not started
                ],
                borderColor: [
                    '#059669',
                    '#D97706',
                    '#DC2626',
                    '#6B7280'
                ],
                borderWidth: 2
            }]
        };
        
        const options = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false // Use custom legend
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = total > 0 ? ((context.parsed / total) * 100).toFixed(1) : 0;
                            return `${context.label}: ${context.parsed} (${percentage}%)`;
                        }
                    }
                }
            }
        };
        
        if (this.currentChartType === 'bar') {
            options.scales = {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    }
                }
            };
        }
        
        this.chart = new Chart(ctx, {
            type: this.currentChartType,
            data: data,
            options: options
        });
    }
    
    renderListView() {
        const listContainer = document.getElementById('user-progress-list');
        if (!listContainer) return;
        
        // Sort users by completion status and score
        const sortedUsers = [...this.userData].sort((a, b) => {
            const progressA = a.progress || a;
            const progressB = b.progress || b;
            
            // Completed users first
            if (progressA.completed && !progressB.completed) return -1;
            if (!progressA.completed && progressB.completed) return 1;
            
            // Then by score (highest first)
            const scoreA = progressA.last_score || 0;
            const scoreB = progressB.last_score || 0;
            return scoreB - scoreA;
        });
        
        listContainer.innerHTML = sortedUsers.map(user => {
            const progress = user.progress || user;
            const userInfo = progress.user || progress;
            const scormData = user.scorm_data || {};
            
            let statusClass, statusText, statusIcon;
            
            if (progress.completed) {
                statusClass = 'bg-green-100 text-green-800';
                statusText = 'Completed';
                statusIcon = 'fa-check-circle';
            } else if (progress.last_accessed && progress.last_score && progress.last_score < 70) {
                statusClass = 'bg-red-100 text-red-800';
                statusText = 'Not Passed';
                statusIcon = 'fa-times-circle';
            } else if (progress.last_accessed) {
                statusClass = 'bg-yellow-100 text-yellow-800';
                statusText = 'In Progress';
                statusIcon = 'fa-clock';
            } else {
                statusClass = 'bg-gray-100 text-gray-800';
                statusText = 'Not Started';
                statusIcon = 'fa-circle';
            }
            
            const displayName = userInfo.get_full_name || userInfo.username || 'Unknown User';
            const score = progress.last_score ? `${parseFloat(progress.last_score).toFixed(1)}%` : '-';
            const lastAccessed = progress.last_accessed ? new Date(progress.last_accessed).toLocaleDateString() : '-';
            
            return `
                <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                    <div class="flex items-center space-x-3">
                        <div class="w-10 h-10 bg-gray-200 rounded-full flex items-center justify-center">
                            <i class="fas fa-user text-gray-500 text-sm"></i>
                        </div>
                        <div>
                            <div class="font-medium text-gray-900">${displayName}</div>
                            <div class="text-sm text-gray-500">Score: ${score} • Last accessed: ${lastAccessed}</div>
                        </div>
                    </div>
                    <div class="flex items-center space-x-3">
                        ${scormData.completion_percent ? `
                            <div class="w-24">
                                <div class="w-full bg-gray-200 rounded-full h-2">
                                    <div class="bg-blue-600 h-2 rounded-full" style="width: ${scormData.completion_percent}%"></div>
                                </div>
                                <span class="text-xs text-gray-500">${parseFloat(scormData.completion_percent).toFixed(1)}%</span>
                            </div>
                        ` : ''}
                        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusClass}">
                            <i class="fas ${statusIcon} mr-1"></i>
                            ${statusText}
                        </span>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    updateLegend() {
        // Update legend counts
        document.getElementById('completed-count').textContent = this.stats.completed;
        document.getElementById('in-progress-count').textContent = this.stats.inProgress;
        document.getElementById('not-passed-count').textContent = this.stats.notPassed;
        document.getElementById('not-started-count').textContent = this.stats.notStarted;
    }
    
    updateSummaryStats() {
        // Total users
        document.getElementById('total-users').textContent = this.stats.totalUsers;
        
        // Completion rate
        const completionRate = this.stats.totalUsers > 0 
            ? ((this.stats.completed / this.stats.totalUsers) * 100).toFixed(1)
            : 0;
        document.getElementById('completion-rate').textContent = `${completionRate}%`;
        
        // Average score
        const avgScore = this.stats.usersWithScores > 0 
            ? (this.stats.totalScore / this.stats.usersWithScores).toFixed(1)
            : 0;
        document.getElementById('avg-score').textContent = `${avgScore}%`;
        
        // Active users (users who have accessed the activity)
        const activeUsers = this.stats.completed + this.stats.inProgress + this.stats.notPassed;
        document.getElementById('active-users').textContent = activeUsers;
    }
    
    exportChart() {
        if (this.currentChartType === 'list') {
            // Export list as CSV
            this.exportAsCSV();
        } else {
            // Export chart as image
            this.exportAsImage();
        }
    }
    
    exportAsImage() {
        if (!this.chart) return;
        
        const link = document.createElement('a');
        link.download = `${this.chartTitle.toLowerCase().replace(/\s+/g, '_')}_chart.png`;
        link.href = this.chart.toBase64Image();
        link.click();
    }
    
    exportAsCSV() {
        const headers = ['User', 'Status', 'Score', 'Last Accessed', 'SCORM Progress'];
        const rows = this.userData.map(user => {
            const progress = user.progress || user;
            const userInfo = progress.user || progress;
            const scormData = user.scorm_data || {};
            
            let status;
            if (progress.completed) {
                status = 'Completed';
            } else if (progress.last_accessed && progress.last_score && progress.last_score < 70) {
                status = 'Not Passed';
            } else if (progress.last_accessed) {
                status = 'In Progress';
            } else {
                status = 'Not Started';
            }
            
            return [
                userInfo.get_full_name || userInfo.username || 'Unknown User',
                status,
                progress.last_score ? `${parseFloat(progress.last_score).toFixed(1)}%` : '-',
                progress.last_accessed ? new Date(progress.last_accessed).toLocaleDateString() : '-',
                scormData.completion_percent ? `${parseFloat(scormData.completion_percent).toFixed(1)}%` : '-'
            ];
        });
        
        const csvContent = [headers, ...rows]
            .map(row => row.map(field => `"${field}"`).join(','))
            .join('\n');
        
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `${this.chartTitle.toLowerCase().replace(/\s+/g, '_')}_data.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
    
    showError(message) {
        console.error('User Progress Chart error:', message);
        if (this.canvas) {
            const ctx = this.canvas.getContext('2d');
            ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            
            ctx.fillStyle = '#EF4444';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(message, this.canvas.width / 2, this.canvas.height / 2);
        }
    }
    
    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }
}

// Static create method for template compatibility
UserProgressChart.create = function(canvasId, userData) {
    console.log(' UserProgressChart.create called with:', canvasId, userData);
    return new UserProgressChart({
        canvasId: canvasId,
        userData: userData
    });
};

// Export for global use
window.UserProgressChart = UserProgressChart;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UserProgressChart;
}
