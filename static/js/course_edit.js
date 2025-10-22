// Helper function to get CSRF token
function getCookie(name) {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [key, value] = cookie.trim().split('=');
        if (key === name) {
            return decodeURIComponent(value);
        }
    }
    return '';
}

document.addEventListener('DOMContentLoaded', function() {
    // View toggle functionality
    const listViewBtn = document.getElementById('list-view-btn');
    const gridViewBtn = document.getElementById('grid-view-btn');
    const topicList = document.getElementById('topic-list');

    // Settings modal functionality
    const settingsModal = document.getElementById('settings-modal');
    const settingsButton = document.getElementById('settings-btn');
    const closeSettingsModal = document.getElementById('closeSettingsModal');
    const cancelSettingsBtn = document.getElementById('cancelSettingsBtn');
    const saveSettingsBtn = document.getElementById('save-settings-btn');

    // Handle settings button click
    if (settingsButton && settingsModal) {
        settingsButton.addEventListener('click', function(e) {
            e.preventDefault();
            settingsModal.classList.remove('hidden');
            settingsModal.classList.add('active');
            document.body.classList.add('modal-open');
        });
    }

    // Handle modal close
    function closeModal(modal) {
        if (modal) {
            modal.classList.remove('active');
            modal.classList.add('hidden');
            document.body.classList.remove('modal-open');
        }
    }

    // Initialize Sortable for drag-and-drop functionality
    if (topicList && typeof Sortable !== 'undefined') {
        new Sortable(topicList, {
            animation: 150,
            handle: '.topic-drag-handle',
            onEnd: function(evt) {
                const topicId = evt.item.getAttribute('data-topic-id');
                const newIndex = evt.newIndex;
                
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
                .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
                .then(data => {
                    if (!data.success) {
                        console.error('Failed to update topic order');
                    }
                })
                .catch(error => {
                    console.error('Error updating topic order:', error);
                });
            }
        });
    } else if (topicList) {
        console.warn('Sortable library not loaded - drag-and-drop functionality disabled');
    }

    // Close on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (settingsModal && settingsModal.classList.contains('active')) {
                closeModal(settingsModal);
            }
        }
    });
}); 