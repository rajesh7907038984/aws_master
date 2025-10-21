/**
 * Topic Handler for Course Edit Page
 * 
 * This script handles topics functionality for the course edit page.
 */

document.addEventListener('DOMContentLoaded', function() {
    
    // Elements
    const topicList = document.getElementById('topic-list');
    const addTopicBtn = document.getElementById('add-topic-btn');
    
    if (!topicList) {
        return;
    }
    
    // Initialize sortable for topics
    initSortable();
    
    // Add event listeners for topic buttons
    addTopicEventListeners();
    
    // Add topic button click handler
    if (addTopicBtn) {
        addTopicBtn.addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = addTopicBtn.getAttribute('href');
        });
    }
    
});

/**
 * Initialize sortable for topic list
 */
function initSortable() {
    const topicList = document.getElementById('topic-list');
    if (!topicList) return;
    
    if (typeof Sortable !== 'undefined') {
        Sortable.create(topicList, {
            animation: 150,
            handle: '.topic-drag-handle',
            onEnd: function(evt) {
                // Save the new order
                saveTopicOrder();
            }
        });
    } else {
    }
}

/**
 * Save the topic order
 */
function saveTopicOrder() {
    const topicList = document.getElementById('topic-list');
    if (!topicList) return;
    
    const topics = Array.from(topicList.children);
    const orderedTopics = topics.map((item, index) => {
        return {
            id: item.dataset.topicId,
            order: index + 1
        };
    });
    
    // Get CSRF token
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    
    // Send order to server
    fetch('/courses/api/topics/reorder/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ topics: orderedTopics })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            
            // Flash success notification if notification system exists
            if (typeof showNotification === 'function') {
                showNotification('Topic order updated successfully', 'success');
            }
        } else {
            
            // Flash error notification if notification system exists
            if (typeof showNotification === 'function') {
                showNotification('Error saving topic order', 'error');
            }
        }
    })
    .catch(error => {
        
        // Flash error notification if notification system exists
        if (typeof showNotification === 'function') {
            showNotification('Error saving topic order', 'error');
        }
    });
}

/**
 * Add event listeners to topic action buttons
 */
function addTopicEventListeners() {
    // Edit topic buttons
    document.querySelectorAll('.edit-topic-btn').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const topicId = this.dataset.topicId;
            window.location.href = `/courses/topic/${topicId}/edit/`;
        });
    });
    
    // Delete topic buttons
    document.querySelectorAll('.delete-topic-btn').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const topicId = this.dataset.topicId;
            const topicTitle = this.dataset.topicTitle;
            
            if (confirm(`Are you sure you want to delete the topic "${topicTitle}"?`)) {
                deleteTopic(topicId);
            }
        });
    });
    
    // View topic buttons
    document.querySelectorAll('.view-topic-btn').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const topicId = this.dataset.topicId;
            window.location.href = `/courses/topic/${topicId}/view/?manual=True`;
        });
    });
}

/**
 * Delete a topic
 */
function deleteTopic(topicId) {
    // Get CSRF token
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    
    fetch(`/courses/topic/${topicId}/delete/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        }
    })
    .then(response => {
        // Check content type before parsing JSON
        const contentType = response.headers.get('Content-Type');
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        } else {
            // Handle non-JSON responses as errors
            throw new Error('Invalid response format from server');
        }
    })
    .then(data => {
        if (data.success) {
            
            // Remove topic from DOM
            const topicElement = document.querySelector(`.topic-item[data-topic-id="${topicId}"]`);
            if (topicElement) {
                topicElement.remove();
            }
            
            // Flash success notification if notification system exists
            if (typeof showNotification === 'function') {
                showNotification('Topic deleted successfully', 'success');
            }
        } else {
            
            // Flash error notification if notification system exists
            if (typeof showNotification === 'function') {
                showNotification(`Error deleting topic: ${data.error}`, 'error');
            }
        }
    })
    .catch(error => {
        
        // Flash error notification if notification system exists
        if (typeof showNotification === 'function') {
            showNotification('Error deleting topic', 'error');
        }
    });
} 