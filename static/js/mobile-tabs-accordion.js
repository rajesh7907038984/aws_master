/**
 * Mobile Tabs Accordion JavaScript
 * Provides responsive tab-to-accordion functionality for mobile devices
 * 
 * Features:
 * - Converts desktop tabs to mobile accordions
 * - Handles content synchronization between desktop tabs and mobile accordion
 * - Accessible keyboard navigation
 * - Touch-friendly interaction
 * - Automatic content population from desktop tabs
 * 
 * Usage:
 * 1. Include mobile-tabs-accordion.css
 * 2. Include this JavaScript file
 * 3. Call MobileTabsAccordion.init() when DOM is ready
 * 4. Use data-tab-target on desktop tab buttons
 * 5. Use data-accordion-target on mobile accordion headers
 * 
 * Version: 2.2.2 - Fixed duplicate script loading issue
 */

// Prevent duplicate class declaration
if (typeof window.MobileTabsAccordion === 'undefined') {

class MobileTabsAccordion {
    constructor() {
        this.containers = [];
        this.activeAccordionItems = new Map();
        this.isInitialized = false;
        
        // Bind methods to preserve context
        this.handleTabClick = this.handleTabClick.bind(this);
        this.handleAccordionClick = this.handleAccordionClick.bind(this);
        this.handleKeyDown = this.handleKeyDown.bind(this);
        this.handleResize = this.handleResize.bind(this);
    }
    
    /**
     * Initialize the mobile tabs accordion system
     */
    static init() {
        if (window.mobileTabsAccordionInstance) {
            console.log('MobileTabsAccordion already initialized');
            return window.mobileTabsAccordionInstance;
        }
        
        window.mobileTabsAccordionInstance = new MobileTabsAccordion();
        window.mobileTabsAccordionInstance.initialize();
        return window.mobileTabsAccordionInstance;
    }
    
    /**
     * Initialize the accordion functionality
     */
    initialize() {
        if (this.isInitialized) {
            console.log('MobileTabsAccordion already initialized');
            return;
        }
        
        console.log('Initializing MobileTabsAccordion');
        
        // Find all tab containers
        this.findTabContainers();
        
        // Set up each container
        this.containers.forEach(container => this.setupContainer(container));
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Set up resize listener for responsive behavior
        window.addEventListener('resize', this.handleResize);
        
        this.isInitialized = true;
        console.log(`MobileTabsAccordion initialized with ${this.containers.length} containers`);
        
        // Set up chart monitoring for mobile view
        this.setupChartMonitoring();
    }
    
    /**
     * Check if current viewport is mobile size
     */
    isMobileView() {
        return window.innerWidth <= 768;
    }
    
    /**
     * Optimize accordion content for mobile display
     */
    optimizeAccordionContentForMobile(accordionContent) {
        if (!this.isMobileView()) return;
        
        // Handle tables - convert to mobile-friendly format
        this.optimizeTablesForMobile(accordionContent);
        
        // Handle wide images and charts
        const images = accordionContent.querySelectorAll('img, canvas');
        images.forEach(img => {
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
        });
        
        // Special handling for Chart.js canvases
        this.optimizeChartsForMobile(accordionContent);
        
        // Handle grid layouts that might overflow
        const grids = accordionContent.querySelectorAll('.grid');
        grids.forEach(grid => {
            // Force single column on very small screens
            if (window.innerWidth <= 480) {
                grid.style.gridTemplateColumns = '1fr';
            }
        });
        
        // Handle flexbox items that might cause overflow
        const flexContainers = accordionContent.querySelectorAll('.flex');
        flexContainers.forEach(flex => {
            // Convert horizontal flex to vertical on mobile for better fit
            if (flex.classList.contains('items-center') && window.innerWidth <= 480) {
                flex.style.flexDirection = 'column';
                flex.style.alignItems = 'flex-start';
            }
        });
        
        console.log('Optimized accordion content for mobile display');
    }
    
    /**
     * Convert tables to mobile-friendly accordion format
     */
    optimizeTablesForMobile(accordionContent) {
        const tables = accordionContent.querySelectorAll('table');
        
        tables.forEach((table, index) => {
            // Skip if already optimized
            if (table.closest('.mobile-table-container')) return;
            
            const tableTitle = this.getTableTitle(table);
            const mobileContainer = this.createMobileTableContainer(table, tableTitle, index);
            
            // Replace table with mobile container
            table.parentNode.insertBefore(mobileContainer, table);
            table.remove();
            
            console.log(`Converted table ${index + 1} to mobile format: ${tableTitle}`);
        });
    }
    
    /**
     * Get table title from context
     */
    getTableTitle(table) {
        // Try to find a preceding header
        let prevElement = table.previousElementSibling;
        while (prevElement) {
            if (prevElement.tagName.match(/^H[1-6]$/)) {
                return prevElement.textContent.trim();
            }
            if (prevElement.textContent.trim().length > 0 && prevElement.textContent.length < 100) {
                return prevElement.textContent.trim();
            }
            prevElement = prevElement.previousElementSibling;
        }
        
        // Fallback titles based on content
        const firstCellText = table.querySelector('th, td')?.textContent?.trim();
        if (firstCellText && firstCellText.includes('Course')) return 'Courses Table';
        if (firstCellText && firstCellText.includes('Activity')) return 'Learning Activities Table';  
        if (firstCellText && firstCellText.includes('Assessment')) return 'Assessments Table';
        if (firstCellText && firstCellText.includes('Certificate')) return 'Certificates Table';
        
        return 'Data Table';
    }
    
    /**
     * Create mobile table container with toggle and scroll options
     */
    createMobileTableContainer(table, title, index) {
        const container = document.createElement('div');
        container.className = 'mobile-table-container';
        
        // Create toggle button
        const toggle = document.createElement('button');
        toggle.className = 'mobile-table-toggle';
        toggle.innerHTML = `
            <span>${title}</span>
            <svg class="mobile-table-toggle-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
            </svg>
        `;
        
        // Create scrollable wrapper
        const scrollWrapper = document.createElement('div');
        scrollWrapper.className = 'mobile-table-scroll-wrapper';
        
        // Clone and optimize table for scrolling
        const scrollTable = table.cloneNode(true);
        scrollWrapper.appendChild(scrollTable);
        
        // Create card-style view for very small screens
        const cardContainer = this.createCardView(table);
        
        // Assemble container
        container.appendChild(toggle);
        container.appendChild(scrollWrapper);
        container.appendChild(cardContainer);
        
        // Add event listener for toggle
        toggle.addEventListener('click', () => {
            const isActive = toggle.classList.contains('active');
            
            if (isActive) {
                toggle.classList.remove('active');
                scrollWrapper.classList.remove('active');
            } else {
                toggle.classList.add('active');
                scrollWrapper.classList.add('active');
            }
            
            console.log(`Table toggle ${isActive ? 'closed' : 'opened'}: ${title}`);
        });
        
        return container;
    }
    
    /**
     * Create card-style view of table data
     */
    createCardView(table) {
        const cardContainer = document.createElement('div');
        cardContainer.className = 'mobile-table-cards';
        
        const headers = Array.from(table.querySelectorAll('thead th, tr:first-child th, tr:first-child td')).map(th => th.textContent.trim());
        const rows = table.querySelectorAll('tbody tr, tr');
        
        // Skip header row if no tbody
        const startIndex = table.querySelector('tbody') ? 0 : 1;
        
        for (let i = startIndex; i < rows.length; i++) {
            const row = rows[i];
            const cells = row.querySelectorAll('td, th');
            
            if (cells.length === 0) continue;
            
            const card = document.createElement('div');
            card.className = 'mobile-table-card';
            
            // Card header from first cell
            const cardHeader = document.createElement('div');
            cardHeader.className = 'mobile-table-card-header';
            cardHeader.textContent = cells[0]?.textContent?.trim() || `Item ${i}`;
            card.appendChild(cardHeader);
            
            // Card rows for remaining cells
            for (let j = 1; j < cells.length && j < headers.length; j++) {
                const cardRow = document.createElement('div');
                cardRow.className = 'mobile-table-card-row';
                
                const label = document.createElement('div');
                label.className = 'mobile-table-card-label';
                label.textContent = headers[j] || `Field ${j}`;
                
                const value = document.createElement('div');
                value.className = 'mobile-table-card-value';
                value.innerHTML = cells[j]?.innerHTML || '-';
                
                cardRow.appendChild(label);
                cardRow.appendChild(value);
                card.appendChild(cardRow);
            }
            
            cardContainer.appendChild(card);
        }
        
        return cardContainer;
    }
    
    /**
     * Optimize charts for mobile display
     */
    optimizeChartsForMobile(accordionContent) {
        const chartContainers = accordionContent.querySelectorAll('.h-64, .chart-container, [class*="h-"], canvas');
        
        chartContainers.forEach(container => {
            // Handle chart containers
            if (container.classList.contains('h-64') || container.classList.contains('chart-container')) {
                container.style.height = '300px'; // Fixed height for mobile
                container.style.maxWidth = '100%';
                container.style.overflow = 'hidden';
                
                // Find canvas inside container
                const canvas = container.querySelector('canvas');
                if (canvas) {
                    this.optimizeCanvasForMobile(canvas);
                }
            }
            // Handle direct canvas elements
            else if (container.tagName === 'CANVAS') {
                this.optimizeCanvasForMobile(container);
            }
        });
        
        // Handle chart wrapper divs with specific classes
        const chartWrappers = accordionContent.querySelectorAll('.rounded-full.flex, .flex.items-center.justify-center');
        chartWrappers.forEach(wrapper => {
            if (wrapper.querySelector('canvas')) {
                wrapper.style.minHeight = '250px';
                wrapper.style.maxWidth = '100%';
                wrapper.style.flexDirection = 'column';
                wrapper.style.alignItems = 'center';
                
                const canvas = wrapper.querySelector('canvas');
                if (canvas) {
                    this.optimizeCanvasForMobile(canvas);
                }
            }
        });
        
        console.log('Optimized charts for mobile display');
    }
    
    /**
     * Optimize individual canvas elements for mobile
     */
    optimizeCanvasForMobile(canvas) {
        // Set responsive dimensions
        canvas.style.maxWidth = '100%';
        canvas.style.height = 'auto';
        canvas.style.display = 'block';
        canvas.style.margin = '0 auto';
        
        // Force chart to be responsive if Chart.js instance exists
        const chartId = canvas.id;
        if (chartId && window.Chart) {
            // Try to get chart instance and update responsive settings
            setTimeout(() => {
                try {
                    const chartInstances = Chart.getChart ? Chart.getChart(canvas) : null;
                    if (chartInstances) {
                        chartInstances.options = chartInstances.options || {};
                        chartInstances.options.responsive = true;
                        chartInstances.options.maintainAspectRatio = false;
                        chartInstances.resize();
                        console.log(`Resized chart: ${chartId}`);
                    }
                } catch (error) {
                    console.warn(`Could not resize chart ${chartId}:`, error);
                }
            }, 100);
        }
        
        // Set container parent styles if needed
        const parent = canvas.parentElement;
        if (parent) {
            parent.style.maxWidth = '100%';
            parent.style.overflow = 'hidden';
        }
    }
    
    /**
     * Reinitialize charts in specific content area
     */
    reinitializeChartsInContent(content) {
        const canvases = content.querySelectorAll('canvas');
        
        canvases.forEach(canvas => {
            // Try to trigger chart re-render if it's a Chart.js chart
            const canvasId = canvas.id;
            if (canvasId && window.Chart) {
                try {
                    // Check if there's an existing chart instance
                    const existingChart = Chart.getChart ? Chart.getChart(canvas) : null;
                    
                    if (!existingChart) {
                        console.log(`No existing chart found for ${canvasId}, will try to recreate in force reinitialization`);
                    } else {
                        // Update existing chart to be responsive
                        existingChart.options.responsive = true;
                        existingChart.options.maintainAspectRatio = false;
                        existingChart.resize();
                        console.log(`Updated existing chart: ${canvasId}`);
                    }
                } catch (error) {
                    console.warn(`Could not reinitialize chart ${canvasId}:`, error);
                }
            }
            
            // Ensure canvas is properly styled for mobile
            this.optimizeCanvasForMobile(canvas);
        });
        
        // Handle specific chart types that might need special treatment
        this.handleSpecificCharts(content);
        
        // Also handle any chart containers that might need resizing
        const chartContainers = content.querySelectorAll('.h-64, .chart-container');
        chartContainers.forEach(container => {
            // Force a reflow to ensure proper sizing
            container.style.display = 'none';
            container.offsetHeight; // Trigger reflow
            container.style.display = 'block';
        });
        
        console.log('Reinitialized charts in mobile accordion content');
    }
    
    /**
     * Handle specific chart types that need special reinitialization
     */
    handleSpecificCharts(content) {
        // Handle activity chart specifically
        const activityChart = content.querySelector('#activity-chart');
        if (activityChart && window.Chart) {
            try {
                const existingChart = Chart.getChart(activityChart);
                if (existingChart) {
                    existingChart.options.responsive = true;
                    existingChart.options.maintainAspectRatio = false;
                    existingChart.resize();
                    console.log('Updated activity chart for mobile');
                }
            } catch (error) {
                console.warn('Could not update activity chart:', error);
            }
        }
        
        // Handle courses chart
        const coursesChart = content.querySelector('#courses-chart');
        if (coursesChart && window.Chart) {
            try {
                const existingChart = Chart.getChart(coursesChart);
                if (existingChart) {
                    existingChart.options.responsive = true;
                    existingChart.options.maintainAspectRatio = false;
                    existingChart.resize();
                    console.log('Updated courses chart for mobile');
                }
            } catch (error) {
                console.warn('Could not update courses chart:', error);
            }
        }
    }
    
    /**
     * Force chart reinitialization by recreating charts from scratch
     */
    forceChartReinitialization(content) {
        console.log('Force reinitializing charts in mobile accordion...');
        
        if (!window.Chart) {
            console.warn('Chart.js library not available');
            return;
        }
        
        // Find activity chart canvas
        const activityCanvas = content.querySelector('#activity-chart');
        if (activityCanvas) {
            try {
                // Destroy existing chart if it exists
                const existingChart = window.Chart.getChart ? window.Chart.getChart(activityCanvas) : null;
                if (existingChart) {
                    existingChart.destroy();
                    console.log('Destroyed existing activity chart');
                }
                
                // Try to recreate the chart by calling the original creation function
                if (typeof window.generateChartData === 'function') {
                    const chartData = window.generateChartData('month');
                    if (chartData && chartData.labels) {
                        const ctx = activityCanvas.getContext('2d');
                        window.activityChart = new window.Chart(ctx, {
                            type: 'line',
                            data: {
                                labels: chartData.labels,
                                datasets: [
                                    {
                                        label: 'Logins',
                                        data: chartData.loginData || [],
                                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                                        borderColor: 'rgba(59, 130, 246, 1)',
                                        borderWidth: 2,
                                        pointBackgroundColor: 'rgba(59, 130, 246, 1)',
                                        pointRadius: 4,
                                        tension: 0.4,
                                        fill: false
                                    },
                                    {
                                        label: 'Course completions',
                                        data: chartData.completionData || [],
                                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                                        borderColor: 'rgba(16, 185, 129, 1)',
                                        borderWidth: 2,
                                        pointBackgroundColor: 'rgba(16, 185, 129, 1)',
                                        pointRadius: 4,
                                        tension: 0.4,
                                        fill: false
                                    }
                                ]
                            },
                            options: {
                                responsive: true,
                                maintainAspectRatio: false,
                                scales: {
                                    y: {
                                        beginAtZero: true,
                                        ticks: {
                                            stepSize: 1
                                        }
                                    }
                                },
                                plugins: {
                                    legend: {
                                        display: false
                                    }
                                }
                            }
                        });
                        console.log('Successfully recreated activity chart in mobile view');
                    } else {
                        console.log('Chart data not available, creating empty activity chart');
                        this.createEmptyActivityChart(activityCanvas);
                    }
                } else {
                    console.log('generateChartData function not available, creating empty activity chart');
                    this.createEmptyActivityChart(activityCanvas);
                }
            } catch (error) {
                console.error('Failed to force reinitialize activity chart:', error);
            }
        }
        
        // Handle courses doughnut chart
        const coursesCanvas = content.querySelector('#courses-chart');
        if (coursesCanvas) {
            try {
                // Destroy existing chart if it exists
                const existingChart = window.Chart.getChart ? window.Chart.getChart(coursesCanvas) : null;
                if (existingChart) {
                    existingChart.destroy();
                    console.log('Destroyed existing courses chart');
                }
                
                // Get course data from the DOM elements in the content area first, then fallback to document
                const getElementText = (id) => {
                    let element = content.querySelector(`#${id}`) || document.getElementById(id);
                    return element ? element.textContent : '';
                };
                
                const completedText = getElementText('completed-count');
                const inProgressText = getElementText('in-progress-count');
                const notStartedText = getElementText('not-started-count');
                const notPassedText = getElementText('not-passed-count');
                
                // Extract numbers from text
                const completedCourses = parseInt(completedText.match(/\d+/)?.[0] || '0');
                const inProgressCourses = parseInt(inProgressText.match(/\d+/)?.[0] || '0');
                const notStartedCourses = parseInt(notStartedText.match(/\d+/)?.[0] || '0');
                const notPassedCourses = parseInt(notPassedText.match(/\d+/)?.[0] || '0');
                
                new window.Chart(coursesCanvas, {
                    type: 'doughnut',
                    data: {
                        labels: ['Completed', 'In Progress', 'Not Started', 'Not Passed'],
                        datasets: [{
                            data: [completedCourses, inProgressCourses, notStartedCourses, notPassedCourses],
                            backgroundColor: ['#10B981', '#F59E0B', '#9CA3AF', '#EF4444'],
                            borderWidth: 0,
                            hoverOffset: 4
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '70%',
                        plugins: {
                            legend: {
                                display: false
                            },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        const label = context.label || '';
                                        const value = context.raw || 0;
                                        const total = context.dataset.data.reduce((acc, val) => acc + val, 0);
                                        const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
                                        return `${label}: ${value} (${percentage}%)`;
                                    }
                                }
                            }
                        }
                    }
                });
                console.log(`Successfully recreated courses chart with data: [${completedCourses}, ${inProgressCourses}, ${notStartedCourses}, ${notPassedCourses}]`);
            } catch (error) {
                console.error('Failed to force reinitialize courses chart:', error);
            }
        }
    }
    
    /**
     * Initialize global activity chart as fallback
     */
    createEmptyActivityChart(canvas) {
        try {
            // Use global activity chart component instead of custom implementation
            if (window.GlobalActivityChart) {
                console.log('Initializing global activity chart as fallback...');
                window.globalActivityChart = new GlobalActivityChart({
                    canvasId: canvas.id,
                    apiEndpoint: '/users/api/dashboard-activity-data/',
                    defaultPeriod: 'month'
                });
                console.log('Global activity chart initialized as fallback');
            } else {
                console.warn('GlobalActivityChart not available, skipping chart initialization');
            }
        } catch (error) {
            console.error('Failed to initialize global activity chart:', error);
        }
    }
    
    /**
     * Set up chart monitoring for mobile accordion initialization
     */
    setupChartMonitoring() {
        // Monitor for Chart.js library loading
        const checkChartLibrary = () => {
            if (typeof window.Chart !== 'undefined') {
                console.log('Chart.js library detected, setting up mobile chart monitoring');
                
                // Set up a periodic check for missing charts in mobile accordions
                setTimeout(() => {
                    this.checkAndFixMobileCharts();
                }, 2000);
                
                // Also check after a longer delay in case charts are created asynchronously
                setTimeout(() => {
                    this.checkAndFixMobileCharts();
                }, 5000);
            } else {
                // Check again in 500ms if Chart.js isn't loaded yet
                setTimeout(checkChartLibrary, 500);
            }
        };
        
        checkChartLibrary();
    }
    
    /**
     * Check and fix missing charts in mobile accordions
     */
    checkAndFixMobileCharts() {
        if (!this.isMobileView()) return;
        
        console.log('Checking for missing charts in mobile accordions...');
        
        // Find all accordion content areas that should have charts
        const accordionContents = document.querySelectorAll('.tab-accordion-content');
        
        accordionContents.forEach(content => {
            const canvases = content.querySelectorAll('canvas');
            canvases.forEach(canvas => {
                // Check if canvas has a chart instance
                const hasChart = window.Chart && window.Chart.getChart ? 
                                 window.Chart.getChart(canvas) !== null : false;
                
                if (!hasChart && canvas.offsetHeight > 0 && canvas.offsetWidth > 0) {
                    console.log(`Found canvas without chart in mobile accordion: ${canvas.id || 'unnamed'}`);
                    // Try to reinitialize the chart
                    setTimeout(() => {
                        this.forceChartReinitialization(content);
                    }, 100);
                }
            });
        });
    }
    
    /**
     * Set up global event listeners
     */
    setupEventListeners() {
        // This method is called during initialization
        // Individual event listeners are set up in setupContainer method
        // for each container's specific elements
        console.log('Setting up global event listeners');
    }
    
    /**
     * Find all tab containers in the document
     */
    findTabContainers() {
        // Look for containers with both desktop tabs and accordion elements
        const containers = document.querySelectorAll('.tab-responsive-container, .tab-container, [data-tab-container]');
        
        containers.forEach(container => {
            const hasDesktopTabs = container.querySelector('.tab-headers-desktop, .tab-btn[data-tab-target]');
            const hasAccordion = container.querySelector('.tab-accordion-container');
            
            if (hasDesktopTabs || hasAccordion) {
                this.containers.push(container);
                console.log('Found tab container:', container);
            }
        });
        
        // Also look for standalone tab systems
        if (this.containers.length === 0) {
            const standaloneTabHeaders = document.querySelectorAll('.tab-headers-desktop');
            standaloneTabHeaders.forEach(header => {
                const container = header.closest('div, section, article') || document.body;
                if (!this.containers.includes(container)) {
                    this.containers.push(container);
                    console.log('Found standalone tab system:', container);
                }
            });
        }
        
        // IMPORTANT: Don't interfere with existing tab systems that use onclick handlers
        // Skip containers that have tab-header elements with onclick attributes
        this.containers = this.containers.filter(container => {
            const onclickTabs = container.querySelectorAll('.tab-header[onclick]');
            if (onclickTabs.length > 0) {
                console.log('Skipping container with onclick tab handlers to avoid conflicts:', container);
                return false;
            }
            return true;
        });
    }
    
    /**
     * Set up a specific container
     */
    setupContainer(container) {
        console.log('Setting up container:', container);
        
        // Find desktop tabs
        const desktopTabs = container.querySelectorAll('.tab-btn[data-tab-target], .tab-button[data-tab-target]');
        
        // Find or create accordion container
        let accordionContainer = container.querySelector('.tab-accordion-container');
        if (!accordionContainer && desktopTabs.length > 0) {
            accordionContainer = this.createAccordionContainer(container, desktopTabs);
        }
        
        if (accordionContainer) {
            // Populate accordion from desktop tabs
            this.populateAccordionFromTabs(desktopTabs, accordionContainer);
            
            // Set up accordion event handlers
            this.setupAccordionEventHandlers(accordionContainer);
            
            // Set up initial state
            this.setInitialState(container, desktopTabs, accordionContainer);
        }
        
        // Set up desktop tab event handlers
        this.setupDesktopTabEventHandlers(desktopTabs);
    }
    
    /**
     * Create accordion container if it doesn't exist
     */
    createAccordionContainer(container, desktopTabs) {
        console.log('Creating accordion container');
        
        const accordionContainer = document.createElement('div');
        accordionContainer.className = 'tab-accordion-container';
        accordionContainer.style.display = 'none'; // Hidden by default, shown by CSS media query
        
        // Insert after desktop tabs or at the beginning
        const desktopContainer = container.querySelector('.tab-headers-desktop');
        if (desktopContainer && desktopContainer.parentNode) {
            desktopContainer.parentNode.insertBefore(accordionContainer, desktopContainer.nextSibling);
        } else {
            container.appendChild(accordionContainer);
        }
        
        return accordionContainer;
    }
    
    /**
     * Populate accordion from desktop tabs
     */
    populateAccordionFromTabs(desktopTabs, accordionContainer) {
        // Clear existing accordion items
        accordionContainer.innerHTML = '';
        
        desktopTabs.forEach((tab, index) => {
            const tabTarget = tab.getAttribute('data-tab-target');
            const tabText = tab.textContent.trim();
            
            if (!tabTarget || !tabText) return;
            
            // Create accordion item
            const accordionItem = document.createElement('div');
            accordionItem.className = 'tab-accordion-item';
            
            // Create accordion header
            const accordionHeader = document.createElement('button');
            accordionHeader.type = 'button';
            accordionHeader.className = 'tab-accordion-header';
            accordionHeader.setAttribute('data-accordion-target', `${tabTarget}-accordion`);
            accordionHeader.setAttribute('aria-expanded', 'false');
            accordionHeader.setAttribute('aria-controls', `${tabTarget}-accordion`.substring(1));
            
            // Add text and icon
            accordionHeader.innerHTML = `
                <span>${tabText}</span>
                <svg class="tab-accordion-icon w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                </svg>
            `;
            
            // Create accordion content
            const accordionContent = document.createElement('div');
            accordionContent.id = `${tabTarget}-accordion`.substring(1);
            accordionContent.className = 'tab-accordion-content';
            accordionContent.setAttribute('aria-hidden', 'true');
            
            // Set first item as active if the corresponding desktop tab is active
            if (tab.classList.contains('active') || index === 0) {
                accordionHeader.classList.add('active');
                accordionHeader.setAttribute('aria-expanded', 'true');
                accordionContent.classList.add('active');
                accordionContent.setAttribute('aria-hidden', 'false');
                this.activeAccordionItems.set(accordionContainer, accordionItem);
            }
            
            accordionItem.appendChild(accordionHeader);
            accordionItem.appendChild(accordionContent);
            accordionContainer.appendChild(accordionItem);
        });
        
        console.log(`Created ${desktopTabs.length} accordion items`);
    }
    
    /**
     * Set up accordion event handlers
     */
    setupAccordionEventHandlers(accordionContainer) {
        const accordionHeaders = accordionContainer.querySelectorAll('.tab-accordion-header');
        
        accordionHeaders.forEach(header => {
            header.addEventListener('click', this.handleAccordionClick);
            header.addEventListener('keydown', this.handleKeyDown);
        });
    }
    
    /**
     * Set up desktop tab event handlers
     */
    setupDesktopTabEventHandlers(desktopTabs) {
        desktopTabs.forEach(tab => {
            tab.addEventListener('click', this.handleTabClick);
        });
        console.log(`Set up ${desktopTabs.length} desktop tab event handlers`);
    }
    
    /**
     * Handle desktop tab clicks
     */
    handleTabClick(event) {
        const tab = event.currentTarget;
        const tabTarget = tab.getAttribute('data-tab-target');
        
        if (!tabTarget) return;
        
        console.log('Tab clicked:', tab.id, 'Target:', tabTarget);
        
        // Find the container
        const container = tab.closest('.tab-responsive-container, .tab-container, [data-tab-container]') || 
                         tab.closest('div, section, article');
        
        // Update desktop tabs - this should hide previous and show new content
        this.updateDesktopTabs(container, tab);
        
        // Update corresponding accordion
        this.updateAccordionFromDesktopTab(container, tab, tabTarget);
        
        // Don't sync content to preserve unique content per tab
        // this.syncContentToAccordion(tabTarget);
        console.log('Tab switch completed for:', tabTarget);
    }
    
    /**
     * Handle accordion clicks
     */
    handleAccordionClick(event) {
        const header = event.currentTarget;
        const accordionTarget = header.getAttribute('data-accordion-target');
        
        if (!accordionTarget) {
            console.warn('No accordion target found for header:', header);
            return;
        }
        
        console.log('Accordion clicked:', accordionTarget);
        
        // Find the container
        const container = header.closest('.tab-responsive-container, .tab-container, [data-tab-container]') || 
                         header.closest('div, section, article');
        
        const accordionContainer = header.closest('.tab-accordion-container');
        const accordionItem = header.closest('.tab-accordion-item');
        
        if (!accordionContainer) {
            console.warn('No accordion container found for header:', header);
            return;
        }
        
        if (!accordionItem) {
            console.warn('No accordion item found for header:', header);
            return;
        }
        
        // Toggle accordion item
        this.toggleAccordionItem(accordionContainer, accordionItem, header);
        
        // For mobile accordion, we need to ensure the accordion content is populated
        const desktopTabTarget = accordionTarget.replace('-accordion', '');
        const desktopContent = document.querySelector(desktopTabTarget);
        const accordionContent = document.querySelector(`#${accordionTarget.substring(1)}`);
        
        console.log('Desktop content found:', !!desktopContent, 'Accordion content found:', !!accordionContent);
        
        // Sync content from desktop to accordion if accordion is empty or needs content
        if (desktopContent && accordionContent) {
            if (accordionContent.innerHTML.trim() === '' || 
                accordionContent.innerHTML.includes('Content will be populated by JavaScript')) {
                
                console.log('Populating accordion content from desktop tab');
                
                // Clone and optimize content for mobile
                accordionContent.innerHTML = desktopContent.innerHTML;
                this.optimizeAccordionContentForMobile(accordionContent);
                
                // Force chart reinitialization for the newly populated content
                setTimeout(() => {
                    this.forceChartReinitialization(accordionContent);
                }, 500);
                
                console.log('Populated accordion content for:', accordionTarget);
            } else {
                console.log('Accordion content already populated');
            }
        } else {
            console.warn('Missing content elements - Desktop:', !!desktopContent, 'Accordion:', !!accordionContent);
        }
        
        // Force chart reinitialization when accordion is opened (even if content already exists)
        if (header.classList.contains('active') && accordionContent) {
            setTimeout(() => {
                this.forceChartReinitialization(accordionContent);
            }, 100);
        }
        
        // Don't update desktop tabs from mobile accordion to preserve unique content
        console.log('Mobile accordion toggle completed for:', accordionTarget);
    }
    
    /**
     * Handle keyboard navigation
     */
    handleKeyDown(event) {
        const header = event.currentTarget;
        
        switch (event.key) {
            case 'Enter':
            case ' ':
                event.preventDefault();
                header.click();
                break;
            case 'ArrowDown':
            case 'ArrowUp':
                event.preventDefault();
                this.navigateAccordion(header, event.key === 'ArrowDown' ? 1 : -1);
                break;
            case 'Home':
                event.preventDefault();
                this.focusFirstAccordionItem(header);
                break;
            case 'End':
                event.preventDefault();
                this.focusLastAccordionItem(header);
                break;
        }
    }
    
    /**
     * Navigate accordion with keyboard
     */
    navigateAccordion(currentHeader, direction) {
        const accordionContainer = currentHeader.closest('.tab-accordion-container');
        const headers = Array.from(accordionContainer.querySelectorAll('.tab-accordion-header'));
        const currentIndex = headers.indexOf(currentHeader);
        const nextIndex = currentIndex + direction;
        
        if (nextIndex >= 0 && nextIndex < headers.length) {
            headers[nextIndex].focus();
        }
    }
    
    /**
     * Focus first accordion item
     */
    focusFirstAccordionItem(currentHeader) {
        const accordionContainer = currentHeader.closest('.tab-accordion-container');
        const firstHeader = accordionContainer.querySelector('.tab-accordion-header');
        if (firstHeader) firstHeader.focus();
    }
    
    /**
     * Focus last accordion item
     */
    focusLastAccordionItem(currentHeader) {
        const accordionContainer = currentHeader.closest('.tab-accordion-container');
        const headers = accordionContainer.querySelectorAll('.tab-accordion-header');
        const lastHeader = headers[headers.length - 1];
        if (lastHeader) lastHeader.focus();
    }
    
    /**
     * Update desktop tabs
     */
    updateDesktopTabs(container, activeTab) {
        // Get all tabs and content within the document (not just container)
        const allTabs = document.querySelectorAll('.tab-btn, .tab-button');
        const allContents = document.querySelectorAll('.tab-pane');
        
        console.log('Updating desktop tabs:', { 
            activeTab: activeTab.id, 
            allTabs: allTabs.length, 
            allContents: allContents.length 
        });
        
        // Remove active class from ALL tabs
        allTabs.forEach(tab => {
            tab.classList.remove('active', 'border-blue-500', 'text-blue-600');
            tab.classList.add('border-transparent', 'text-gray-500');
            console.log('Deactivated tab:', tab.id);
        });
        
        // Hide ALL content panes (but exclude help sections)
        allContents.forEach(content => {
            // Don't hide help sections or file upload components
            if (content.closest('.bg-blue-50') || content.closest('[class*="help"]')) {
                return;
            }
            content.classList.remove('active');
            content.classList.add('hidden');
            content.style.setProperty('display', 'none', 'important');
            content.style.setProperty('visibility', 'hidden', 'important');
            content.style.setProperty('opacity', '0', 'important');
            console.log('Hidden content:', content.id);
        });
        
        // Activate clicked tab
        activeTab.classList.add('active', 'border-blue-500', 'text-blue-600');
        activeTab.classList.remove('border-transparent', 'text-gray-500');
        console.log('Activated tab:', activeTab.id);
        
        // Show corresponding content
        const tabTarget = activeTab.getAttribute('data-tab-target');
        if (tabTarget) {
            const targetContent = document.querySelector(tabTarget);
            if (targetContent) {
                targetContent.classList.add('active');
                targetContent.classList.remove('hidden');
                
                // Force display with multiple approaches and !important
                targetContent.style.setProperty('display', 'block', 'important');
                targetContent.style.setProperty('visibility', 'visible', 'important');
                targetContent.style.setProperty('opacity', '1', 'important');
                targetContent.style.setProperty('height', 'auto', 'important');
                targetContent.style.setProperty('overflow', 'visible', 'important');
                
                console.log('Activated content:', targetContent.id);
                console.log('Content styles applied:', {
                    display: targetContent.style.display,
                    visibility: targetContent.style.visibility,
                    opacity: targetContent.style.opacity
                });
                
                // Double-check that other content is hidden
                allContents.forEach(content => {
                    if (content !== targetContent) {
                        content.style.setProperty('display', 'none', 'important');
                        console.log('Ensured hidden:', content.id);
                    }
                });
                
            } else {
                console.warn('Target content not found:', tabTarget);
            }
        }
    }
    
    /**
     * Update accordion from desktop tab
     */
    updateAccordionFromDesktopTab(container, activeTab, tabTarget) {
        const accordionContainer = container.querySelector('.tab-accordion-container');
        if (!accordionContainer) return;
        
        const accordionTarget = `${tabTarget}-accordion`;
        const accordionHeader = accordionContainer.querySelector(`[data-accordion-target="${accordionTarget}"]`);
        
        if (accordionHeader) {
            const accordionItem = accordionHeader.closest('.tab-accordion-item');
            this.activateAccordionItem(accordionContainer, accordionItem, accordionHeader);
        }
    }
    
    /**
     * Update desktop tab from accordion
     */
    updateDesktopTabFromAccordion(container, desktopTabTarget) {
        const desktopTab = container.querySelector(`[data-tab-target="${desktopTabTarget}"]`);
        if (desktopTab) {
            this.updateDesktopTabs(container, desktopTab);
        }
    }
    
    /**
     * Toggle accordion item
     */
    toggleAccordionItem(accordionContainer, accordionItem, header) {
        const isCurrentlyActive = header.classList.contains('active');
        
        console.log('Toggling accordion item:', header.textContent.trim(), 'Currently active:', isCurrentlyActive);
        
        if (isCurrentlyActive) {
            // Close current item
            this.deactivateAccordionItem(accordionItem, header);
            this.activeAccordionItems.delete(accordionContainer);
            console.log('Closed accordion item');
        } else {
            // Close all other items and open this one
            this.closeAllAccordionItems(accordionContainer);
            this.activateAccordionItem(accordionContainer, accordionItem, header);
            console.log('Opened accordion item');
        }
    }
    
    /**
     * Activate accordion item
     */
    activateAccordionItem(accordionContainer, accordionItem, header) {
        this.closeAllAccordionItems(accordionContainer);
        
        const content = accordionItem.querySelector('.tab-accordion-content');
        
        header.classList.add('active');
        header.setAttribute('aria-expanded', 'true');
        
        if (content) {
            // Ensure content is visible
            content.style.display = 'block';
            content.classList.add('active');
            content.setAttribute('aria-hidden', 'false');
            
            // Force a reflow to ensure the content is rendered
            content.offsetHeight;
            
            // Trigger the animation
            setTimeout(() => {
                content.style.visibility = 'visible';
                content.style.opacity = '1';
            }, 10);
            
            console.log('Activated accordion content:', content);
        } else {
            console.warn('No accordion content found for item:', accordionItem);
        }
        
        this.activeAccordionItems.set(accordionContainer, accordionItem);
        
        // Force show content after a short delay to ensure DOM is updated
        setTimeout(() => {
            this.forceShowAccordionContent(content);
        }, 50);
    }
    
    /**
     * Force show accordion content
     */
    forceShowAccordionContent(content) {
        if (!content) return;
        
        // Remove any conflicting styles
        content.style.display = 'block';
        content.style.visibility = 'visible';
        content.style.opacity = '1';
        content.style.height = 'auto';
        content.style.overflow = 'visible';
        
        // Add active class
        content.classList.add('active');
        content.setAttribute('aria-hidden', 'false');
        
        // Force a reflow
        content.offsetHeight;
        
        console.log('Forced show accordion content:', content);
    }
    
    /**
     * Deactivate accordion item
     */
    deactivateAccordionItem(accordionItem, header) {
        const content = accordionItem.querySelector('.tab-accordion-content');
        
        header.classList.remove('active');
        header.setAttribute('aria-expanded', 'false');
        
        if (content) {
            // Hide content with animation
            content.style.visibility = 'hidden';
            content.style.opacity = '0';
            
            setTimeout(() => {
                content.classList.remove('active');
                content.setAttribute('aria-hidden', 'true');
                content.style.display = 'none';
            }, 300);
            
            console.log('Deactivated accordion content:', content);
        }
    }
    
    /**
     * Close all accordion items
     */
    closeAllAccordionItems(accordionContainer) {
        const headers = accordionContainer.querySelectorAll('.tab-accordion-header');
        const contents = accordionContainer.querySelectorAll('.tab-accordion-content');
        
        headers.forEach(header => {
            header.classList.remove('active');
            header.setAttribute('aria-expanded', 'false');
        });
        
        contents.forEach(content => {
            // Hide content with animation
            content.style.visibility = 'hidden';
            content.style.opacity = '0';
            
            setTimeout(() => {
                content.classList.remove('active');
                content.setAttribute('aria-hidden', 'true');
                content.style.display = 'none';
            }, 300);
        });
    }
    
    /**
     * Sync content from desktop tab to accordion
     */
    syncContentToAccordion(tabTarget) {
        const desktopContent = document.querySelector(tabTarget);
        const accordionContent = document.querySelector(`${tabTarget}-accordion`);
        
        if (desktopContent && accordionContent) {
            // Always sync for mobile support, but don't overwrite if content looks populated
            const currentContent = accordionContent.innerHTML.trim();
            const needsContent = currentContent === '' || 
                                currentContent.includes('Content will be populated by JavaScript') ||
                                currentContent.length < 100; // Very minimal content
                                
            if (needsContent) {
                accordionContent.innerHTML = desktopContent.innerHTML;
                
                // Optimize for mobile display
                this.optimizeAccordionContentForMobile(accordionContent);
                
                // Re-trigger chart initialization if charts exist
                setTimeout(() => {
                    this.reinitializeChartsInContent(accordionContent);
                }, 500);
                
                // Also trigger a more aggressive chart reinitialization
                setTimeout(() => {
                    this.forceChartReinitialization(accordionContent);
                }, 1000);
                
                console.log(`Synced content from ${tabTarget} to accordion`);
            } else {
                console.log(`Skipped syncing ${tabTarget} - accordion already has substantial content`);
            }
        } else {
            console.warn(`Sync failed - Desktop: ${!!desktopContent}, Accordion: ${!!accordionContent} for ${tabTarget}`);
        }
    }
    
    /**
     * Sync content from accordion to desktop tab
     */
    syncContentFromAccordion(accordionTarget, desktopTabTarget) {
        // Disable reverse sync to prevent content overwriting
        console.log(`Skipping reverse sync from accordion to desktop to preserve unique content`);
        return;
        
        const accordionContent = document.querySelector(`#${accordionTarget.substring(1)}`);
        const desktopContent = document.querySelector(desktopTabTarget);
        
        if (accordionContent && desktopContent) {
            // Clone content from accordion to desktop
            desktopContent.innerHTML = accordionContent.innerHTML;
            console.log(`Synced content from accordion to ${desktopTabTarget}`);
        }
    }
    
    /**
     * Set initial state
     */
    setInitialState(container, desktopTabs, accordionContainer) {
        console.log('Setting initial state for container');
        
        // Find active desktop tab or use first one
        let activeTab = container.querySelector('.tab-btn.active, .tab-button.active');
        if (!activeTab && desktopTabs.length > 0) {
            activeTab = desktopTabs[0];
            console.log('No active tab found, using first tab:', activeTab.id);
        }
        
        if (activeTab) {
            // Don't call updateDesktopTabs during initialization to preserve content
            // Just ensure the active tab has proper styling
            activeTab.classList.add('active', 'border-blue-500', 'text-blue-600');
            activeTab.classList.remove('border-transparent', 'text-gray-500');
            
            const tabTarget = activeTab.getAttribute('data-tab-target');
            if (tabTarget) {
                // Make sure the active tab content is visible without overwriting
                const targetContent = document.querySelector(tabTarget);
                if (targetContent) {
                    targetContent.classList.add('active');
                    targetContent.classList.remove('hidden');
                    targetContent.style.display = 'block';
                    targetContent.style.visibility = 'visible';
                    targetContent.style.opacity = '1';
                }
                
                // Always sync to accordion for mobile support during initialization
                this.syncContentToAccordion(tabTarget);
                
                // Update accordion state
                this.updateAccordionFromDesktopTab(container, activeTab, tabTarget);
                
                console.log('Initial state set for tab:', tabTarget);
            }
        }
    }
    
    /**
     * Handle window resize
     */
    handleResize() {
        // Re-sync content when switching between desktop and mobile views
        // But only if accordion content is empty to preserve unique content
        this.containers.forEach(container => {
            const activeTab = container.querySelector('.tab-btn.active, .tab-button.active');
            if (activeTab) {
                const tabTarget = activeTab.getAttribute('data-tab-target');
                if (tabTarget) {
                    // Only sync if needed for mobile support
                    this.syncContentToAccordion(tabTarget);
                }
            }
        });
    }
    
    /**
     * Reinitialize for dynamically added content
     */
    reinitialize() {
        console.log('Reinitializing MobileTabsAccordion');
        this.containers = [];
        this.activeAccordionItems.clear();
        this.isInitialized = false;
        this.initialize();
    }
    
    /**
     * Add a new container manually
     */
    addContainer(container) {
        if (!this.containers.includes(container)) {
            this.containers.push(container);
            this.setupContainer(container);
            console.log('Added container manually:', container);
        }
    }
    
    /**
     * Public method to sync specific content
     */
    syncContent(tabTarget) {
        this.syncContentToAccordion(tabTarget);
    }
}

