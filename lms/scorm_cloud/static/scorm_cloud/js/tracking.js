// SCORM Tracking functionality
const SCORMTracking = {
    updateProgress: async function(topicId) {
        try {
            const response = await fetch(`/scorm/topic/${topicId}/tracking/update/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to update SCORM progress');
            }
            
            return await response.json();
        } catch (error) {
            console.error('Error updating SCORM progress:', error);
            return null;
        }
    },
    
    getStatus: async function(topicId) {
        try {
            const response = await fetch(`/scorm/topic/${topicId}/tracking/status/`);
            
            if (!response.ok) {
                throw new Error('Failed to get SCORM status');
            }
            
            return await response.json();
        } catch (error) {
            console.error('Error getting SCORM status:', error);
            return null;
        }
    }
};

// Helper function to get CSRF token
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

// Initialize tracking when SCORM content is loaded
document.addEventListener('DOMContentLoaded', function() {
    const scormFrame = document.getElementById('scormFrame');
    if (scormFrame) {
        // Update progress periodically
        setInterval(async function() {
            const topicId = scormFrame.dataset.topicId;
            if (topicId) {
                await SCORMTracking.updateProgress(topicId);
            }
        }, 30000); // Update every 30 seconds
    }
}); 