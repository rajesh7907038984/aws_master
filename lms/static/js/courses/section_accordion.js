/**
 * Section Accordion Handler
 * 
 * This script handles the accordion functionality for course sections
 */

// Define global notification function for use across the file
function showNotification(message, type = 'info', duration = 3000) {
    const notification = document.createElement('div');
    notification.className = `fixed bottom-4 right-4 px-6 py-3 rounded shadow-lg z-50`;
    
    // Set colors based on type
    switch(type) {
        case 'success': 
            notification.classList.add('bg-green-500', 'text-white');
            break;
        case 'error': 
            notification.classList.add('bg-red-500', 'text-white');
            break;
        case 'warning': 
            notification.classList.add('bg-yellow-500', 'text-white');
            break;
        default: 
            notification.classList.add('bg-blue-500', 'text-white');
    }
    
    notification.innerHTML = message;
    document.body.appendChild(notification);
    
    // Store timeout ID for cleanup
    const timeoutId = setTimeout(() => {
        notification.classList.add('opacity-0', 'transition-opacity', 'duration-300');
        const removeTimeoutId = setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
        
        // Store remove timeout for cleanup
        notification._removeTimeoutId = removeTimeoutId;
    }, duration);
    
    // Store timeout ID for cleanup
    notification._timeoutId = timeoutId;
    
    // Add cleanup method
    notification.cleanup = function() {
        if (this._timeoutId) {
            clearTimeout(this._timeoutId);
        }
        if (this._removeTimeoutId) {
            clearTimeout(this._removeTimeoutId);
        }
        if (this.parentNode) {
            this.parentNode.removeChild(this);
        }
    };
    
    return notification;
}

// Standardized function to get CSRF token
function getCsrfToken() {
    // Try to get from cookie first
    let token = null;
    
    // Try to get CSRF token from cookie
    if (typeof getCookie === 'function') {
        token = getCookie('csrftoken');
    } else {
        // Fallback: implement getCookie locally
        const getCookieLocal = function(name) {
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        };
        token = getCookieLocal('csrftoken');
    }
    
    // If not found in cookie, try to get from DOM
    if (!token) {
        const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenElement) {
            token = tokenElement.value;
        }
    }
    
    return token;
}

// Polyfill for Element.closest() for older browsers
if (!Element.prototype.matches) {
    Element.prototype.matches = Element.prototype.msMatchesSelector || 
                              Element.prototype.webkitMatchesSelector;
}

if (!Element.prototype.closest) {
    Element.prototype.closest = function(s) {
        var el = this;
        do {
            if (el.matches(s)) return el;
            el = el.parentElement || el.parentNode;
        } while (el !== null && el.nodeType === 1);
        return null;
    };
}

// Initialize tracking for sortables
const initializedSortables = {
    sections: false,
    topics: new Set()
};

// Global event listener cleanup tracking with improved performance
window.LMSEventListeners = window.LMSEventListeners || {
    listeners: new Map(),
    add: function(element, event, handler, options) {
        if (!element || typeof element.addEventListener !== 'function') {
            console.warn('Invalid element provided to LMSEventListeners.add');
            return;
        }
        
        const key = `${element}_${event}_${Date.now()}`;
        if (this.listeners.has(key)) {
            this.remove(key);
        }
        
        // Use passive listeners for better performance where appropriate
        const optimizedOptions = {
            passive: event === 'scroll' || event === 'touchstart' || event === 'touchmove',
            ...options
        };
        
        element.addEventListener(event, handler, optimizedOptions);
        this.listeners.set(key, { element, event, handler, options: optimizedOptions });
    },
    remove: function(key) {
        if (this.listeners.has(key)) {
            const { element, event, handler, options } = this.listeners.get(key);
            if (element && typeof element.removeEventListener === 'function') {
                element.removeEventListener(event, handler, options);
            }
            this.listeners.delete(key);
        }
    },
    cleanup: function() {
        for (const [key, listener] of this.listeners) {
            const { element, event, handler, options } = listener;
            if (element && typeof element.removeEventListener === 'function') {
                element.removeEventListener(event, handler, options);
            }
        }
        this.listeners.clear();
    }
};

document.addEventListener('DOMContentLoaded', function() {
    
    // Set courseId in the sections container for API calls
    const urlMatch = window.location.pathname.match(/\/courses\/(\d+)/);
    const courseId = urlMatch && urlMatch[1] ? urlMatch[1] : null;
    
    if (courseId) {
        const sectionsContainer = document.getElementById('sections-container');
        if (sectionsContainer) {
            sectionsContainer.dataset.courseId = courseId;
        }
    }
    
    // Initialize section toggling
    initializeSectionAccordion();

    // Check if we're on the edit page (contains sections-container) or view page (doesn't need sortable)
    const isEditPage = document.getElementById('sections-container') !== null;
    
    // Only initialize sortable functionality on edit pages
    if (isEditPage && typeof Sortable !== 'undefined') {
        // Initialize drag-and-drop for sections and topics
        initializeSectionSortable();
        initializeTopicsSortable();
        
        // Add event listener for dynamically added sections
        document.addEventListener('section:added', function() {
            initializeSectionAccordion();
            initializeSectionSortable();
            initializeTopicsSortable();
        });
    } else {
        // View page only needs accordion functionality
    }
    
    // On page load, restore section collapsed state
    try {
        const collapsedSections = JSON.parse(localStorage.getItem('collapsedSections') || '[]');
        collapsedSections.forEach(sectionId => {
            const sectionItem = document.querySelector(`.section-item[data-id="${sectionId}"]`);
            if (sectionItem) {
                const topicsContainer = sectionItem.querySelector('.section-topics');
                const toggle = sectionItem.querySelector('.section-toggle');
                if (topicsContainer && toggle) {
                    topicsContainer.style.display = 'none';
                    toggle.classList.add('collapsed');
                }
            }
        });
    } catch (e) {
    }
});

