// Debug: Verify file is loaded
console.log('topic_actions.js loaded successfully');

// Function to edit a topic
function editTopic(topicId) {
    console.log('editTopic called with topicId:', topicId);
    console.log('Current URL:', window.location.href);
    console.log('User agent:', navigator.userAgent);
    
    // Get the CSRF token
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    if (!csrfToken) {
        console.error('CSRF token not found!');
        showNotification('CSRF token not found. Please refresh the page.', 'error');
        return;
    }
    console.log('CSRF token found:', csrfToken.value ? 'Yes' : 'No');
    
    // Make a GET request to get the topic data with timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
    
    const requestUrl = `/courses/topic/${topicId}/edit/`;
    console.log('Making request to:', requestUrl);
    
    fetch(requestUrl, {
        method: 'GET',
        headers: {
            'X-CSRFToken': csrfToken.value,
            'X-Requested-With': 'XMLHttpRequest'
        },
        signal: controller.signal
    })
    .then(response => {
        clearTimeout(timeoutId); // Clear timeout on successful response
        if (!response.ok) {
            throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            console.log('Topic data received:', data.topic);
            
            // First navigate to the edit page if not already there
            if (!window.location.href.includes(`/topic/${topicId}/edit/`)) {
                window.location.href = `/courses/topic/${topicId}/edit/`;
                return;
            }
            
            console.log('Starting to populate form fields for topic ID:', topicId);
            
            // Find and set values for basic fields
            setFieldValue('topic_title', data.topic.title);
            setFieldValue('topic_description', data.topic.description);
            setFieldValue('status', data.topic.status);
            
            // Set dates
            if (data.topic.start_date) {
                console.log('Setting start date:', data.topic.start_date);
                setFieldValue('topic_start_date', data.topic.start_date);
            }
            
            if (data.topic.endless_access) {
                console.log('Topic has endless access');
                const endlessAccessCheckbox = document.getElementById('topic_endless_access');
                if (endlessAccessCheckbox) {
                    endlessAccessCheckbox.checked = true;
                    // Disable end date field
                    const endDateField = document.getElementById('topic_end_date');
                    if (endDateField) endDateField.disabled = true;
                } else {
                    console.warn('Could not find endless_access checkbox');
                }
            } else if (data.topic.end_date) {
                console.log('Setting end date:', data.topic.end_date);
                setFieldValue('topic_end_date', data.topic.end_date);
            }
            
            // Select the proper content type radio button
            const contentTypeRadio = document.querySelector(`input[name="content_type"][value="${data.topic.content_type}"]`);
            if (contentTypeRadio) {
                contentTypeRadio.checked = true;
                
                // Trigger content type display
                const contentTypeEvent = new Event('change');
                contentTypeRadio.dispatchEvent(contentTypeEvent);
                
                // Ensure the appropriate content field is visible
                showContentField(data.topic.content_type);
                
                // Set content based on type
                switch (data.topic.content_type) {
                    case 'Text':
                        handleTextContent(data.topic);
                        break;
                    case 'Web':
                        setFieldValue('web_url', data.topic.web_url);
                        break;
                    case 'EmbedVideo':
                        const embedField = document.querySelector('textarea[name="embed_code"]');
                        if (embedField) embedField.value = data.topic.embed_code || '';
                        break;
                    case 'Quiz':
                        setSelectFieldValue('quiz', data.topic.quiz_id);
                        // Ensure quiz content field is visible
                        const quizField = document.getElementById('quiz-content');
                        if (quizField) {
                            quizField.style.display = 'block';
                            quizField.style.visibility = 'visible';
                            quizField.style.opacity = '1';
                        }
                        break;
                    case 'Assignment':
                        console.log('Handling assignment content type, assignment_id:', data.topic.assignment_id);
                        setSelectFieldValue('assignment', data.topic.assignment_id);
                        // Ensure assignment content field is visible
                        const assignmentField = document.getElementById('assignment-content');
                        if (assignmentField) {
                            console.log('Making assignment field visible');
                            assignmentField.style.display = 'block';
                            assignmentField.style.visibility = 'visible';
                            assignmentField.style.opacity = '1';
                            assignmentField.classList.add('active');
                        }
                        break;
                    case 'Conference':
                        setSelectFieldValue('conference', data.topic.conference_id);
                        // Ensure conference content field is visible
                        const conferenceField = document.getElementById('conference-content');
                        if (conferenceField) {
                            conferenceField.style.display = 'block';
                            conferenceField.style.visibility = 'visible';
                            conferenceField.style.opacity = '1';
                        }
                        break;
                    case 'Discussion':
                        setSelectFieldValue('discussion', data.topic.discussion_id);
                        // Ensure discussion content field is visible
                        const discussionField = document.getElementById('discussion-content');
                        if (discussionField) {
                            discussionField.style.display = 'block';
                            discussionField.style.visibility = 'visible';
                            discussionField.style.opacity = '1';
                        }
                        break;
                    // For file based content types, we can't populate the input
                    // but we can show the current file name
                    case 'Audio':
                    case 'Video':
                    case 'Document':
                    case 'SCORM':
                        if (data.topic.content_file) {
                            const fileContainer = document.querySelector(`#${data.topic.content_type.toLowerCase()}-content .file-upload-container`);
                            if (fileContainer) {
                                const filenameEl = fileContainer.querySelector('.selected-filename');
                                if (filenameEl) {
                                    filenameEl.textContent = `Current file: ${getFilenameFromUrl(data.topic.content_file)}`;
                                    filenameEl.classList.remove('hidden');
                                }
                            }
                        }
                        break;
                }
                
                // Additional check to ensure content field is visible (after a delay to allow DOM updates)
                setTimeout(() => {
                    showContentField(data.topic.content_type);
                }, 200);
            }
        } else {
            throw new Error(data.error || 'Error loading topic data');
        }
    })
    .catch(error => {
        console.error('Topic edit error:', error);
        console.error('Error details:', {
            message: error.message,
            stack: error.stack,
            url: window.location.href,
            topicId: topicId,
            isStaging: window.location.hostname.includes('staging'),
            isLocal: false
        });
        
        // Check if it's a timeout error
        if (error.name === 'AbortError') {
            console.error('Request timed out after 10 seconds');
            showNotification('Request timed out. This might be a staging server issue. Please try again.', 'error');
        } else {
            // Show more detailed error message
            const errorMessage = error.message || 'Error loading topic data';
            showNotification(`Topic edit failed: ${errorMessage}`, 'error');
        }
        
        // Fallback: redirect to course edit page
        setTimeout(() => {
            const courseId = window.location.pathname.match(/\/courses\/(\d+)\/edit\//);
            if (courseId) {
                console.log('Redirecting to course edit page as fallback');
                window.location.href = `/courses/${courseId[1]}/edit/`;
            }
        }, 3000);
    });
}

// Helper function to set field values
function setFieldValue(fieldId, value) {
    if (value === undefined || value === null) {
        console.log(`Skipping field ${fieldId} due to null/undefined value`);
        return;
    }
    
    // First try by ID (exact match)
    let field = document.getElementById(fieldId);
    
    // If not found, try looking by name attribute
    if (!field) {
        field = document.querySelector(`[name="${fieldId}"]`);
        if (field) {
            console.log(`Field ${fieldId} found by name instead of ID`);
        }
    }
    
    // If still not found, try alternate IDs (for example, without 'topic_' prefix)
    if (!field && fieldId.startsWith('topic_')) {
        const altId = fieldId.replace('topic_', '');
        field = document.getElementById(altId) || document.querySelector(`[name="${altId}"]`);
        if (field) {
            console.log(`Field ${fieldId} found with alternate ID ${altId}`);
        }
    }
    
    // If still not found, try by input type + name pattern
    if (!field) {
        // Special case for title/description fields
        if (fieldId === 'topic_title' || fieldId === 'title') {
            field = document.querySelector('input[name="title"]');
        } else if (fieldId === 'topic_description' || fieldId === 'description') {
            field = document.querySelector('textarea[name="description"]');
        } else if (fieldId === 'topic_start_date' || fieldId === 'start_date') {
            field = document.querySelector('input[name="start_date"]');
        } else if (fieldId === 'topic_end_date' || fieldId === 'end_date') {
            field = document.querySelector('input[name="end_date"]');
        } else if (fieldId === 'status' || fieldId === 'topic_status') {
            field = document.querySelector('select[name="status"]') || document.getElementById('topic_status');
        }
        
        if (field) {
            console.log(`Field ${fieldId} found using specific selector`);
        }
    }
    
    if (field) {
        console.log(`Setting value for ${fieldId}:`, value);
        field.value = value;
    } else {
        console.warn(`Field with ID or name "${fieldId}" does not exist in the DOM`);
    }
}

// Helper function to set select field value
function setSelectFieldValue(fieldName, valueId) {
    if (!valueId) return;
    console.log(`Setting select field value for ${fieldName} to ${valueId}`);
    const select = document.querySelector(`select[name="${fieldName}"]`);
    if (select) {
        // First try to find the option by value
        let option = select.querySelector(`option[value="${valueId}"]`);
        
        if (option) {
            option.selected = true;
            // Trigger a change event to ensure any listeners are notified
            const event = new Event('change');
            select.dispatchEvent(event);
            console.log(`Successfully selected option with value ${valueId} for ${fieldName}`);
        } else {
            console.warn(`Could not find option with value ${valueId} for ${fieldName}`);
            
            // In case options are loaded dynamically, try again after a short delay
            setTimeout(() => {
                const retryOption = select.querySelector(`option[value="${valueId}"]`);
                if (retryOption) {
                    retryOption.selected = true;
                    // Trigger a change event
                    const event = new Event('change');
                    select.dispatchEvent(event);
                    console.log(`Successfully selected option with value ${valueId} for ${fieldName} after delay`);
                }
            }, 500);
        }
    } else {
        console.warn(`Select field with name "${fieldName}" not found in the DOM`);
    }
}

// Helper function to show the content field for the given type
function showContentField(contentType) {
    // Hide all content fields
    document.querySelectorAll('.content-type-field').forEach(field => {
        field.classList.remove('active');
    });
    
    // Show the selected content field
    let fieldId = '';
    switch(contentType) {
        case 'Text':
            fieldId = 'text-content';
            break;
        case 'Web':
            fieldId = 'web-content';
            break;
        case 'EmbedVideo':
            fieldId = 'embedvideo-content';
            break;
        case 'Audio':
            fieldId = 'audio-content';
            break;
        case 'Video':
            fieldId = 'video-content';
            break;
        case 'Document':
            fieldId = 'document-content';
            break;
        case 'Quiz':
            fieldId = 'quiz-content';
            break;
        case 'Assignment':
            fieldId = 'assignment-content';
            break;
        case 'Conference':
            fieldId = 'conference-content';
            break;
        case 'Discussion':
            fieldId = 'discussion-content';
            break;
        case 'SCORM':
            fieldId = 'scorm-content';
            break;
    }
    
    if (fieldId) {
        const field = document.getElementById(fieldId);
        if (field) {
            field.classList.add('active');
            field.style.display = 'block';
            field.style.visibility = 'visible';
            field.style.opacity = '1';
        }
    }
}

// Helper function to handle text content
function handleTextContent(topic) {
    if (!topic.text_content) return;
    
    console.log('Handling text content for topic:', topic.id);
    console.log('Text content data:', topic.text_content);
    
    // Function to decode HTML entities
    function decodeHtmlEntities(str) {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = str;
        return tempDiv.textContent || tempDiv.innerText || '';
    }
    
    // Set text content in textarea field first
    const textContentField = document.querySelector('textarea[name="text_content"]');
    if (textContentField) {
        console.log('Setting text content in textarea');
        textContentField.value = topic.text_content || '';
    }
    
    // Wait for TinyMCE to be initialized and handle the content
    const checkTinyMCE = setInterval(() => {
        if (typeof tinymce !== 'undefined' && tinymce.editors && tinymce.editors.length > 0) {
            // Find the TinyMCE editor for text content
            const textEditor = tinymce.get('id_text_content');
            if (textEditor) {
                clearInterval(checkTinyMCE);
                
                try {
                    let htmlContent = '';
                    
                    // Handle different formats of text_content
                    if (typeof topic.text_content === 'string') {
                        // Check if it's JSON format first
                        if (topic.text_content.trim().startsWith('{') && topic.text_content.trim().endsWith('}')) {
                            try {
                                const content = JSON.parse(topic.text_content);
                                if (content && content.html) {
                                    htmlContent = content.html;
                                    console.log('Parsed JSON content successfully');
                                } else {
                                    // Valid JSON but without html property - decode entities
                                    htmlContent = decodeHtmlEntities(topic.text_content);
                                    console.log('JSON parsed but no HTML property found, decoded entities');
                                }
                            } catch (e) {
                                // If parsing fails, decode HTML entities
                                console.log('JSON parsing failed, decoding HTML entities');
                                htmlContent = decodeHtmlEntities(topic.text_content);
                            }
                        } else {
                            // Not JSON format - decode HTML entities
                            console.log('Not JSON format, decoding HTML entities');
                            htmlContent = decodeHtmlEntities(topic.text_content);
                        }
                    } else if (typeof topic.text_content === 'object') {
                        // Already an object
                        if (topic.text_content.html) {
                            htmlContent = topic.text_content.html;
                            console.log('Using object HTML content');
                        } else {
                            // No html property, convert to string and decode
                            htmlContent = decodeHtmlEntities(JSON.stringify(topic.text_content));
                            console.log('No HTML in object, stringified and decoded');
                        }
                    }
                    
                    // Set content in TinyMCE editor
                    console.log('Setting TinyMCE content:', htmlContent.substring(0, 100) + '...');
                    textEditor.setContent(htmlContent);
                    
                } catch (e) {
                    console.error('Error setting TinyMCE content:', e);
                    // Fallback: set raw content
                    textEditor.setContent(topic.text_content || '');
                }
            }
        }
    }, 200);
    
    // Stop checking after 10 seconds
    setTimeout(() => {
        clearInterval(checkTinyMCE);
    }, 10000);
}

// Helper function to extract filename from URL
function getFilenameFromUrl(url) {
    if (!url) return 'No file';
    const parts = url.split('/');
    return parts[parts.length - 1];
}

// Function to delete a topic
function deleteTopic(topicId) {
    if (!confirm('Are you sure you want to delete this topic?')) {
        return;
    }

    // Get the CSRF token
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    
    // Make a POST request to delete the topic
    fetch(`/courses/topic/${topicId}/delete/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        
        // Check content type before parsing JSON
        const contentType = response.headers.get('Content-Type');
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        } else {
            // Handle non-JSON responses as errors
            console.error('Received non-JSON response from topic delete endpoint');
            throw new Error('Invalid response format from server');
        }
    })
    .then(data => {
        if (data.success) {
            // Remove the topic element from the DOM
            const topicElement = document.querySelector(`[data-topic-id="${topicId}"]`);
            if (topicElement) {
                topicElement.remove();
                
                // Check if there are no more topics
                const topicsList = document.querySelector('.topics-list');
                if (topicsList && topicsList.children.length === 0) {
                    // Show the empty state
                    topicsList.innerHTML = `
                        <div class="text-center py-8">
                            <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path>
                            </svg>
                            <h3 class="mt-2 text-sm font-medium text-gray-900">No topics</h3>
                            <p class="mt-1 text-sm text-gray-500">Get started by creating a new topic.</p>
                            <div class="mt-6">
                                <button type="button" id="add-topic-btn" class="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-[#1c2261] hover:bg-[#1c2261]/90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#1c2261]">
                                    <svg class="-ml-1 mr-2 h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
                                    </svg>
                                    Add Topic
                                </button>
                            </div>
                        </div>
                    `;
                }
                
                // Show success notification
                const notification = document.createElement('div');
                notification.className = 'fixed top-4 right-4 p-4 rounded-lg shadow-lg bg-green-500 text-white z-50';
                notification.textContent = data.message || 'Topic deleted successfully';
                document.body.appendChild(notification);
                
                // Remove notification after 3 seconds
                setTimeout(() => {
                    notification.remove();
                }, 3000);
            }
        } else {
            throw new Error(data.error || 'Error deleting topic');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        // Show error notification
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 p-4 rounded-lg shadow-lg bg-red-500 text-white z-50';
        notification.textContent = error.message || 'Error deleting topic';
        document.body.appendChild(notification);
        
        // Remove notification after 3 seconds
        setTimeout(() => {
            notification.remove();
        }, 3000);
    });
}

// Function to view a topic
function viewTopic(topicId) {
    // Redirect to the topic view page
    window.location.href = `/courses/topic/${topicId}/view/?manual=True`;
}

// Function to move a topic up or down
function moveTopic(topicId, direction) {
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    const courseId = document.querySelector('[name=course_id]').value;
    
    fetch(`/courses/api/topics/reorder/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({
            course_id: courseId,
            topic_id: topicId,
            direction: direction
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            // Reload the page to show updated order
            window.location.reload();
        } else {
            showNotification(data.error || 'Error reordering topic', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Error reordering topic', 'error');
    });
}

// Function to show notifications
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg ${
        type === 'success' ? 'bg-green-500' :
        type === 'error' ? 'bg-red-500' :
        'bg-blue-500'
    } text-white z-50`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Remove notification after 3 seconds
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Function to close the edit modal
function closeEditModal() {
    document.getElementById('editTopicModal').classList.add('hidden');
}

// Function to show the move topic modal
function showMoveTopicModal(topicId) {
    // Set the topic ID in the hidden input
    document.getElementById('topic_id_to_move').value = topicId;
    
    // Show the modal
    document.getElementById('move-topic-modal').classList.remove('hidden');
}

// Function to hide the move topic modal
function hideMoveTopicModal() {
    document.getElementById('move-topic-modal').classList.add('hidden');
}

// Add to global scope for use in HTML onclick attributes
window.showMoveTopicModal = showMoveTopicModal;
window.hideMoveTopicModal = hideMoveTopicModal;
window.deleteTopic = deleteTopic;

// Add event listeners when the document is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners to move topic buttons
    const moveTopicButtons = document.querySelectorAll('.move-topic-btn');
    moveTopicButtons.forEach(button => {
        button.addEventListener('click', function() {
            const topicItem = this.closest('.topic-item');
            const topicId = topicItem.dataset.id;
            showMoveTopicModal(topicId);
        });
    });
    
    // Handle move topic form submission
    const moveTopicForm = document.getElementById('moveTopicForm');
    if (moveTopicForm) {
        moveTopicForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
            
            fetch('/courses/move_topic_to_section/', {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Hide the modal
                    hideMoveTopicModal();
                    
                    // Show a success notification
                    showNotification(data.message || 'Topic moved successfully', 'success');
                    
                    // Reload the page to reflect changes
                    setTimeout(() => {
                        window.location.reload();
                    }, 1000);
                } else {
                    throw new Error(data.error || 'Error moving topic');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showNotification(error.message || 'Error moving topic', 'error');
            });
        });
    }

    // Enable auto-completion when visiting a topic
    autoMarkTopicAsComplete();
    
    // Add manual complete button for text topics
    addManualCompleteButtonForTextTopic();

    // Additional initialization for assignment type topics - runs when DOM is fully loaded
    if (window.location.pathname.includes('/topic/') && window.location.pathname.includes('/edit')) {
        // Check if this is an assignment topic
        const assignmentRadio = document.querySelector('input[name="content_type"][value="Assignment"]');
        if (assignmentRadio && assignmentRadio.checked) {
            console.log('Assignment content type detected - ensuring field is visible');
            // Find the assignment content field
            const assignmentField = document.getElementById('assignment-content');
            if (assignmentField) {
                // Force display
                assignmentField.style.display = 'block';
                assignmentField.style.visibility = 'visible';
                assignmentField.style.opacity = '1';
                assignmentField.classList.add('active');
                
                // Also make sure assignment select is visible
                const assignmentSelect = assignmentField.querySelector('select[name="assignment"]');
                if (assignmentSelect) {
                    assignmentSelect.style.display = 'block';
                    assignmentSelect.style.visibility = 'visible';
                    assignmentSelect.style.opacity = '1';
                    
                    // Get assignment ID from hidden field
                    const assignmentIdField = document.querySelector('[name="assignment_id"]');
                    if (assignmentIdField && assignmentIdField.value) {
                        // Find and select the corresponding option
                        const option = assignmentSelect.querySelector(`option[value="${assignmentIdField.value}"]`);
                        if (option) {
                            option.selected = true;
                            console.log('Selected assignment option from hidden field value:', assignmentIdField.value);
                        }
                    }
                }
            }
        }
    }
});

/**
 * Auto mark topic as complete when the page loads
 * This function checks if the current URL matches a topic view pattern
 * and if it does, it will automatically mark the topic as complete
 */
function autoMarkTopicAsComplete() {
    console.log('autoMarkTopicAsComplete function called');
    
    // Check if we're on a topic view page
    const urlPattern = /\/courses\/topic\/(\d+)\/view\//;
    const match = window.location.pathname.match(urlPattern);
    console.log('URL match:', match);
    
    if (match) {
        const topicId = match[1];
        console.log('Topic ID:', topicId);
        
        const completeForm = document.querySelector(`form[action^='/courses/topic/${topicId}/complete/']`);
        console.log('Complete form found:', completeForm ? true : false);
        
        // Debug body classes
        console.log('Body class list:', document.body.classList);
        console.log('Document URL:', window.location.href);
        
        // Check for manual completion types in multiple ways
        
        // 1. First check body classes
        const hasManualCompletionClass = 
            document.body.classList.contains('topic-type-text') || 
            document.body.classList.contains('topic-type-document') ||
            document.body.classList.contains('topic-type-web') ||
            document.body.classList.contains('topic-type-embedvideo');
        
        // 2. Also check for content type indicators in the DOM
        const textContentElement = document.querySelector('.text-content');
        const documentContentElement = document.querySelector('.document-content');
        const webContentElement = document.querySelector('.web-content-frame, .web-content-container');
        const embedVideoElement = document.querySelector('.embed-video-container');
        const assignmentContentElement = document.querySelector('.assignment-content, [data-content-type="Assignment"]');
        const scormContentElement = document.querySelector('.scorm-content, [data-content-type="SCORM"]');
        const quizContentElement = document.querySelector('.quiz-content, [data-content-type="Quiz"]');
        const conferenceContentElement = document.querySelector('.conference-content, [data-content-type="Conference"]');
        const discussionContentElement = document.querySelector('.discussion-content, [data-content-type="Discussion"]');
        
        // 3. Check for topic type meta tag that may be added by the server
        const topicTypeMeta = document.querySelector('meta[name="topic-type"]');
        const metaTopicType = topicTypeMeta ? topicTypeMeta.getAttribute('content') : null;
        
        // 4. Check for an explicit data attribute on the content container
        const contentContainer = document.querySelector('[data-content-type]');
        const containerContentType = contentContainer ? contentContainer.getAttribute('data-content-type') : null;
        
        // 5. Check for topic type from the main container
        const mainContainer = document.querySelector('[data-topic-type]');
        const mainContainerType = mainContainer ? mainContainer.getAttribute('data-topic-type') : null;
        
        // Combine all checks - Assignment topics should auto-complete
        const isManualCompletionType = 
            hasManualCompletionClass || 
            textContentElement || 
            documentContentElement || 
            webContentElement || 
            (metaTopicType && ['Text', 'Document', 'Web'].includes(metaTopicType)) ||
            (containerContentType && ['Text', 'Document', 'Web'].includes(containerContentType));
        
        console.log('Has manual completion class:', hasManualCompletionClass);
        console.log('Text content element found:', !!textContentElement);
        console.log('Document content element found:', !!documentContentElement);
        console.log('Web content element found:', !!webContentElement);
        console.log('Embed video element found:', !!embedVideoElement);
        console.log('Assignment content element found:', !!assignmentContentElement);
        console.log('SCORM content element found:', !!scormContentElement);
        console.log('Quiz content element found:', !!quizContentElement);
        console.log('Conference content element found:', !!conferenceContentElement);
        console.log('Discussion content element found:', !!discussionContentElement);
        console.log('Topic type from meta tag:', metaTopicType);
        console.log('Content type from container:', containerContentType);
        console.log('Main container type:', mainContainerType);
        console.log('Is manual completion type:', isManualCompletionType);
            
        // Special handling for auto-complete topics - they should auto-complete
        const isAutoCompleteTopic = 
            assignmentContentElement || 
            scormContentElement ||
            quizContentElement ||
            conferenceContentElement ||
            discussionContentElement ||
            (metaTopicType && ['Assignment', 'SCORM', 'Quiz', 'Conference', 'Discussion'].includes(metaTopicType)) ||
            (containerContentType && ['Assignment', 'SCORM', 'Quiz', 'Conference', 'Discussion'].includes(containerContentType)) ||
            (mainContainerType && ['assignment', 'scorm', 'quiz', 'conference', 'discussion'].includes(mainContainerType)) ||
            document.body.classList.contains('topic-type-assignment') ||
            document.body.classList.contains('topic-type-scorm') ||
            document.body.classList.contains('topic-type-quiz') ||
            document.body.classList.contains('topic-type-conference') ||
            document.body.classList.contains('topic-type-discussion');
        
        console.log('Is auto-complete topic:', isAutoCompleteTopic);
        
        // If content requires manual completion, skip auto-completion (except for auto-complete topics)
        if (isManualCompletionType && !isAutoCompleteTopic) {
            console.log('Manual completion content type detected, skipping auto-completion');
            return;
        }
        
        // For auto-complete topics, add a small delay to ensure page is fully loaded
        if (isAutoCompleteTopic) {
            console.log('Auto-complete topic detected, will auto-complete after delay');
            setTimeout(() => {
                performAutoComplete(topicId, completeForm);
            }, 2000); // 2 second delay for auto-complete topics
            return;
        }
        
        // Also check if the form itself has the manual-completion class
        // This is an alternative way to determine if the topic should have manual completion
        if (completeForm && completeForm.classList.contains('manual-completion-only')) {
            console.log('Form marked for manual completion only, skipping auto-completion');
            return;
        }
        
        // For non-assignment topics, auto-complete immediately
        if (completeForm) {
            performAutoComplete(topicId, completeForm);
        }
    }
}

/**
 * Perform auto-completion for a topic
 * @param {string} topicId - The ID of the topic to complete
 * @param {HTMLElement} completeForm - The completion form element
 */
function performAutoComplete(topicId, completeForm) {
    if (!completeForm) {
        console.log('No completion form found for topic:', topicId);
        return;
    }
    
    console.log('Performing auto-complete for topic:', topicId);
    
    // Create custom headers for the fetch request
    const headers = new Headers({
        'X-Requested-With': 'XMLHttpRequest',
        'X-Auto-Complete': 'true'  // Flag to indicate auto-completion
    });
    
    // Submit the form using fetch
    fetch(completeForm.action, {
        method: 'POST',
        body: new FormData(completeForm),
        headers: headers
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            console.log('Topic auto-marked as complete');
            // Update UI to reflect completion
            updateCompletionUI(topicId);
            
            // Show toast notification
            showCompletionToast(data.title || 'Topic');
        }
    })
    .catch(error => {
        console.error('Error auto-marking topic as complete:', error);
    });
}

/**
 * Update the UI after a topic is marked complete
 * @param {string} topicId - The ID of the completed topic
 */
function updateCompletionUI(topicId) {
    // Update the topic item in the sidebar
    const topicItem = document.querySelector(`.topic-item[data-topic-id="${topicId}"]`);
    if (topicItem) {
        const statusIcon = topicItem.querySelector('.status-icons');
        if (statusIcon) {
            statusIcon.innerHTML = `
                <span class="completed-icon">
                    <svg class="h-4 w-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                    </svg>
                </span>
            `;
        }
    }
    
    // If there's a mark complete button in the footer, hide it
    const completeFormContainer = document.querySelector('.fixed.bottom-0 form');
    if (completeFormContainer) {
        completeFormContainer.style.display = 'none';
    }
}

/**
 * Show a toast notification for topic completion
 * @param {string} topicTitle - The title of the completed topic
 */
function showCompletionToast(topicTitle) {
    // Create toast container if it doesn't exist
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }
    
    // Create toast element
    const toast = document.createElement('div');
    toast.className = 'topic-complete-toast toast-enter';
    toast.innerHTML = `
        <div class="icon">
            <i class="fas fa-check"></i>
        </div>
        <div class="message">
            <strong>${topicTitle}</strong> has been automatically marked as complete.
        </div>
        <button class="close">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    // Add to container
    toastContainer.appendChild(toast);
    
    // Add close button event listener
    const closeBtn = toast.querySelector('.close');
    closeBtn.addEventListener('click', () => {
        toast.classList.add('hide');
        setTimeout(() => {
            toast.remove();
        }, 300);
    });
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.classList.add('hide');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 5000);
}

/**
 * Add a manual complete button for text-type topics
 * This function adds a button below the content for text-type topics
 */
function addManualCompleteButtonForTextTopic() {
    // Check if we're on a topic view page
    const urlPattern = /\/courses\/topic\/(\d+)\/view\//;
    const match = window.location.pathname.match(urlPattern);
    
    if (match) {
        const topicId = match[1];
        const isTextTopic = document.body.classList.contains('topic-type-text');
        
        // Only add the button for text-type topics
        if (isTextTopic) {
            const completeForm = document.querySelector(`form[action^='/courses/topic/${topicId}/complete/']`);
            
            // If form exists but no manual complete button in the content area yet
            if (completeForm && !document.querySelector('.text-content-complete-button')) {
                const textContent = document.querySelector('.text-content');
                
                if (textContent) {
                    // Create the complete button for the content area
                    const completeButton = document.createElement('button');
                    completeButton.className = 'text-content-complete-button inline-flex items-center px-5 py-2 mt-4 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors font-medium shadow-sm';
                    completeButton.innerHTML = '<i class="fas fa-check mr-2"></i>Mark as Complete';
                    
                    // Add click handler
                    completeButton.addEventListener('click', function() {
                        completeForm.dispatchEvent(new Event('submit', { cancelable: true }));
                    });
                    
                    // Append button to the text content area
                    textContent.appendChild(completeButton);
                }
            }
        }
    }
}

/**
 * Sync topic completion status with course details page
 * @param {number} topicId - The ID of the completed topic
 * @param {number} courseId - The ID of the course 
 */
function syncTopicCompletion(topicId, courseId) {
    if (!topicId || !courseId) return;
    
    // Store the completion in localStorage to sync between pages
    const completionKey = `topic_${topicId}_completed`;
    localStorage.setItem(completionKey, 'true');
    
    // Also store the course ID for reference
    localStorage.setItem(`topic_${topicId}_course`, courseId);
    
    // Update UI if we're on the topic view page
    updateCompletionUI(topicId);
    
    // If we're on the course details page, update the progress display
    const courseDetailsEl = document.querySelector(`.course-container[data-course-id="${courseId}"]`);
    if (courseDetailsEl) {
        // Find all topic items and count completed ones
        const allTopicItems = document.querySelectorAll('.topic-item');
        let completedCount = 0;
        
        allTopicItems.forEach(item => {
            const itemId = item.getAttribute('data-topic-id');
            if (localStorage.getItem(`topic_${itemId}_completed`) === 'true' || 
                item.querySelector('.completed-icon')) {
                completedCount++;
            }
        });
        
        // Update progress percentage
        const totalTopics = allTopicItems.length;
        if (totalTopics > 0) {
            const progressPercentage = Math.round((completedCount / totalTopics) * 100);
            const progressEl = courseDetailsEl.querySelector('.progress-percentage');
            if (progressEl) {
                progressEl.textContent = `${progressPercentage}%`;
            }
            
            // Update progress bar if it exists
            const progressBarEl = courseDetailsEl.querySelector('.progress-bar-fill');
            if (progressBarEl) {
                progressBarEl.style.width = `${progressPercentage}%`;
            }
        }
    }
}

// Hook into existing mark complete functionality
document.addEventListener('DOMContentLoaded', function() {
    // Get course ID from the page
    let courseId = null;
    const courseElement = document.querySelector('[data-course-id]');
    if (courseElement) {
        courseId = courseElement.getAttribute('data-course-id');
    }
    
    // Intercept the mark complete form submission
    const completeForms = document.querySelectorAll('form[action*="mark_topic_complete"]');
    completeForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // Allow normal form submission to proceed, but also sync the completion
            const topicIdMatch = form.action.match(/\/topic\/(\d+)\/complete/);
            if (topicIdMatch && topicIdMatch[1] && courseId) {
                const topicId = topicIdMatch[1];
                // Call after a small delay to ensure the server-side operation completes
                setTimeout(() => syncTopicCompletion(topicId, courseId), 500);
            }
        });
    });
    
    // Check for completions from other pages on page load
    const currentTopicElement = document.querySelector('.topic-item.active');
    if (currentTopicElement) {
        const topicId = currentTopicElement.getAttribute('data-topic-id');
        if (topicId && localStorage.getItem(`topic_${topicId}_completed`) === 'true') {
            updateCompletionUI(topicId);
        }
    }
}); 