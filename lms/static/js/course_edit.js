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
                                new_order: newIndex + 1
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
                            }
                        })
                        .catch(function(error) {
                            console.error('Error reordering topics:', error);
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