/**
 * Initialize the accordion functionality for all sections
 */
function initializeSectionAccordion() {
    
    // Find all toggle buttons - handle different markup in course edit page vs topic view page
    const toggleButtons = document.querySelectorAll('.section-toggle');
    
    // Detect if we're on the topic view page or course edit page
    const isTopicViewPage = window.location.pathname.includes('/topic/') && window.location.pathname.includes('/view/');
    const isEditPage = document.getElementById('sections-container') !== null;
    
    
    // Handle specific page types
    if (isTopicViewPage) {
        // For topic view page, also add click handler to the section headers directly
        const sectionHeaders = document.querySelectorAll('.section-header');
        sectionHeaders.forEach(header => {
            header.removeEventListener('click', handleSectionHeaderClick);
            header.addEventListener('click', handleSectionHeaderClick);
        });
    }
    
    // Add click handlers to toggle buttons
    toggleButtons.forEach(toggle => {
        // Remove existing event listeners to prevent duplicates
        toggle.removeEventListener('click', handleToggleClick);
        
        // Add new event listener
        toggle.addEventListener('click', handleToggleClick);
    });
    
}

/**
 * Handle click on section header (for topic view page)
 * @param {Event} e - Click event
 */
function handleSectionHeaderClick(e) {
    // Don't handle if the click was on the toggle button (it will be handled separately)
    if (e.target.closest('.section-toggle')) {
        return;
    }
    
    const section = this.closest('.section');
    if (!section) return;
    
    // Get the toggle button and simulate a click on it
    const toggle = section.querySelector('.section-toggle');
    if (toggle) {
        toggle.click();
    } else {
        // No toggle button found, handle the toggling directly
        section.classList.toggle('active');
        const topicsContainer = section.querySelector('.section-topics');
        if (topicsContainer) {
            topicsContainer.style.display = section.classList.contains('active') ? 'block' : 'none';
        }
        
        // Store state in localStorage
        const sectionId = section.dataset.sectionId;
        if (sectionId) {
            const collapsedSections = JSON.parse(localStorage.getItem('collapsedSections') || '[]');
            if (!section.classList.contains('active')) {
                if (!collapsedSections.includes(sectionId)) {
                    collapsedSections.push(sectionId);
                }
            } else {
                const index = collapsedSections.indexOf(sectionId);
                if (index > -1) {
                    collapsedSections.splice(index, 1);
                }
            }
            localStorage.setItem('collapsedSections', JSON.stringify(collapsedSections));
        }
    }
}

/**
 * Handle click on toggle button
 * @param {Event} e - Click event
 */
function handleToggleClick(e) {
    e.stopPropagation();
    e.preventDefault();
    
    // Find container and topics section - handle both course edit and topic view page structures
    const container = this.closest('.section-container') || this.closest('.section');
    if (!container) {
        return;
    }
    
    const topicsContainer = container.querySelector('.section-topics');
    
    if (topicsContainer) {
        // Toggle visibility with animation
        if (topicsContainer.style.display === 'none') {
            // Show section
            topicsContainer.style.display = 'block';
            this.classList.remove('collapsed');
        } else {
            // Hide section
            topicsContainer.style.display = 'none';
            this.classList.add('collapsed');
        }
        
        // Store state in localStorage
        const sectionId = container.closest('.section-item')?.dataset?.id || 
                          container.dataset.id || 
                          container.dataset.sectionId; // Try all possible approaches
        
        if (sectionId) {
            const collapsedSections = JSON.parse(localStorage.getItem('collapsedSections') || '[]');
            if (topicsContainer.style.display === 'none') {
                if (!collapsedSections.includes(sectionId)) {
                    collapsedSections.push(sectionId);
                }
            } else {
                const index = collapsedSections.indexOf(sectionId);
                if (index > -1) {
                    collapsedSections.splice(index, 1);
                }
            }
            localStorage.setItem('collapsedSections', JSON.stringify(collapsedSections));
        }
    }
}

// Improved error detection for HTML responses
function isHtmlResponse(text) {
    return (
        text && 
        typeof text === 'string' && 
        (text.trim().startsWith('<!DOCTYPE') || 
         text.trim().startsWith('<html') ||
         text.trim().startsWith('<?xml'))
    );
}