// Auto-initialize when DOM is ready (only if not already initialized)
document.addEventListener('DOMContentLoaded', function() {
    if (!window.mobileTabsAccordionInstance) {
        MobileTabsAccordion.init();
    }
});

// Also initialize on page load as fallback
window.addEventListener('load', function() {
    if (!window.mobileTabsAccordionInstance) {
        MobileTabsAccordion.init();
    }
});

// Global helper function for manual chart reinitialization
if (!window.fixMobileCharts) {
    window.fixMobileCharts = function() {
        if (window.mobileTabsAccordionInstance) {
            console.log('Manually fixing mobile charts...');
            window.mobileTabsAccordionInstance.checkAndFixMobileCharts();
            
            // Also try to force reinitialization for all accordion content
            const accordionContents = document.querySelectorAll('.tab-accordion-content');
            accordionContents.forEach((content, index) => {
                setTimeout(() => {
                    window.mobileTabsAccordionInstance.forceChartReinitialization(content);
                    console.log(`Force reinitialized charts in accordion ${index + 1}`);
                }, index * 200); // Stagger the reinitializations
            });
        } else {
            console.warn('MobileTabsAccordion instance not found');
        }
    };
}

// Expose globally
window.MobileTabsAccordion = MobileTabsAccordion;

// Expose common functions globally for backward compatibility (only if not already defined)
if (!window.initializeMobileAccordion) {
    window.initializeMobileAccordion = function() {
        return MobileTabsAccordion.init();
    };
}

if (!window.reinitializeMobileAccordion) {
    window.reinitializeMobileAccordion = function() {
        if (window.mobileTabsAccordionInstance) {
            window.mobileTabsAccordionInstance.reinitialize();
        } else {
            MobileTabsAccordion.init();
        }
    };
}

} else {
    console.log('MobileTabsAccordion already loaded, skipping duplicate declaration');
} // End of duplicate prevention check
