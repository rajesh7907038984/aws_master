// Helper function to get CSRF token
function getCookie(name) {
    var cookies = document.cookie.split(';');
    for (var cookie of cookies) {
        var [key, value] = cookie.trim().split('=');
        if (key === name) {
            return decodeURIComponent(value);
        }
    }
    return '';
}

// Helper function to show notifications
function showNotification(message, type) {
    // Create notification element
    var notification = document.createElement('div');
    notification.className = 'notification ' + type;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 4px;
        color: white;
        font-weight: 500;
        z-index: 10000;
        max-width: 300px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    `;
    
    // Set background color based on type
    if (type === 'error') {
        notification.style.backgroundColor = '#dc3545';
    } else if (type === 'success') {
        notification.style.backgroundColor = '#28a745';
    } else {
        notification.style.backgroundColor = '#007bff';
    }
    
    // Add to page
    document.body.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(function() {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 5000);
}

// Global function to handle modal close
function closeModal(modal) {
    if (modal) {
        modal.classList.remove('active');
        modal.classList.add('hidden');
        document.body.classList.remove('modal-open');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    try {
        // View toggle functionality
        var listViewBtn = document.getElementById('list-view-btn');
        var gridViewBtn = document.getElementById('grid-view-btn');
        var topicList = document.getElementById('topic-list');

        // Settings modal functionality
        var settingsModal = document.getElementById('settings-modal');
        var settingsButton = document.getElementById('settings-btn');
        var closeSettingsModal = document.getElementById('closeSettingsModal');
        var cancelSettingsBtn = document.getElementById('cancelSettingsBtn');
        var saveSettingsBtn = document.getElementById('save-settings-btn');

        // Handle settings button click
        if (settingsButton && settingsModal) {
            settingsButton.addEventListener('click', function(e) {
                try {
                    e.preventDefault();
                    settingsModal.classList.remove('hidden');
                    settingsModal.classList.add('active');
                    document.body.classList.add('modal-open');
                } catch (error) {
                    console.error('Error handling settings button click:', error);
                }
            });
        }


        // Initialize Sortable for drag-and-drop functionality
        if (topicList && typeof Sortable !== 'undefined') {
            new Sortable(topicList, {
                animation: 150,
                handle: '.topic-drag-handle',
                onEnd: function(evt) {
                    try {
                        var topicId = evt.item.getAttribute('data-topic-id');
                        var newIndex = evt.newIndex;
                        
                        // Update topic order in the database
                        fetch('/courses/api/topics/reorder/', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': getCookie('csrftoken')
                            },
                            body: JSON.stringify({
                                topic_id: topicId,
                                new_order: newIndex + 1  // Convert 0-based index to 1-based order
                            })
                        })
                        .then(function(response) {
                            if (!response.ok) {
                                throw new Error('HTTP error! status: ' + response.status);
                            }
                            return response.json();
                        })
                        .then(function(data) {
                            if (!data.success) {
                                console.warn('Topic reorder failed:', data);
                                // Show user-friendly error message
                                showNotification('Failed to reorder topics. Please try again.', 'error');
                            } else {
                                showNotification('Topics reordered successfully', 'success');
                            }
                        })
                        .catch(function(error) {
                            console.error('Error reordering topics:', error);
                            showNotification('Error reordering topics. Please refresh and try again.', 'error');
                        });
                    } catch (error) {
                        console.error('Error in sortable onEnd:', error);
                    }
                }
            });
        } else if (topicList) {
            console.warn('Sortable library not available');
        }

        // Close on escape key
        document.addEventListener('keydown', function(e) {
            try {
                if (e.key === 'Escape') {
                    if (settingsModal && settingsModal.classList.contains('active')) {
                        closeModal(settingsModal);
                    }
                }
            } catch (error) {
                console.error('Error handling escape key:', error);
            }
        });
    } catch (error) {
        console.error('Error initializing course edit:', error);
    }
}); 