/**
 * Standard fetch with timeout and better error handling
 */
function fetchWithTimeout(url, options, timeoutMs = 15000) {
    
    // Log the request body for more debugging info
    if (options.body) {
        try {
            const parsedBody = JSON.parse(options.body);
        } catch (e) {
        }
    }

    const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Request timed out')), timeoutMs)
    );
    
    return Promise.race([
        fetch(url, options)
            .then(response => {
                // Log response details for debugging (production: remove)
                if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
                    console.log('Response details:', {
                        status: response.status,
                        statusText: response.statusText,
                        headers: response.headers ? Object.fromEntries(response.headers.entries()) : {}
                    });
                }
                
                return response;
            })
            .catch(error => {
                throw error;
            }),
        timeoutPromise
    ]);
}

// Make fetchWithTimeout globally available
window.fetchWithTimeout = fetchWithTimeout;

// Enhanced fetch wrapper with better error handling
function robustFetch(url, options = {}) {
    return new Promise((resolve, reject) => {
        try {
            // Use fetchWithTimeout if available, otherwise use standard fetch
            const fetchFunction = typeof fetchWithTimeout === 'function' ? fetchWithTimeout : fetch;
            
            // Add default timeout if not specified
            if (!options.timeout && typeof fetchWithTimeout !== 'function') {
                options.timeout = 15000;
            }
            
            fetchFunction(url, options)
                .then(response => {
                    // Validate response object
                    if (!response || typeof response !== 'object') {
                        throw new Error('Invalid response object received from server');
                    }
                    
                    // Check if response has expected properties
                    if (typeof response.status === 'undefined') {
                        throw new Error('Response object missing status property - possible network or server issue');
                    }
                    
                    resolve(response);
                })
                .catch(error => {
                    reject(error);
                });
        } catch (error) {
            reject(error);
        }
    });
}

// Make robustFetch globally available
window.robustFetch = robustFetch;

// Enhanced parse JSON with HTML detection and better error handling
function safeParseJson(text) {
    try {
        // Validate input
        if (typeof text !== 'string') {
            return {
                success: false,
                error: 'Invalid input: expected string, got ' + typeof text
            };
        }
        
        // Check if the response is HTML
        if (isHtmlResponse(text)) {
            return {
                success: false,
                error: 'Server returned HTML instead of JSON. Possible server error.',
                isHtml: true
            };
        }
        
        // Check for empty response
        if (!text.trim()) {
            return {
                success: false,
                error: 'Empty response from server'
            };
        }
        
        // Try to parse as JSON
        const parsed = JSON.parse(text);
        
        // Validate parsed object structure
        if (typeof parsed !== 'object' || parsed === null) {
            return {
                success: false,
                error: 'Invalid JSON structure: expected object'
            };
        }
        
        return parsed;
    } catch (e) {
        return {
            success: false,
            error: 'Invalid JSON response: ' + (text ? text.substring(0, 100) + '...' : 'empty response'),
            parseError: e.message
        };
    }
}

/**
 * Initialize Sortable for the sections container
 */
function initializeSectionSortable() {
    const sectionsContainer = document.getElementById('sections-container');
    if (!sectionsContainer) return;
    
    
    try {
        // Destroy existing instance if it exists to prevent duplicates
        if (sectionsContainer.sortableInstance) {
            sectionsContainer.sortableInstance.destroy();
        }
        
        if (typeof Sortable !== 'undefined') {
            try {
                // Create Sortable instance for sections
                const sortableInstance = Sortable.create(sectionsContainer, {
                    animation: 150,
                    handle: '.drag-handle, .section-drag-handle',
                    ghostClass: 'bg-gray-100',
                    chosenClass: 'bg-blue-50',
                    dragClass: 'shadow-lg',
                    onStart: function(evt) {
                        document.body.classList.add('section-dragging-active');
                    },
                    onEnd: function(evt) {
                        document.body.classList.remove('section-dragging-active');
                        try {
                            saveSectionOrder();
                        } catch (error) {
                            console.error('Error saving section order:', error);
                            showNotification('Error saving section order. Please try again.', 'error');
                        }
                    },
                    onError: function(evt) {
                        console.error('Sortable error:', evt);
                        showNotification('Drag and drop error occurred. Please try again.', 'error');
                    }
                });
                
                // Store the instance on the DOM element for future reference
                sectionsContainer.sortableInstance = sortableInstance;
                
                initializedSortables.sections = true;
                // console.log('Section sortable initialized successfully'); // Production: remove
            } catch (error) {
                console.error('Error initializing section sortable:', error);
                showNotification('Failed to initialize drag and drop. Please refresh the page.', 'error');
            }
        } else {
            console.warn('Sortable library not available');
            showNotification('Drag and drop functionality not available. Please refresh the page.', 'warning');
        }
    } catch (error) {
    }
}

/**
 * Initialize drag-and-drop for topics within sections
 */
