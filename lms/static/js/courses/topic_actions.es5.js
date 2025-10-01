// Debug: Verify file is loaded
console.log('topic_actions.es5.js loaded successfully');

// Function to edit a topic
function editTopic(topicId) {
    // Get the CSRF token
    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    
    // Make a GET request to get the topic data
    fetch('/courses/topic/' + topicId + '/edit/', {
        method: 'GET',
        headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(function(response) {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(function(data) {
        if (data.success) {
            console.log('Topic data received:', data.topic);
            
            // First navigate to the edit page if not already there
            if (window.location.href.indexOf('/topic/' + topicId + '/edit/') === -1) {
                window.location.href = '/courses/topic/' + topicId + '/edit/';
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
                var endlessAccessCheckbox = document.getElementById('topic_endless_access');
                if (endlessAccessCheckbox) {
                    endlessAccessCheckbox.checked = true;
                    // Disable end date field
                    var endDateField = document.getElementById('topic_end_date');
                    if (endDateField) endDateField.disabled = true;
                } else {
                    console.warn('Could not find endless_access checkbox');
                }
            } else if (data.topic.end_date) {
                console.log('Setting end date:', data.topic.end_date);
                setFieldValue('topic_end_date', data.topic.end_date);
            }
            
            // Select the proper content type radio button
            var contentTypeRadio = document.querySelector('input[name="content_type"][value="' + data.topic.content_type + '"]');
            if (contentTypeRadio) {
                contentTypeRadio.checked = true;
                
                // Trigger content type display
                var contentTypeEvent = new Event('change');
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
                        var embedField = document.querySelector('textarea[name="embed_code"]');
                        if (embedField) embedField.value = data.topic.embed_code || '';
                        break;
                    case 'Quiz':
                        setSelectFieldValue('quiz', data.topic.quiz_id);
                        // Ensure quiz content field is visible
                        var quizField = document.getElementById('quiz-content');
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
                        var assignmentField = document.getElementById('assignment-content');
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
                        var conferenceField = document.getElementById('conference-content');
                        if (conferenceField) {
                            conferenceField.style.display = 'block';
                            conferenceField.style.visibility = 'visible';
                            conferenceField.style.opacity = '1';
                        }
                        break;
                    case 'Discussion':
                        setSelectFieldValue('discussion', data.topic.discussion_id);
                        // Ensure discussion content field is visible
                        var discussionField = document.getElementById('discussion-content');
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
                            var fileContainer = document.querySelector('#' + data.topic.content_type.toLowerCase() + '-content .file-upload-container');
                            if (fileContainer) {
                                var filenameEl = fileContainer.querySelector('.selected-filename');
                                if (filenameEl) {
                                    filenameEl.textContent = 'Current file: ' + getFilenameFromUrl(data.topic.content_file);
                                    filenameEl.classList.remove('hidden');
                                }
                            }
                        }
                        break;
                }
                
                // Additional check to ensure content field is visible (after a delay to allow DOM updates)
                setTimeout(function() {
                    showContentField(data.topic.content_type);
                }, 200);
            }
        } else {
            throw new Error(data.error || 'Error loading topic data');
        }
    })
    .catch(function(error) {
        console.error('Error:', error);
        showNotification(error.message || 'Error loading topic data', 'error');
    });
}

// Helper function to set field values
function setFieldValue(fieldId, value) {
    if (value === undefined || value === null) {
        console.log('Skipping field ' + fieldId + ' due to null/undefined value');
        return;
    }
    
    // First try by ID (exact match)
    var field = document.getElementById(fieldId);
    
    // If not found, try looking by name attribute
    if (!field) {
        field = document.querySelector('[name="' + fieldId + '"]');
        if (field) {
            console.log('Field ' + fieldId + ' found by name instead of ID');
        }
    }
    
    // If still not found, try alternate IDs (for example, without 'topic_' prefix)
    if (!field && fieldId.indexOf('topic_') === 0) {
        var altId = fieldId.replace('topic_', '');
        field = document.getElementById(altId) || document.querySelector('[name="' + altId + '"]');
        if (field) {
            console.log('Field ' + fieldId + ' found with alternate ID ' + altId);
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
        }
        
        if (field) {
            console.log('Field ' + fieldId + ' found using specific selector');
        }
    }
    
    if (field) {
        console.log('Setting value for ' + fieldId + ':', value);
        field.value = value;
    } else {
        console.warn('Field with ID or name "' + fieldId + '" does not exist in the DOM');
    }
}

// Helper function to set select field value
function setSelectFieldValue(fieldName, valueId) {
    if (!valueId) return;
    console.log('Setting select field value for ' + fieldName + ' to ' + valueId);
    var select = document.querySelector('select[name="' + fieldName + '"]');
    if (select) {
        // First try to find the option by value
        var option = select.querySelector('option[value="' + valueId + '"]');
        
        if (option) {
            option.selected = true;
            // Trigger a change event to ensure any listeners are notified
            var event = new Event('change');
            select.dispatchEvent(event);
            console.log('Successfully selected option with value ' + valueId + ' for ' + fieldName);
        } else {
            console.warn('Could not find option with value ' + valueId + ' for ' + fieldName);
            
            // In case options are loaded dynamically, try again after a short delay
            setTimeout(function() {
                var retryOption = select.querySelector('option[value="' + valueId + '"]');
                if (retryOption) {
                    retryOption.selected = true;
                    // Trigger a change event
                    var event = new Event('change');
                    select.dispatchEvent(event);
                    console.log('Successfully selected option with value ' + valueId + ' for ' + fieldName + ' after delay');
                }
            }, 500);
        }
    } else {
        console.warn('Select field with name "' + fieldName + '" not found in the DOM');
    }
}

// Helper function to show the content field for a specific content type
function showContentField(contentType) {
    // Normalize content type for field ID
    var fieldId = contentType.toLowerCase() + '-content';
    console.log('Showing content field for: ' + contentType + ' (ID: ' + fieldId + ')');
    
    // Hide all content fields first
    var allContentFields = document.querySelectorAll('.content-type-field');
    for (var i = 0; i < allContentFields.length; i++) {
        var field = allContentFields[i];
        field.style.display = 'none';
        field.style.visibility = 'hidden';
        field.style.opacity = '0';
        field.classList.remove('active');
    }
    
    // Show the selected content field
    var selectedField = document.getElementById(fieldId);
    if (selectedField) {
        console.log('Found field with ID ' + fieldId + ', making it visible');
        selectedField.style.display = 'block';
        selectedField.style.visibility = 'visible';
        selectedField.style.opacity = '1';
        selectedField.classList.add('active');
        
        // Special handling for Text content
        if (contentType.toLowerCase() === 'text') {
            var textContent = document.getElementById('text-content');
            if (textContent) {
                console.log('Making text content editor visible');
                // Make TinyMCE visible if present
                var tinyMceEditor = textContent.querySelector('.tox-tinymce');
                if (tinyMceEditor) {
                    tinyMceEditor.style.display = 'block';
                    tinyMceEditor.style.visibility = 'visible';
                    tinyMceEditor.style.opacity = '1';
                    
                    // Make edit area visible
                    var editArea = tinyMceEditor.querySelector('.tox-edit-area');
                    if (editArea) {
                        editArea.style.display = 'block';
                        editArea.style.visibility = 'visible';
                        editArea.style.opacity = '1';
                    }
                }
            }
        }
    } else {
        console.warn('Content field with ID ' + fieldId + ' not found');
    }
}

// Helper function to handle text content
function handleTextContent(topic) {
    console.log('Handling text content');
    
    // Function to decode HTML entities
    function decodeHtmlEntities(str) {
        var tempDiv = document.createElement('div');
        tempDiv.innerHTML = str;
        return tempDiv.textContent || tempDiv.innerText || '';
    }
    
    // Set text content field
    var textContentField = document.querySelector('textarea[name="text_content"]');
    if (textContentField) {
        console.log('Setting text content');
        textContentField.value = topic.text_content || '';
        
        // If TinyMCE is initialized
        if (typeof tinymce !== 'undefined' && tinymce.editors) {
            console.log('TinyMCE found, setting editor content');
            // Find the TinyMCE instance for this field
            for (var i = 0; i < tinymce.editors.length; i++) {
                var editor = tinymce.editors[i];
                if (editor.id === textContentField.id) {
                    var htmlContent = '';
                    
                    // Handle different formats of text_content
                    if (typeof topic.text_content === 'string') {
                        // Check if it's JSON format first
                        if (topic.text_content.trim().indexOf('{') === 0 && 
                            topic.text_content.trim().lastIndexOf('}') === topic.text_content.trim().length - 1) {
                            try {
                                var content = JSON.parse(topic.text_content);
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
                    } else {
                        // Fallback to original content
                        htmlContent = topic.text_content || '';
                    }
                    
                    // Set content in TinyMCE
                    console.log('Setting TinyMCE content:', htmlContent.substring(0, 100) + '...');
                    editor.setContent(htmlContent);
                    break;
                }
            }
        } else {
            console.log('TinyMCE not found, using plain textarea');
        }
    } else {
        console.warn('Text content textarea not found');
    }
}

// Helper function to extract filename from URL
function getFilenameFromUrl(url) {
    if (!url) return '';
    var parts = url.split('/');
    return parts[parts.length - 1];
}

// Function to delete a topic
function deleteTopic(topicId) {
    if (!confirm('Are you sure you want to delete this topic? This action cannot be undone.')) {
        return;
    }
    
    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    
    fetch('/courses/topic/' + topicId + '/delete/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(function(response) {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(function(data) {
        if (data.success) {
            showNotification('Topic deleted successfully', 'success');
            
            // If we're on the course edit page, reload to update the topic list
            if (window.location.href.indexOf('/courses/') !== -1 && 
                window.location.href.indexOf('/edit/') !== -1) {
                setTimeout(function() {
                    window.location.reload();
                }, 1000);
            } 
            // If we're on the topic page, go back to the course
            else if (window.location.href.indexOf('/topic/') !== -1) {
                var courseId = document.querySelector('[name=course_id]');
                if (courseId) {
                    setTimeout(function() {
                        window.location.href = '/courses/' + courseId.value + '/edit/';
                    }, 1000);
                } else {
                    setTimeout(function() {
                        window.location.href = '/courses/';
                    }, 1000);
                }
            }
        } else {
            showNotification(data.error || 'Error deleting topic', 'error');
        }
    })
    .catch(function(error) {
        console.error('Error:', error);
        showNotification('Error deleting topic', 'error');
    });
}

// Function to view a topic
function viewTopic(topicId) {
    // Redirect to the topic view page
    window.location.href = '/courses/topic/' + topicId + '/view/?manual=True';
}

// Function to move a topic up or down
function moveTopic(topicId, direction) {
    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    var courseId = document.querySelector('[name=course_id]').value;
    
    fetch('/courses/api/topics/reorder/', {
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
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.success) {
            // Reload the page to show updated order
            window.location.reload();
        } else {
            showNotification(data.error || 'Error reordering topic', 'error');
        }
    })
    .catch(function(error) {
        console.error('Error:', error);
        showNotification('Error reordering topic', 'error');
    });
}

// Function to show notification
function showNotification(message, type) {
    if (!type) type = 'info';
    
    // Create notification element
    var notification = document.createElement('div');
    notification.className = 'fixed bottom-4 right-4 p-4 rounded shadow-lg z-50 max-w-md notification-' + type;
    
    // Set background color based on type
    if (type === 'success') {
        notification.style.backgroundColor = '#d1fae5';
        notification.style.borderLeft = '4px solid #10b981';
        notification.style.color = '#065f46';
    } else if (type === 'error') {
        notification.style.backgroundColor = '#fee2e2';
        notification.style.borderLeft = '4px solid #ef4444';
        notification.style.color = '#7f1d1d';
    } else if (type === 'warning') {
        notification.style.backgroundColor = '#fef3c7';
        notification.style.borderLeft = '4px solid #f59e0b';
        notification.style.color = '#78350f';
    } else {
        notification.style.backgroundColor = '#e0f2fe';
        notification.style.borderLeft = '4px solid #0ea5e9';
        notification.style.color = '#0c4a6e';
    }
    
    notification.innerHTML = message + '<button class="ml-4 text-sm opacity-75" onclick="this.parentNode.remove()">×</button>';
    document.body.appendChild(notification);
    
    // Remove after 5 seconds
    setTimeout(function() {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Function to close edit modal
function closeEditModal() {
    var modal = document.getElementById('edit-topic-modal');
    if (modal) modal.classList.add('hidden');
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
window.editTopic = editTopic;
window.viewTopic = viewTopic;
window.moveTopic = moveTopic;

// Add event listeners when the document is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners to move topic buttons
    var moveTopicButtons = document.querySelectorAll('.move-topic-btn');
    for (var i = 0; i < moveTopicButtons.length; i++) {
        moveTopicButtons[i].addEventListener('click', function() {
            var topicItem = this.closest('.topic-item');
            var topicId = topicItem.dataset.id;
            showMoveTopicModal(topicId);
        });
    }
    
    // Handle move topic form submission
    var moveTopicForm = document.getElementById('moveTopicForm');
    if (moveTopicForm) {
        moveTopicForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            var topicId = document.getElementById('topic_id_to_move').value;
            var targetSectionId = document.getElementById('target_section').value;
            var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
            
            // Send AJAX request to move the topic
            fetch('/courses/move_topic_to_section/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    topic_id: topicId,
                    section_id: targetSectionId
                })
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success) {
                    showNotification('Topic moved successfully', 'success');
                    // Hide the modal
                    hideMoveTopicModal();
                    // Reload the page after a short delay
                    setTimeout(function() {
                        window.location.reload();
                    }, 1000);
                } else {
                    showNotification(data.error || 'Error moving topic', 'error');
                }
            })
            .catch(function(error) {
                console.error('Error:', error);
                showNotification('Error moving topic', 'error');
            });
        });
    }
    
    // Add event listeners to section toggles
    var sectionToggles = document.querySelectorAll('.section-toggle');
    for (var j = 0; j < sectionToggles.length; j++) {
        sectionToggles[j].addEventListener('click', function() {
            var section = this.closest('.section-item');
            var topicsList = section.querySelector('.section-topics');
            var toggleIcon = this.querySelector('svg');
            
            if (topicsList) {
                if (topicsList.classList.contains('hidden')) {
                    topicsList.classList.remove('hidden');
                    if (toggleIcon) toggleIcon.classList.add('rotate-90');
                } else {
                    topicsList.classList.add('hidden');
                    if (toggleIcon) toggleIcon.classList.remove('rotate-90');
                }
            }
        });
    }
    
    // Handle automatic topic completion for content types that can be auto-completed
    autoMarkTopicAsComplete();
});

