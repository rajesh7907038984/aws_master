// Course Edit JavaScript - Fixed version
// Handles course editing functionality with proper error handling

// Helper function to get CSRF token
function getCookie(name) {
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        var eqPos = cookie.indexOf('=');
        var cookieName = eqPos > -1 ? cookie.substring(0, eqPos) : cookie;
        var value = eqPos > -1 ? cookie.substring(eqPos + 1) : '';
        if (cookieName === name) {
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

// Form change detection
var formChanged = false;
var originalFormData = {};

// Initialize form change tracking
function initializeFormChangeTracking() {
    var form = document.getElementById('course-form');
    if (!form) return;
    
    // Store original form data
            var formData = new FormData(form);
    for (var pair of formData.entries()) {
        originalFormData[pair[0]] = pair[1];
    }
    
    // Add event listeners to all form elements
    var elements = form.querySelectorAll('input, textarea, select');
    elements.forEach(function(element) {
        element.addEventListener('change', function() {
            updateFormChangedState();
        });
        
        // For text inputs and textareas, also listen for input events
        if ((element.tagName === 'INPUT' && (element.type === 'text' || element.type === 'number' || element.type === 'email' || element.type === 'hidden')) || 
            element.tagName === 'TEXTAREA') {
            element.addEventListener('input', function() {
                if (element.name === 'description' || element.id === 'id_description') {
                    // Description field specific handling
                }
                updateFormChangedState();
            });
            
            // Additional specific handler for description field
            if (element.name === 'description' || element.id === 'id_description') {
                element.addEventListener('keyup', function() {
                    updateFormChangedState();
                });
            }
        }
        
        // For select elements, ensure we catch all changes
        if (element.tagName === 'SELECT') {
            element.addEventListener('input', function() {
                updateFormChangedState();
            });
        }
    });
    
    // Additional specific detection for description field by multiple selectors
    var descriptionSelectors = [
        'textarea[name="description"]',
        '#id_description',
        'textarea[data-field="description"]'
    ];
    
    descriptionSelectors.forEach(function(selector) {
        var element = document.querySelector(selector);
        if (element) {
        element.addEventListener('input', function() {
                    updateFormChangedState();
            });
            element.addEventListener('keyup', function() {
                    updateFormChangedState();
            });
        }
    });
}

// Update form changed state
function updateFormChangedState() {
    var form = document.getElementById('course-form');
    if (!form) return;
    
    var currentData = {};
    var formData = new FormData(form);
    for (var pair of formData.entries()) {
        currentData[pair[0]] = pair[1];
    }
    
    // Compare with original data
    var hasChanged = false;
    for (var key in currentData) {
        if (originalFormData[key] !== currentData[key]) {
            hasChanged = true;
            break;
        }
    }
    
    // Check for new keys
    for (var key in originalFormData) {
        if (!(key in currentData)) {
            hasChanged = true;
            break;
        }
    }
    
    formChanged = hasChanged;
    
    // Update save button state
    var saveButton = document.getElementById('save-course-btn');
    if (saveButton) {
        if (hasChanged) {
            saveButton.classList.remove('opacity-50', 'cursor-not-allowed');
            saveButton.classList.add('opacity-100', 'cursor-pointer');
            saveButton.disabled = false;
        } else {
            saveButton.classList.add('opacity-50', 'cursor-not-allowed');
            saveButton.classList.remove('opacity-100', 'cursor-pointer');
            saveButton.disabled = true;
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    try {
        // Initialize form change tracking
        initializeFormChangeTracking();
        
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

        // Handle close settings modal
        if (closeSettingsModal && settingsModal) {
            closeSettingsModal.addEventListener('click', function(e) {
                try {
            e.preventDefault();
                    closeModal(settingsModal);
                } catch (error) {
                    console.error('Error closing settings modal:', error);
                }
            });
        }

        // Handle cancel settings
        if (cancelSettingsBtn && settingsModal) {
            cancelSettingsBtn.addEventListener('click', function(e) {
                try {
                    e.preventDefault();
                    closeModal(settingsModal);
                } catch (error) {
                    console.error('Error canceling settings:', error);
                }
            });
        }

        // Handle save settings
        if (saveSettingsBtn) {
            saveSettingsBtn.addEventListener('click', function(e) {
                try {
                    e.preventDefault();
                    // Add settings save logic here
                    closeModal(settingsModal);
                } catch (error) {
                    console.error('Error saving settings:', error);
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

        // Handle form submission
        var courseForm = document.getElementById('course-form');
        if (courseForm) {
            courseForm.addEventListener('submit', function(e) {
                try {
                    // Reset form changed state on submit
                    formChanged = false;
                    updateFormChangedState();
                } catch (error) {
                    console.error('Error handling form submission:', error);
                }
            });
        }

        // Handle beforeunload to warn about unsaved changes
        window.addEventListener('beforeunload', function(e) {
            if (formChanged) {
                e.preventDefault();
                e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
                return 'You have unsaved changes. Are you sure you want to leave?';
            }
        });

    } catch (error) {
        console.error('Error initializing course edit:', error);
    }
});

// Export functions for global access
window.closeModal = closeModal;
window.updateFormChangedState = updateFormChangedState;