function initializeTopicsSortable() {
    // Check if Sortable library is available
    if (typeof Sortable === 'undefined') {
        return;
    }
    
    // Get all topic lists in all sections
    const topicLists = document.querySelectorAll('.topic-list');
    
    // For each topic list
    topicLists.forEach(list => {
        // Get section ID - try multiple ways to get the section ID
        const sectionItem = list.closest('.section-item');
        const sectionId = sectionItem ? (sectionItem.dataset.sectionId || sectionItem.dataset.id) : null;
        
        // Skip if we've already initialized this list or can't find section ID
        if (!sectionId) {
            return;
        }
        
        // Destroy existing instance if it exists (important for reinitializing)
        if (initializedSortables.topics.has(sectionId)) {
            try {
                if (list.sortableInstance) {
                    list.sortableInstance.destroy();
                }
            } catch (err) {
            }
        }
        
        // Initialize Sortable for this list
        try {
            // console.log(`Initializing sortable for section ${sectionId}`); // Production: remove
            
            const sortableInstance = new Sortable(list, {
                animation: 150,
                group: 'shared-topics-group', // Use a shared group name for all lists
                handle: '.drag-handle, .topic-drag-handle', // Support both handle classes
                draggable: '.topic-item',
                ghostClass: 'sortable-ghost',
                chosenClass: 'sortable-chosen',
                dragClass: 'sortable-drag',
                forceFallback: false, // Set to false for better performance, only use true if needed for mobile
                fallbackClass: 'sortable-fallback',
                fallbackOnBody: true,
                fallbackTolerance: 3, // Reduced for better responsiveness
                scroll: true,
                scrollSensitivity: 80,
                scrollSpeed: 10,
                delay: 100, // Slightly reduced delay for more responsive dragging
                delayOnTouchOnly: true, // Only apply delay for touch devices
                onStart: function(evt) {
                    // Try different ways to get the topic ID
                    const topicId = evt.item.dataset.topicId || evt.item.dataset.id || evt.item.id.replace('topic-', '');
                    document.body.classList.add('topic-dragging-active');
                    
                    // Mark the item being dragged with a special class
                    evt.item.classList.add('is-dragging');
                    
                    // Add an attribute to all section topics containers for targeting in CSS
                    document.querySelectorAll('.section-topics').forEach(container => {
                        container.setAttribute('data-drag-active', 'true');
                    });
                },
                onEnd: function(evt) {
                    document.body.classList.remove('topic-dragging-active');
                    
                    // Remove the dragging class
                    evt.item.classList.remove('is-dragging');
                    
                    // Remove the attribute from section topics containers
                    document.querySelectorAll('.section-topics').forEach(container => {
                        container.removeAttribute('data-drag-active');
                    });
                    
                    // Get the source section ID, trying multiple ways to get it
                    const fromSectionItem = evt.from.closest('.section-item');
                    const fromSectionId = fromSectionItem ? (fromSectionItem.dataset.sectionId || fromSectionItem.dataset.id) : null;
                    
                    // Get the target section ID, trying multiple ways to get it
                    const toSectionItem = evt.to.closest('.section-item');
                    const toSectionId = toSectionItem ? (toSectionItem.dataset.sectionId || toSectionItem.dataset.id) : null;
                    
                    
                    try {
                        if (fromSectionId === toSectionId) {
                            // Same section, just reordering
                            // console.log(`Reordering topics within section ${fromSectionId}`); // Production: remove
                            saveTopicOrder(fromSectionId);
                        } else {
                            // Moving to different section
                            if (toSectionId) {
                                // Get moved topic ID - try all possible data attributes
                                const topicId = evt.item.dataset.topicId || evt.item.dataset.id || evt.item.id.replace('topic-', '');
                                
                                if (!topicId) {
                                    console.error('Could not identify topic being moved:', evt.item);
                                    showNotification('Error: Could not identify the topic being moved', 'error');
                                    return;
                                }
                                
                                // Get new position
                                const newOrder = Array.from(evt.to.children).indexOf(evt.item) + 1; // Add 1 for 1-based indexing
                                
                                // console.log(`Moving topic ${topicId} from section ${fromSectionId} to section ${toSectionId} at position ${newOrder}`); // Production: remove
                                
                                // Add visual indicator that the move is being processed
                                evt.item.classList.add('topic-processing');
                                
                                // Update the data-section-id attribute on the topic element
                                evt.item.dataset.sectionId = toSectionId;
                                
                                // Save the move
                                saveTopicMove(topicId, toSectionId, newOrder - 1) // Subtract 1 because saveTopicMove adds 1
                                    .then(() => {
                                        // On success, replace processing with moved class
                                        evt.item.classList.remove('topic-processing');
                                        evt.item.classList.add('topic-moved');
                                        
                                        // Remove the class after animation completes
                                        setTimeout(() => {
                                            evt.item.classList.remove('topic-moved');
                                        }, 1500);
                                    })
                                    .catch(error => {
                                        console.error('Error saving topic move:', error);
                                        evt.item.classList.remove('topic-processing');
                                        
                                        // Add error indicator
                                        evt.item.classList.add('topic-error');
                                        setTimeout(() => {
                                            evt.item.classList.remove('topic-error');
                                            
                                            // Refresh the page to restore to a consistent state
                                            window.location.reload();
                                        }, 1500);
                                    });
                            } else {
                                console.error('No target section ID found');
                                showNotification('Error: Could not determine target section', 'error');
                            }
                        }
                    } catch (error) {
                        console.error('Error processing drag and drop operation:', error);
                        showNotification('Error processing drag and drop operation', 'error');
                        
                        // Refresh the page to restore to a consistent state
                        setTimeout(() => {
                            window.location.reload();
                        }, 1500);
                    }
                }
            });
            
            // Store the instance on the DOM element for future reference
            list.sortableInstance = sortableInstance;
            
            // Mark as initialized
            initializedSortables.topics.add(sectionId);
        } catch (e) {
        }
    });
}