// Function to automatically mark a topic as complete based on viewing it
function autoMarkTopicAsComplete() {
    // Check if we're on a topic view page
    if (window.location.pathname.indexOf('/topic/') === -1 || 
        window.location.pathname.indexOf('/view/') === -1) {
        return;
    }
    
    // Get topic ID from URL path
    var pathParts = window.location.pathname.split('/');
    var topicIdIndex = pathParts.indexOf('topic') + 1;
    
    if (topicIdIndex < pathParts.length) {
        var topicId = pathParts[topicIdIndex];
        if (!topicId || isNaN(parseInt(topicId))) return;
        
        // Get topic type
        var topicTypeElement = document.querySelector('.topic-type');
        if (!topicTypeElement) return;
        
        var topicType = topicTypeElement.textContent.trim();
        
        // Auto-complete for certain content types if we haven't already
        if (['Text', 'Web', 'Video', 'Audio', 'Document', 'EmbedVideo', 'Assignment', 'SCORM', 'Quiz', 'Conference', 'Discussion'].indexOf(topicType) !== -1) {
            // Check if we've already marked this as complete
            if (localStorage.getItem('topic_' + topicId + '_completed') === 'true') {
                console.log('Topic already marked as complete');
                updateCompletionUI(topicId);
                return;
            }
            
            // Set a timeout to mark as complete after 10 seconds of viewing
            var autoCompleteTimeout = setTimeout(function() {
                console.log('Auto-marking topic as complete after 10 seconds');
                
                // Get course ID 
                var courseIdElement = document.querySelector('[data-course-id]');
                if (!courseIdElement) return;
                
                var courseId = courseIdElement.getAttribute('data-course-id');
                if (!courseId) return;
                
                // Mark as complete via AJAX
                var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
                
                fetch('/courses/topic/' + topicId + '/complete/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        course_id: courseId,
                        topic_id: topicId,
                        auto_complete: true
                    })
                })
                .then(function(response) { return response.json(); })
                .then(function(data) {
                    if (data.success) {
                        console.log('Topic marked as complete successfully');
                        localStorage.setItem('topic_' + topicId + '_completed', 'true');
                        updateCompletionUI(topicId);
                        
                        // Show completion toast
                        var topicTitle = document.querySelector('.topic-title');
                        if (topicTitle) {
                            showCompletionToast(topicTitle.textContent.trim());
                        } else {
                            showCompletionToast('Topic');
                        }
                    } else {
                        console.error('Error marking topic as complete:', data.error);
                    }
                })
                .catch(function(error) {
                    console.error('Error marking topic as complete:', error);
                });
            }, 10000);
            
            // Clear the timeout if the user leaves the page
            window.addEventListener('beforeunload', function() {
                clearTimeout(autoCompleteTimeout);
            });
        } else if (topicType === 'Text') {
            // For text content, add a manual complete button at the bottom
            addManualCompleteButtonForTextTopic();
        }
    }
}

