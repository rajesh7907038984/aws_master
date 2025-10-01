document.addEventListener('DOMContentLoaded', function() {
    console.log('Course edit JS loaded');
    
    // Tab functionality
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    console.log('Found tab buttons:', tabButtons.length);
    console.log('Found tab contents:', tabContents.length);
    
    // Initialize tab functionality
    function initTabs() {
        tabButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                console.log('Tab clicked:', this.getAttribute('data-tab-target'));
                
                // Remove active class from all buttons and contents
                tabButtons.forEach(btn => {
                    btn.classList.remove('active');
                    btn.classList.remove('border-blue-600');
                    btn.classList.add('text-gray-500');
                });
                
                tabContents.forEach(content => {
                    content.classList.remove('active');
                });
                
                // Add active class to clicked button
                this.classList.add('active');
                this.classList.add('border-blue-600');
                this.classList.remove('text-gray-500');
                
                // Show corresponding content
                const target = this.getAttribute('data-tab-target');
                const targetContent = document.querySelector(target);
                console.log('Target content found:', !!targetContent);
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
    if (topicList) {
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
    }

    // Close on escape key
    document.addEventListener('keydown', (e) => {
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
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(function() {
        console.log('Initializing tabs after document load');
        const tabButtons = document.querySelectorAll('.tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');
        
        tabButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                console.log('Tab clicked (fallback):', this.getAttribute('data-tab-target'));
                
                // Remove active class from all buttons and contents
                tabButtons.forEach(btn => {
                    btn.classList.remove('active');
                    btn.classList.remove('border-blue-600');
                    btn.classList.add('text-gray-500');
                });
                
                tabContents.forEach(content => {
                    content.classList.remove('active');
                });
                
                // Add active class to clicked button
                this.classList.add('active');
                this.classList.add('border-blue-600');
                this.classList.remove('text-gray-500');
                
                // Show corresponding content
                const target = this.getAttribute('data-tab-target');
                const targetContent = document.querySelector(target);
                if (targetContent) {
                    targetContent.classList.add('active');
                }
            });
        });
    }, 500);
} 