/**
 * Save the order of sections
 */
function saveSectionOrder() {
    // Get sections container
    const sectionsContainer = document.getElementById('sections-container');
    if (!sectionsContainer) {
        showNotification('Error: Sections container not found', 'error');
        return;
    }
    
    // Get course ID
    const courseId = sectionsContainer.dataset.courseId;
    if (!courseId) {
        showNotification('Error: Course ID not found', 'error');
        return;
    }
    
    // Get all sections
    const sections = Array.from(sectionsContainer.querySelectorAll('.section-item'));
    
    // Create array of section IDs with their new order
    const sectionOrders = sections.map((section, index) => {
        return {
            section_id: parseInt(section.dataset.id),
            order: index + 1
        };
    });
    
    // Get CSRF token
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        showNotification('Error: CSRF token not found', 'error');
        return;
    }
    
    // Show loading indicator
    const loadingIndicator = document.createElement('div');
    loadingIndicator.className = 'fixed top-0 left-0 right-0 bg-blue-500 text-white text-center py-2 z-50';
    loadingIndicator.id = 'section-order-loading';
    loadingIndicator.innerHTML = 'Saving section order...';
    document.body.appendChild(loadingIndicator);
    
    // Send to server with timeout
    fetchWithTimeout('/courses/api/sections/reorder/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({
            course_id: parseInt(courseId),
            section_orders: sectionOrders
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                if (isHtmlResponse(text)) {
                    throw new Error('Server returned an HTML page instead of JSON (status ' + response.status + ')');
                }
                
                try {
                    const data = JSON.parse(text);
                    throw new Error(data.error || `Server responded with ${response.status}: ${response.statusText}`);
                } catch (e) {
                    if (e.message.includes('JSON')) {
                        throw new Error(`Server responded with ${response.status}: ${response.statusText}`);
                    } else {
                        throw e;
                    }
                }
            });
        }
        
        return response.text().then(text => {
            const result = safeParseJson(text);
            if (!result.success && result.error && result.error.includes('HTML')) {
                throw new Error('Server returned HTML instead of JSON. Please try again.');
            }
            return result;
        });
    })
    .then(data => {
        // Remove loading indicator
        removeLoadingIndicator();
        
        if (data.success) {
            showNotification('Section order updated successfully', 'success');
        } else {
            throw new Error(data.error || 'Failed to update section order');
        }
    })
    .catch(error => {
        // Remove loading indicator if it still exists
        removeLoadingIndicator();
        
        // Show error notification
        showNotification(`Error saving section order: ${error.message}`, 'error');
        
        // Reload the page if sections are likely out of sync with server
        if (error.message.includes('404') || error.message.includes('500')) {
            showNotification('Reloading page to restore section order...', 'warning');
            setTimeout(() => window.location.reload(), 2000);
        }
    });
    
    // Helper function to remove loading indicator
    function removeLoadingIndicator() {
        const indicator = document.getElementById('section-order-loading');
        if (indicator && indicator.parentNode) {
            indicator.parentNode.removeChild(indicator);
        }
    }
}

/**
 * Helper function to get the course ID
 */
function getElementCourseId() {
    // Try several methods to get the course ID
    try {
        // 1. From sections container
        const sectionsContainer = document.getElementById('sections-container');
        if (sectionsContainer && sectionsContainer.dataset.courseId) {
            return parseInt(sectionsContainer.dataset.courseId);
        }
        
        // 2. From URL
        const urlMatch = window.location.pathname.match(/\/courses\/(\d+)/);
        if (urlMatch && urlMatch[1]) {
            return parseInt(urlMatch[1]);
        }
        
        // 3. From a hidden input
        const courseIdInput = document.querySelector('input[name="course_id"]');
        if (courseIdInput && courseIdInput.value) {
            return parseInt(courseIdInput.value);
        }
        
        // 4. From form action URL
        const form = document.querySelector('form[action*="/courses/"]');
        if (form) {
            const formUrlMatch = form.action.match(/\/courses\/(\d+)/);
            if (formUrlMatch && formUrlMatch[1]) {
                return parseInt(formUrlMatch[1]);
            }
        }
        
        // Last resort: Get from the HTML as a data attribute
        const courseElement = document.querySelector('[data-course-id]');
        if (courseElement && courseElement.dataset.courseId) {
            return parseInt(courseElement.dataset.courseId);
        }
        
        // No course ID found
        return null;
    } catch (e) {
        return null;
    }
}

