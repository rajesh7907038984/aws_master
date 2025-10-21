document.addEventListener('DOMContentLoaded', function() {
    
    // Tab functionality
    var tabButtons = document.querySelectorAll('.tab-btn');
    var tabContents = document.querySelectorAll('.tab-content');
    
    
    // Initialize tab functionality
    function initTabs() {
        tabButtons.forEach(function(button) {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                
                // Remove active class from all buttons and contents
                tabButtons.forEach(function(btn) {
                    btn.classList.remove('active');
                    btn.classList.remove('border-blue-600');
                    btn.classList.add('text-gray-500');
                });
                
                tabContents.forEach(function(content) {
                    content.classList.remove('active');
                });
                
                // Add active class to clicked button
                this.classList.add('active');
                this.classList.add('border-blue-600');
                this.classList.remove('text-gray-500');
                
                // Show corresponding content
                var target = this.getAttribute('data-tab-target');
                var targetContent = document.querySelector(target);
                if (targetContent) {
                    targetContent.classList.add('active');
                }
            });
        });
    }
    
    // Initialize tabs immediately and also after a short delay to ensure it runs
    initTabs();
    setTimeout(initTabs, 500);

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
    if (topicList) {
        new Sortable(topicList, {
            animation: 150,
            handle: '.topic-drag-handle',
            onEnd: function(evt) {
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
                    }
                })
                .catch(function(error) {
                });
            }
        });
    }

    // Close on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            if (settingsModal && settingsModal.classList.contains('active')) {
                closeModal(settingsModal);
            }
        }
    });
    
    // Add a global initialization function for tabs that can be called from elsewhere
    window.initializeCourseTabs = initTabs;
}); 

// Add a fallback to ensure tabs work even if DOMContentLoaded event has already fired
if (document.readyState === 'compvare' || document.readyState === 'interactive') {
    setTimeout(function() {
        var tabButtons = document.querySelectorAll('.tab-btn');
        var tabContents = document.querySelectorAll('.tab-content');
        
        tabButtons.forEach(function(button) {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                
                // Remove active class from all buttons and contents
                tabButtons.forEach(function(btn) {
                    btn.classList.remove('active');
                    btn.classList.remove('border-blue-600');
                    btn.classList.add('text-gray-500');
                });
                
                tabContents.forEach(function(content) {
                    content.classList.remove('active');
                });
                
                // Add active class to clicked button
                this.classList.add('active');
                this.classList.add('border-blue-600');
                this.classList.remove('text-gray-500');
                
                // Show corresponding content
                var target = this.getAttribute('data-tab-target');
                var targetContent = document.querySelector(target);
                if (targetContent) {
                    targetContent.classList.add('active');
                }
            });
        });
    }, 500);
} 