/**
 * Unified Topic Actions for LMS
 * Handles topic-related actions across the application
 */

(function() {
    'use strict';

    const UnifiedTopicActions = {
        init: function() {
            this.setupTopicHandlers();
        },
        
        setupTopicHandlers: function() {
            // Handle topic creation
            document.addEventListener('click', (e) => {
                if (e.target.matches('[data-action="create-topic"]')) {
                    this.createTopic(e);
                }
                
                if (e.target.matches('[data-action="edit-topic"]')) {
                    this.editTopic(e);
                }
                
                if (e.target.matches('[data-action="delete-topic"]')) {
                    this.deleteTopic(e);
                }
                
                if (e.target.matches('[data-action="toggle-topic"]')) {
                    this.toggleTopic(e);
                }
            });
        },
        
        createTopic: function(event) {
            event.preventDefault();
            const form = event.target.closest('form');
            if (!form) return;
            
            const formData = new FormData(form);
            const topicData = {
                title: formData.get('title'),
                content: formData.get('content'),
                course_id: formData.get('course_id')
            };
            
            this.submitTopicAction('/api/topics/', 'POST', topicData)
                .then(response => {
                    this.showSuccess('Topic created successfully');
                    this.refreshTopicList();
                })
                .catch(error => {
                    this.showError('Failed to create topic: ' + error.message);
                });
        },
        
        editTopic: function(event) {
            event.preventDefault();
            const topicId = event.target.dataset.topicId;
            const form = event.target.closest('form');
            if (!form || !topicId) return;
            
            const formData = new FormData(form);
            const topicData = {
                title: formData.get('title'),
                content: formData.get('content')
            };
            
            this.submitTopicAction(`/api/topics/${topicId}/`, 'PUT', topicData)
                .then(response => {
                    this.showSuccess('Topic updated successfully');
                    this.refreshTopicList();
                })
                .catch(error => {
                    this.showError('Failed to update topic: ' + error.message);
                });
        },
        
        deleteTopic: function(event) {
            event.preventDefault();
            const topicId = event.target.dataset.topicId;
            if (!topicId) return;
            
            if (!confirm('Are you sure you want to delete this topic?')) {
                return;
            }
            
            this.submitTopicAction(`/api/topics/${topicId}/`, 'DELETE')
                .then(response => {
                    this.showSuccess('Topic deleted successfully');
                    this.refreshTopicList();
                })
                .catch(error => {
                    this.showError('Failed to delete topic: ' + error.message);
                });
        },
        
        toggleTopic: function(event) {
            event.preventDefault();
            const topicId = event.target.dataset.topicId;
            const isActive = event.target.dataset.active === 'true';
            
            this.submitTopicAction(`/api/topics/${topicId}/toggle/`, 'POST', { active: !isActive })
                .then(response => {
                    this.showSuccess('Topic status updated');
                    this.refreshTopicList();
                })
                .catch(error => {
                    this.showError('Failed to update topic status: ' + error.message);
                });
        },
        
        submitTopicAction: function(url, method, data = null) {
            const options = {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': window.getCSRFToken ? window.getCSRFToken() : ''
                }
            };
            
            if (data && method !== 'DELETE') {
                options.body = JSON.stringify(data);
            }
            
            return fetch(url, options)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    return response.json();
                });
        },
        
        refreshTopicList: function() {
            // Trigger a custom event to refresh topic lists
            window.dispatchEvent(new CustomEvent('topicListRefresh'));
        },
        
        showSuccess: function(message) {
            // Use existing notification system if available
            if (window.showNotification) {
                window.showNotification(message, 'success');
            } else {
                alert(message);
            }
        },
        
        showError: function(message) {
            // Use existing notification system if available
            if (window.showNotification) {
                window.showNotification(message, 'error');
            } else {
                alert(message);
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            UnifiedTopicActions.init();
        });
    } else {
        UnifiedTopicActions.init();
    }

    // Export to global scope
    window.UnifiedTopicActions = UnifiedTopicActions;
})();