/**
 * Save the order of topics within a section
 * @param {number|null} sectionId - ID of the section, or null for standalone topics
 */
function saveTopicOrder(sectionId) {
    try {
        // Get topic list container for this section
        let topicList;
        if (sectionId === null || sectionId === 'null' || sectionId === 'standalone') {
            topicList = document.querySelector('.topic-list[data-section-id="standalone"]');
            if (!topicList) {
                topicList = document.querySelector('.topic-list[data-section-id="null"]');
            }
            sectionId = null; // Normalize to null for API
        } else {
            topicList = document.querySelector(`.topic-list[data-section-id="${sectionId}"]`);
        }
        
        if (!topicList) {
            showNotification('Error: Topic list not found', 'error');
            return;
        }
        
        // Get course ID from URL or sections container
        const courseId = getElementCourseId();
        if (!courseId) {
            showNotification('Error: Course ID not found', 'error');
            return;
        }
        
        // Get all topic items in this section
        const topicItems = Array.from(topicList.querySelectorAll('.topic-item'));
        if (!topicItems.length) {
            return; // No topics to reorder
        }
        
        // Create array of topic IDs with their new order
        const topicOrders = topicItems.map((item, index) => {
            const topicId = item.dataset.topicId;
            if (!topicId) {
                return null;
            }
            return {
                topic_id: parseInt(topicId, 10),
                order: index + 1,
                section_id: sectionId
            };
        }).filter(Boolean); // Remove null entries
        
        if (!topicOrders.length) {
            showNotification('Error: No valid topics to reorder', 'error');
            return;
        }
        
        // Get CSRF token
        const csrfToken = getCsrfToken();
        if (!csrfToken) {
            showNotification('Error: CSRF token not found', 'error');
            return;
        }
        
        // Show loading indicator
        const loadingId = 'topic-order-loading-' + (sectionId || 'standalone');
        const loadingIndicator = document.createElement('div');
        loadingIndicator.className = 'fixed top-0 left-0 right-0 bg-blue-500 text-white text-center py-2 z-50';
        loadingIndicator.id = loadingId;
        loadingIndicator.innerHTML = 'Saving topic order...';
        document.body.appendChild(loadingIndicator);
        
        // Debug logs (production: remove)
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            console.log('Saving topic order:', {
                course_id: courseId,
                section_id: sectionId,
                topic_orders: topicOrders
            });
        }
        
        // Send update to server
        fetchWithTimeout('/courses/api/topics/reorder/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
                course_id: courseId,
                section_id: sectionId === 'standalone' ? null : sectionId,
                topic_orders: topicOrders
            })
        }, 15000)
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => {
                    if (isHtmlResponse(text)) {
                        throw new Error('Server returned an HTML page instead of JSON (status ' + response.status + ')');
                    }
                    
                    // Try to parse response as JSON to get error details
                    try {
                        const data = JSON.parse(text);
                        throw new Error(data.error || `Server responded with ${response.status}: ${response.statusText}`);
                    } catch (e) {
                        // If parsing fails, use the text or status
                        if (e.message.includes('JSON')) {
                            throw new Error(`Server responded with ${response.status}: ${response.statusText}`);
                        } else {
                            throw e; // Re-throw if it's our custom error
                        }
                    }
                });
            }
            
            // Not using response.json() directly to catch HTML disguised as JSON
            return response.text().then(text => {
                // Use our safe JSON parser
                const result = safeParseJson(text);
                
                // Handle parsing errors
                if (!result.success && result.error && result.error.includes('HTML')) {
                    throw new Error('Server returned HTML instead of JSON. Please try again.');
                }
                
                return result;
            });
        })
        .then(data => {
            // Remove loading indicator
            removeLoadingIndicator();
            
            if (data && data.success) {
                showNotification('Topic order updated successfully', 'success');
            } else {
                throw new Error((data && data.error) || 'Failed to update topic order');
            }
        })
        .catch(error => {
            // Remove loading indicator
            removeLoadingIndicator();
            
            showNotification('Error updating topic order: ' + error.message, 'error');
            
            // Refresh the page after a delay to ensure consistent state
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        });
        
        // Helper function to remove loading indicator
        function removeLoadingIndicator() {
            const indicator = document.getElementById(loadingId);
            if (indicator) {
                indicator.remove();
            }
        }
    } catch (e) {
        showNotification('Unexpected error: ' + e.message, 'error');
    }
}

/**
 * Move a topic to a different section and update its order
 * @param {string|number} topicId - ID of the topic to move
 * @param {string|number} sectionId - New section ID, can be null for standalone topics
 * @param {number} newOrder - New order position
 * @returns {Promise} - Promise that resolves when the move is complete
 */