// Function to update UI elements for completed topics
function updateCompletionUI(topicId) {
    // Update sidebar item if exists
    var sidebarItem = document.querySelector('.topic-item[data-topic-id="' + topicId + '"]');
    if (sidebarItem) {
        sidebarItem.classList.add('topic-completed');
        
        // Add a completion icon if not already present
        if (!sidebarItem.querySelector('.completion-icon')) {
            var icon = document.createElement('span');
            icon.className = 'completion-icon ml-2 text-green-500';
            icon.innerHTML = '✓';
            sidebarItem.querySelector('a').appendChild(icon);
        }
    }
    
    // Update completion button if exists
    var completeButton = document.querySelector('.topic-complete-button');
    if (completeButton) {
        completeButton.textContent = 'Completed';
        completeButton.disabled = true;
        completeButton.className = 'topic-complete-button px-4 py-2 bg-green-100 text-green-800 rounded-md cursor-not-allowed';
    }
}

// Function to show a toast notification for completion
function showCompletionToast(topicTitle) {
    var toast = document.createElement('div');
    toast.className = 'fixed bottom-4 left-4 bg-green-100 border-l-4 border-green-500 text-green-700 p-4 rounded shadow-lg z-50 max-w-md toast-enter';
    toast.innerHTML = `
        <div class="flex items-center">
            <div class="mr-3">
                <svg class="h-6 w-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
            </div>
            <div>
                <p class="font-bold">Topic Completed</p>
                <p>${topicTitle} has been marked as complete.</p>
            </div>
            <button class="ml-4 text-green-700 hover:text-green-900" onclick="this.parentNode.parentNode.remove()">
                <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"></path>
                </svg>
            </button>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    // Remove after 5 seconds
    setTimeout(function() {
        if (toast.parentNode) {
            toast.classList.add('toast-leave');
            setTimeout(function() {
                if (toast.parentNode) {
                    toast.remove();
                }
            }, 300);
        }
    }, 5000);
}

// Function to add a manual complete button for text content topics
function addManualCompleteButtonForTextTopic() {
    // Check if we already have a completion button
    if (document.querySelector('.topic-complete-button')) return;
    
    // Get topic content container
    var contentContainer = document.querySelector('.topic-content');
    if (!contentContainer) return;
    
    // Get topic ID from URL path
    var pathParts = window.location.pathname.split('/');
    var topicIdIndex = pathParts.indexOf('topic') + 1;
    
    if (topicIdIndex < pathParts.length) {
        var topicId = pathParts[topicIdIndex];
        if (!topicId || isNaN(parseInt(topicId))) return;
        
        // Create button container
        var buttonContainer = document.createElement('div');
        buttonContainer.className = 'text-center mt-8';
        
        // Create button
        var completeButton = document.createElement('button');
        completeButton.className = 'topic-complete-button px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition';
        completeButton.textContent = 'Mark as Complete';
        
        // Check if already completed
        if (localStorage.getItem('topic_' + topicId + '_completed') === 'true') {
            completeButton.textContent = 'Completed';
            completeButton.disabled = true;
            completeButton.className = 'topic-complete-button px-4 py-2 bg-green-100 text-green-800 rounded-md cursor-not-allowed';
        }
        
        // Add click handler
        completeButton.addEventListener('click', function() {
            // Get course ID
            var courseIdElement = document.querySelector('[data-course-id]');
            if (!courseIdElement) return;
            
            var courseId = courseIdElement.getAttribute('data-course-id');
            if (!courseId) return;
            
            syncTopicCompletion(topicId, courseId);
        });
        
        buttonContainer.appendChild(completeButton);
        contentContainer.appendChild(buttonContainer);
    }
}

// Function to synchronize topic completion state
function syncTopicCompletion(topicId, courseId) {
    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    
    fetch('/courses/topic/' + topicId + '/complete/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({
            course_id: courseId,
            topic_id: topicId,
            manual_complete: true
        })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.success) {
            console.log('Topic marked as complete successfully');
            localStorage.setItem('topic_' + topicId + '_completed', 'true');
            updateCompletionUI(topicId);
            
            // Show completion toast
            var topicTitle = document.querySelector('.topic-title');
            if (topicTitle) {
                showCompletionToast(topicTitle.textContent.trim());
            } else {
                showCompletionToast('Topic');
            }
        } else {
            console.error('Error marking topic as complete:', data.error);
            showNotification(data.error || 'Error marking topic as complete', 'error');
        }
    })
    .catch(function(error) {
        console.error('Error marking topic as complete:', error);
        showNotification('Error marking topic as complete', 'error');
    });
}

// Hook into existing mark complete functionality
document.addEventListener('DOMContentLoaded', function() {
    // Get course ID from the page
    var courseId = null;
    var courseElement = document.querySelector('[data-course-id]');
    if (courseElement) {
        courseId = courseElement.getAttribute('data-course-id');
    }
    
    // Intercept the mark complete form submission
    var completeForms = document.querySelectorAll('form[action*="mark_topic_complete"]');
    for (var i = 0; i < completeForms.length; i++) {
        completeForms[i].addEventListener('submit', function(e) {
            // Allow normal form submission to proceed, but also sync the completion
            var topicIdMatch = this.action.match(/\/topic\/(\d+)\/complete/);
            if (topicIdMatch && topicIdMatch[1] && courseId) {
                var topicId = topicIdMatch[1];
                // Call after a small delay to ensure the server-side operation completes
                setTimeout(function() { 
                    syncTopicCompletion(topicId, courseId);
                }, 500);
            }
        });
    }
    
    // Check for completions from other pages on page load
    var currentTopicElement = document.querySelector('.topic-item.active');
    if (currentTopicElement) {
        var topicId = currentTopicElement.getAttribute('data-topic-id');
        if (topicId && localStorage.getItem('topic_' + topicId + '_completed') === 'true') {
            updateCompletionUI(topicId);
        }
    }
}); 