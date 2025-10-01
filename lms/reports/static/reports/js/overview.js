/**
 * Overview Page JavaScript
 * Handles overview page functionality and chart initialization
 */

// console.log('Overview page JavaScript loaded');

// Overview page initialization
document.addEventListener('DOMContentLoaded', function() {
    // console.log('Overview page DOM loaded');
    
    // Initialize overview page functionality
    initializeOverviewPage();
});

/**
 * Initialize overview page functionality
 */
function initializeOverviewPage() {
    // console.log('Initializing overview page...');
    
    // Check if we're on the overview page
    if (!window.location.pathname.includes('/reports/overview')) {
        // console.log('Not on overview page, skipping initialization');
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
    // console.log('Initializing overview charts...');
    
    // Check if Chart.js is available
    if (typeof Chart === 'undefined') {
        console.warn('Chart.js not available, charts will not be initialized');
        return;
    }
    
        // Chart initialization is handled by global components
    }
    
    // Initialize courses chart if it exists
    const coursesChart = document.getElementById('courses-chart');
    if (coursesChart) {
        // console.log('Courses chart canvas found');
        // Chart initialization is handled by global components
    }
}

/**
 * Initialize overview-specific features
 */
function initializeOverviewFeatures() {
    // console.log('Initializing overview features...');
    
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
            // console.log('Refreshing overview data...');
            // Trigger data refresh if needed
            refreshOverviewData();
        }, 300000); // 5 minutes
    }
}

/**
 * Refresh overview data
 */
function refreshOverviewData() {
    // console.log('Refreshing overview data...');
    
    // Refresh charts if they exist
    }
    
}

// Export functions for global access
window.OverviewPage = {
    initialize: initializeOverviewPage,
    refreshData: refreshOverviewData
};

// console.log('Overview page JavaScript initialization complete');