function saveTopicMove(topicId, sectionId, newOrder) {
    return new Promise((resolve, reject) => {
        try {
            if (!topicId) {
                const error = 'No topic ID provided to saveTopicMove';
                showNotification('Error: No topic ID provided', 'error');
                return reject(new Error(error));
            }
            
            
            // Ensure sectionId is properly formatted - null or number
            let formattedSectionId = sectionId;
            if (sectionId === 'null' || sectionId === 'standalone' || !sectionId) {
                formattedSectionId = null;
            } else if (!isNaN(parseInt(sectionId))) {
                formattedSectionId = parseInt(sectionId, 10);
            }
            
            // Add loading indicator
            const loadingIndicator = document.createElement('div');
            loadingIndicator.className = 'fixed inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50';
            loadingIndicator.id = 'topic-move-loading';
            loadingIndicator.innerHTML = `
                <div class="bg-white p-4 rounded-lg shadow-lg">
                    <div class="flex items-center space-x-3">
                        <svg class="animate-spin h-5 w-5 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span>Moving topic to new section...</span>
                    </div>
                </div>
            `;
            document.body.appendChild(loadingIndicator);
            
            // Get course ID
            const courseId = getElementCourseId();
            if (!courseId) {
                removeLoadingIndicator();
                const error = 'Could not determine course ID';
                showNotification('Error: ' + error, 'error');
                return reject(new Error(error));
            }
            
            // Get CSRF token
            const csrfToken = getCsrfToken();
            if (!csrfToken) {
                removeLoadingIndicator();
                const error = 'CSRF token not found';
                showNotification('Error: ' + error, 'error');
                return reject(new Error(error));
            }
            
            // Debug log the data being sent (production: remove)
            if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
                console.log('Moving topic:', {
                    topic_id: parseInt(topicId, 10),
                    section_id: formattedSectionId,
                    new_order: newOrder + 1,
                    course_id: courseId
                });
            }
            
            // Make API request
            fetchWithTimeout(`/courses/api/topics/move/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    topic_id: parseInt(topicId, 10),
                    section_id: formattedSectionId,
                    new_order: newOrder + 1,  // 1-indexed for backend
                    course_id: courseId
                })
            }, 30000)
            .then(response => {
                if (!response.ok) {
                    return response.text().then(text => {
                        if (isHtmlResponse(text)) {
                            throw new Error('Server returned an HTML page instead of JSON (status ' + response.status + ')');
                        }
                        
                        // Try to parse response as JSON to get error details
                        try {
                            const data = JSON.parse(text);
                            throw new Error(data.error || `Server responded with status ${response.status}`);
                        } catch (e) {
                            // If parsing fails, use the text or status
                            if (e.message.includes('JSON')) {
                                throw new Error(`Server responded with status ${response.status}`);
                            } else {
                                throw e; // Re-throw if it's our custom error
                            }
                        }
                    });
                }
                
                // Not using response.json() directly to catch HTML disguised as JSON
                return response.text().then(text => {
                    // Use our safe JSON parser
                    const result = safeParseJson(text);
                    
                    // Handle parsing errors
                    if (!result.success && result.error && result.error.includes('HTML')) {
                        throw new Error('Server returned HTML instead of JSON. Please try again.');
                    }
                    
                    return result;
                });
            })
            .then(data => {
                if (data.success) {
                    // Show success notification
                    showNotification('Topic moved successfully', 'success');
                    
                    // Update any UI state if needed
                    
                    // Resolve the promise
                    resolve(data);
                    
                    // Refresh the page to reflect the changes accurately if needed
                    // This is optional now that we handle the UI updates in the caller
                    /* 
                    setTimeout(() => {
                        window.location.reload();
                    }, 500);
                    */
                } else {
                    throw new Error(data.error || 'Unknown error');
                }
            })
            .catch(error => {
                // Show error notification
                showNotification(`Error moving topic: ${error.message}`, 'error');
                
                // Reject the promise
                reject(error);
                
                // Refresh the page to restore consistent state
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            })
            .finally(() => {
                // Remove loading indicator
                removeLoadingIndicator();
            });
            
            function removeLoadingIndicator() {
                const indicator = document.querySelector('.fixed.inset-0.bg-black.bg-opacity-30');
                if (indicator) {
                    indicator.remove();
                }
            }
        } catch (e) {
            showNotification('Unexpected error: ' + e.message, 'error');
            
            // Remove loading indicator if it exists
            const indicator = document.querySelector('.fixed.inset-0.bg-black.bg-opacity-30');
            if (indicator) {
                indicator.remove();
            }
            
            // Reject the promise
            reject(e);
        }
    });
}

/**
 * Delete a section
 * @param {number} sectionId - ID of the section to delete
 */
function deleteSection(sectionId) {
    if (!confirm('Are you sure you want to delete this section? All topics will be moved to unsectioned.')) {
        return;
    }
    
    // Get CSRF token
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        showNotification('Error: CSRF token not found', 'error');
        return;
    }
    
    // Show loading indicator
    const loadingId = 'section-delete-loading-' + sectionId;
    const loadingIndicator = document.createElement('div');
    loadingIndicator.className = 'fixed top-0 left-0 right-0 bg-red-500 text-white text-center py-2 z-50';
    loadingIndicator.id = loadingId;
    loadingIndicator.innerHTML = 'Deleting section...';
    document.body.appendChild(loadingIndicator);
    
    // Send DELETE request to server
    fetchWithTimeout(`/courses/api/sections/${sectionId}/delete/`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': csrfToken,
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                if (isHtmlResponse(text)) {
                    throw new Error('Server returned an HTML page instead of JSON (status ' + response.status + ')');
                }
                
                try {
                    const data = JSON.parse(text);
                    throw new Error(data.error || `Server responded with ${response.status}: ${response.statusText}`);
                } catch (e) {
                    if (e.message.includes('JSON')) {
                        throw new Error(`Server responded with ${response.status}: ${response.statusText}`);
                    } else {
                        throw e;
                    }
                }
            });
        }
        
        return response.text().then(text => {
            const result = safeParseJson(text);
            if (!result.success && result.error && result.error.includes('HTML')) {
                throw new Error('Server returned HTML instead of JSON. Please try again.');
            }
            return result;
        });
    })
    .then(data => {
        // Remove loading indicator
        const indicator = document.getElementById(loadingId);
        if (indicator) indicator.remove();
        
        if (data.success) {
            // Remove section from UI
            const sectionElement = document.querySelector(`.section-item[data-id="${sectionId}"]`);
            if (sectionElement) {
                sectionElement.remove();
                showNotification('Section deleted successfully', 'success');
            } else {
                showNotification('Section deleted, but UI needs to be refreshed', 'warning');
                setTimeout(() => window.location.reload(), 1000);
            }
        } else {
            throw new Error(data.error || 'Failed to delete section');
        }
    })
    .catch(error => {
        // Remove loading indicator
        const indicator = document.getElementById(loadingId);
        if (indicator) indicator.remove();
        
        showNotification('Error deleting section: ' + error.message, 'error');
    });
}

/**
 * Rename a section
 * @param {number} sectionId - ID of the section to rename
 * @param {string} currentName - Current name of the section
 */
function renameSection(sectionId, currentName) {
    const newName = prompt('Enter new section name:', currentName);
    
    if (!newName || newName.trim() === '' || newName.trim() === currentName) {
        return; // User cancelled or no change
    }
    
    // Get CSRF token
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        showNotification('Error: CSRF token not found', 'error');
        return;
    }
    
    // Show loading indicator
    const loadingId = 'section-rename-loading-' + sectionId;
    const loadingIndicator = document.createElement('div');
    loadingIndicator.className = 'fixed top-0 left-0 right-0 bg-blue-500 text-white text-center py-2 z-50';
    loadingIndicator.id = loadingId;
    loadingIndicator.innerHTML = 'Renaming section...';
    document.body.appendChild(loadingIndicator);
    
    // Send POST request to server
    fetchWithTimeout(`/courses/api/sections/${sectionId}/rename/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: newName.trim() })
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                if (isHtmlResponse(text)) {
                    throw new Error('Server returned an HTML page instead of JSON (status ' + response.status + ')');
                }
                
                try {
                    const data = JSON.parse(text);
                    throw new Error(data.error || `Server responded with ${response.status}: ${response.statusText}`);
                } catch (e) {
                    if (e.message.includes('JSON')) {
                        throw new Error(`Server responded with ${response.status}: ${response.statusText}`);
                    } else {
                        throw e;
                    }
                }
            });
        }
        
        return response.text().then(text => {
            const result = safeParseJson(text);
            if (!result.success && result.error && result.error.includes('HTML')) {
                throw new Error('Server returned HTML instead of JSON. Please try again.');
            }
            return result;
        });
    })
    .then(data => {
        // Remove loading indicator
        const indicator = document.getElementById(loadingId);
        if (indicator) indicator.remove();
        
        if (data.success) {
            // Update the section name in the DOM
            const nameElement = document.querySelector(`[data-section-id="${sectionId}"].section-name`);
            if (nameElement) {
                nameElement.textContent = data.name;
                nameElement.title = data.name;
                showNotification('Section renamed successfully', 'success');
            } else {
                showNotification('Section renamed, but UI needs to be refreshed', 'warning');
                setTimeout(() => window.location.reload(), 1000);
            }
        } else {
            throw new Error(data.error || 'Failed to rename section');
        }
    })
    .catch(error => {
        // Remove loading indicator
        const indicator = document.getElementById(loadingId);
        if (indicator) indicator.remove();
        
        showNotification('Error renaming section: ' + error.message, 'error');
    });
}

// Make functions available globally
window.initializeSectionAccordion = initializeSectionAccordion;
window.handleToggleClick = handleToggleClick;
window.handleSectionHeaderClick = handleSectionHeaderClick;
window.deleteSection = deleteSection;
window.renameSection = renameSection;
window.renameSectionGlobal = renameSection; // Provide both names for compatibility

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (window.LMSEventListeners) {
        window.LMSEventListeners.cleanup();
    }
    
    // Cleanup any active notifications
    const notifications = document.querySelectorAll('.fixed.bottom-4.right-4');
    notifications.forEach(notification => {
        if (notification.cleanup) {
            notification.cleanup();
        }
    });
});