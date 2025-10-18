/**
 * Overview Page JavaScript
 * Handles overview page functionality and chart initialization
 */


// Overview page initialization
document.addEventListener('DOMContentLoaded', function() {
    
    // Initialize overview page functionality
    initializeOverviewPage();
});

/**
 * Initialize overview page functionality
 */
function initializeOverviewPage() {
    
    // Check if we're on the overview page
    if (!window.location.pathname.includes('/reports/overview')) {
        return;
    }
    
    // Initialize charts if they exist
    initializeOverviewCharts();
    
    // Initialize any other overview-specific functionality
    initializeOverviewFeatures();
}

/**
 * Initialize overview charts
 */
function initializeOverviewCharts() {
    
    // Check if Chart.js is available
    if (typeof Chart === 'undefined') {
        return;
    }
    
    // Chart initialization is handled by global components
    
    // Initialize courses chart if it exists
    const coursesChart = document.getElementById('courses-chart');
    if (coursesChart) {
        // Chart initialization is handled by global components
    }
}

/**
 * Initialize overview-specific features
 */
function initializeOverviewFeatures() {
    
    // Initialize any overview-specific features here
    // For example, data refresh, filters, etc.
    
    // Set up periodic data refresh if needed
    setupDataRefresh();
}

/**
 * Set up periodic data refresh for overview page
 */
function setupDataRefresh() {
    // Refresh data every 5 minutes if on overview page
    if (window.location.pathname.includes('/reports/overview')) {
        setInterval(function() {
            // Trigger data refresh if needed
            refreshOverviewData();
        }, 300000); // 5 minutes
    }
}

/**
 * Refresh overview data
 */
function refreshOverviewData() {
    
    // Refresh charts if they exist
    // Implementation would go here
}

// Export functions for global access
window.OverviewPage = {
    initialize: initializeOverviewPage,
    refreshData: refreshOverviewData
};

