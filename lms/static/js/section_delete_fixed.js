/**
 * Section Delete Handler - Fixed version
 * Handles section deletion with proper error handling
 */
document.addEventListener('DOMContentLoaded', function() {
    // Debug logging removed for production
    
    // Initialize section delete functionality
    const deleteButtons = document.querySelectorAll('[data-action="delete-section"]');
    
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            try {
                e.preventDefault();
                
                const sectionId = this.getAttribute('data-section-id');
                const sectionName = this.getAttribute('data-section-name');
                
                if (confirm(`Are you sure you want to delete the section "${sectionName}"? This will also delete all topics in this section.`)) {
                    // Handle section deletion
                    deleteSection(sectionId);
                }
            } catch (error) {
                console.error('Error handling section delete click:', error);
            }
        });
    });
    
    function deleteSection(sectionId) {
        try {
            const csrfToken = getCookie('csrftoken');
            
            if (!csrfToken) {
                alert('CSRF token not found. Please refresh the page and try again.');
                return;
            }
            
            fetch(`/courses/section/${sectionId}/delete/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                }
            })
            .then(response => {
                try {
                    return response.json();
                } catch (error) {
                    console.error('Error parsing response:', error);
                    throw error;
                }
            })
            .then(data => {
                try {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert('Error deleting section: ' + (data.error || 'Unknown error'));
                    }
                } catch (error) {
                    console.error('Error processing delete response:', error);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error deleting section: ' + error.message);
            });
        } catch (error) {
            console.error('Error in deleteSection function:', error);
        }
    }
    
    function getCookie(name) {
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
    }
    
    if (window.DEBUG_MODE) {
        // Debug logging removed for production
    }
});
