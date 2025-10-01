/**
 * Course Progress JavaScript
 * Handles fetching and displaying course progress in the course details page
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Course progress script loaded');
    
    // Check if user is enrolled by looking for the progress bar container
    const progressBarContainer = document.querySelector('.progress-container, .mb-6');
    if (!progressBarContainer) {
        console.log('User not enrolled or progress container not found. Skipping progress tracking.');
        return;
    }
    
    // Initialize course progress tracking
    initCourseProgress();
});

function initCourseProgress() {
    // Get course ID from the page
    let courseId = document.getElementById('course-data')?.dataset?.courseId;
    
    // If not found, try the course-container
    if (!courseId) {
        const container = document.querySelector('.course-container');
        if (container) {
            courseId = container.getAttribute('data-course-id');
            console.log('Found course ID from container:', courseId);
        }
    }
    
    // If still not found, try to extract from URL
    if (!courseId) {
        const urlPath = window.location.pathname;
        const courseIdMatch = urlPath.match(/\/courses\/(\d+)\/view\//);
        if (courseIdMatch && courseIdMatch[1]) {
            courseId = courseIdMatch[1];
            console.log('Extracted course ID from URL:', courseId);
        }
    }
    
    if (!courseId) {
        console.log('Could not find course ID for progress tracking. Elements on page:', {
            'course-data': document.getElementById('course-data'),
            'course-container': document.querySelector('.course-container')
        });
        return;
    }
    
    console.log('Initializing progress tracking for course:', courseId);
    
    // Find progress elements
    const progressBar = document.getElementById('progress-bar');
    const progressPercentage = document.getElementById('progress-percentage');
    
    // If progress elements don't exist, we likely don't have the right permissions
    if (!progressBar || !progressPercentage) {
        console.log('Progress elements not found. User may not be enrolled.');
        return;
    }
    
    // If progress bar already exists in the DOM with initial values, update its width directly
    if (progressBar) {
        console.log('Initial progress bar found:', progressBar);
        // Ensure the width is properly set with percentage units
        const currentStyle = progressBar.getAttribute('style');
        if (currentStyle && currentStyle.includes('width:')) {
            // Make sure the width ends with '%'
            if (!currentStyle.includes('%')) {
                const widthValue = parseInt(currentStyle.replace(/width:\s*/, ''));
                if (!isNaN(widthValue)) {
                    progressBar.style.width = `${widthValue}%`;
                    console.log('Fixed initial progress bar width:', progressBar.style.width);
                }
            }
        }
    }
    
    // Load initial progress data
    loadProgressData();
    
    // Set up periodic refresh (every 30 seconds for reasonable balance between updates and performance)
    setInterval(loadProgressData, 30000);
    
    function loadProgressData() {
        fetch(`/courses/${courseId}/progress/`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (!data.success) {
                    console.error('Error in progress data:', data.error || 'Unknown error');
                    return;
                }
                
                // Update button state first based on progress
                updateButtonState(data.overall_progress);
                
                // Update course overall progress
                if (progressBar && data.overall_progress !== undefined) {
                    console.log('Setting progress bar width to:', `${data.overall_progress}%`);
                    progressBar.style.width = `${data.overall_progress}%`;
                    
                    // Double check that the width was set properly
                    setTimeout(() => {
                        if (progressBar.style.width !== `${data.overall_progress}%`) {
                            console.log('Progress bar width not set correctly, forcing update');
                            progressBar.style.width = `${data.overall_progress}%`;
                        }
                    }, 100);
                }
                
                if (progressPercentage && data.completed_topics !== undefined && data.total_topics !== undefined) {
                    progressPercentage.textContent = `${data.completed_topics}/${data.total_topics} (${Math.round(data.overall_progress)}%)`;
                }
                
                // Update individual topic progress
                if (data.topics) {
                    data.topics.forEach(topic => {
                        updateTopicStatus(topic.id, topic.completed);
                    });
                }
            })
            .catch(error => {
                console.error('Error fetching progress data:', error);
            });
    }
    
    // Helper function to update button state based on progress
    function updateButtonState(progress) {
        console.log('updateButtonState called with progress:', progress);
        
        const startButton = document.querySelector('.start-button');
        if (!startButton) {
            console.log('No start button found');
            return;
        }
        
        // Reset classes
        startButton.classList.remove('resume-button', 'completed-button');
        
        // Update text and add appropriate class based on progress
        if (progress === 100) {
            console.log('Setting button to Show Certificate mode');
            // Change to certificate button
            startButton.textContent = 'Show Certificate';
            startButton.classList.add('completed-button');
            
            // Update href and onclick
            startButton.href = '#';
            startButton.id = 'show-certificate-btn';
            startButton.setAttribute('onclick', 'showCertificateTab()');
            
            // If this was previously a different button type, we need to update the link
            const firstTopicLink = document.querySelector('.topic-item');
            const courseId = document.querySelector('.course-container').getAttribute('data-course-id');
            
            // Remove any existing event listeners by cloning and replacing
            const newButton = startButton.cloneNode(true);
            startButton.parentNode.replaceChild(newButton, startButton);
        } else if (progress > 0) {
            console.log('Setting button to Resume mode');
            // Resume button
            startButton.textContent = 'Resume';
            startButton.classList.add('resume-button');
            
            // Clear certificate onclick if it was previously set
            if (startButton.getAttribute('onclick')) {
                // Clone and replace to remove event listeners
                const newButton = startButton.cloneNode(true);
                newButton.removeAttribute('onclick');
                newButton.removeAttribute('id');
                startButton.parentNode.replaceChild(newButton, startButton);
            }
        } else {
            console.log('Setting button to Start mode');
            // Start button
            startButton.textContent = 'Start';
            
            // Clear certificate onclick if it was previously set
            if (startButton.getAttribute('onclick')) {
                // Clone and replace to remove event listeners
                const newButton = startButton.cloneNode(true);
                newButton.removeAttribute('onclick');
                newButton.removeAttribute('id');
                startButton.parentNode.replaceChild(newButton, startButton);
            }
        }
        
        // Make sure the button has the arrow
        const startButtonUpdated = document.querySelector('.start-button');
        if (startButtonUpdated && !startButtonUpdated.querySelector('svg')) {
            const arrowSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            arrowSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
            arrowSvg.setAttribute('viewBox', '0 0 20 20');
            arrowSvg.setAttribute('fill', 'currentColor');
            
            const pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            pathEl.setAttribute('fill-rule', 'evenodd');
            pathEl.setAttribute('d', 'M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z');
            pathEl.setAttribute('clip-rule', 'evenodd');
            
            arrowSvg.appendChild(pathEl);
            startButtonUpdated.appendChild(arrowSvg);
        }
    }
    
    // Helper function to mark topic completion in the UI
    function updateTopicStatus(topicId, completed) {
        if (!topicId) return;
        
        const topicItem = document.querySelector(`.topic-item[data-topic-id="${topicId}"]`);
        if (!topicItem) return;
        
        if (completed) {
            const checkCircle = topicItem.querySelector('.w-5.h-5.rounded-full');
            if (checkCircle && !checkCircle.classList.contains('bg-green-500')) {
                checkCircle.classList.remove('border-2', 'border-gray-300');
                checkCircle.classList.add('bg-green-500', 'flex', 'items-center', 'justify-center', 'text-white');
                checkCircle.innerHTML = `<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>`;
            }
        }
    }
    
    // Handle topic click to mark as completed (if applicable)
    document.querySelectorAll('.topic-complete-button').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const topicId = this.dataset.topicId;
            
            if (!topicId) return;
            
            fetch(`/courses/topic/${topicId}/complete/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ completed: true })
            })
            .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
            .then(data => {
                if (data.success) {
                    // Update UI to show completion
                    updateTopicStatus(topicId, true);
                    // Refresh overall progress
                    loadProgressData();
                }
            })
            .catch(error => {
                console.error('Error marking topic as complete:', error);
            });
        });
    });
    
    // Helper function to get CSRF token
    function getCsrfToken() {
        return document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';
    }
} 