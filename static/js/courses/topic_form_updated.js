document.addEventListener('DOMContentLoaded', function() {
    console.log('topic_form_updated.js loaded - VERSION 1.8 (Updated with field visibility requirements)');
    console.log('Current URL:', window.location.href);
    
    // Global error handler
    window.addEventListener('error', function(event) {
        console.log('Global error caught:', event.error ? event.error.message : 'Unknown error');
        // Prevent the error from completely breaking the page functionality
        event.preventDefault();
        return true;
    });
    
    // Safe method to access properties with null/undefined checking
    function safelyAccessProperty(obj, path) {
        if (!obj) return undefined;
        
        var properties = path.split('.');
        var current = obj;
        
        for (var i = 0; i < properties.length; i++) {
            var prop = properties[i];
            if (current === null || current === undefined) {
                return undefined;
            }
            current = current[prop];
        }
        
        return current;
    }
    
    // Get all content type radio buttons
    var contentTypeRadios = document.querySelectorAll('input[name="content_type"]');
    var contentFields = document.querySelectorAll('.content-type-field');
    
    console.log('DOM loaded. Checking for text content type selection.');
    
    // Check if text content type is selected on page load
    var textRadioSelected = document.querySelector('input[name="content_type"][value="Text"]:checked') || 
                           document.querySelector('input[name="content_type"][value="text"]:checked');
    
    if (textRadioSelected) {
        console.log('Text content type is selected on page load. Will attempt to show content.');
        // Try multiple times with increasing delays to ensure it works
        setTimeout(forceTextContentVisibility, 100);
        setTimeout(forceTextContentVisibility, 500);
        setTimeout(forceTextContentVisibility, 1000);
        setTimeout(forceTextContentVisibility, 2000);
    }
    
    // Variables to store topic form values when creating a section
    var topicTitleValue = '';
    var topicDescriptionValue = '';
    
    // Enhanced function to force text content field visibility
    function forceTextContentVisibility() {
        try {
            var textContent = document.getElementById('text-content');
            
            if (textContent) {
                console.log('Forcing text content field visibility');
                
                // Explicitly set inline styles to override any CSS rules
                textContent.style.display = 'block';
                textContent.style.visibility = 'visible';
                textContent.style.opacity = '1';
                textContent.style.height = 'auto';
                textContent.style.minHeight = '500px';
                textContent.style.overflow = 'visible';
                textContent.classList.add('active');
                
                // Make sure TinyMCE is visible
                var tinymceEditor = textContent.querySelector('.tox-tinymce');
                if (tinymceEditor) {
                    tinymceEditor.style.display = 'block';
                    tinymceEditor.style.visibility = 'visible';
                    tinymceEditor.style.opacity = '1';
                    tinymceEditor.style.height = 'auto';
                    tinymceEditor.style.minHeight = '450px';
                    
                    // Ensure edit area is visible
                    var editArea = tinymceEditor.querySelector('.tox-edit-area');
                    if (editArea) {
                        editArea.style.display = 'block';
                        editArea.style.visibility = 'visible';
                        editArea.style.opacity = '1';
                        editArea.style.height = 'auto';
                        editArea.style.minHeight = '200px';
                    }
                    
                    // Ensure iframe is visible
                    var iframe = tinymceEditor.querySelector('iframe');
                    if (iframe) {
                        iframe.style.display = 'block';
                        iframe.style.visibility = 'visible';
                        iframe.style.opacity = '1';
                        iframe.style.height = '400px';
                        iframe.style.minHeight = '350px';
                    }
                    
                    // Force toolbar visibility
                    var toolbar = tinymceEditor.querySelector('.tox-toolbar__primary');
                    if (toolbar) {
                        toolbar.style.display = 'flex';
                        toolbar.style.visibility = 'visible';
                        toolbar.style.opacity = '1';
                    }
                    
                    // Force toolbar groups visibility
                    var toolbarGroups = tinymceEditor.querySelectorAll('.tox-toolbar__group');
                    if (toolbarGroups && toolbarGroups.length > 0) {
                        for (var i = 0; i < toolbarGroups.length; i++) {
                            var group = toolbarGroups[i];
                            group.style.display = 'flex';
                            group.style.visibility = 'visible';
                            group.style.opacity = '1';
                        }
                    }
                    
                    // Force button visibility
                    var buttons = tinymceEditor.querySelectorAll('.tox-tbtn');
                    if (buttons && buttons.length > 0) {
                        for (var j = 0; j < buttons.length; j++) {
                            var btn = buttons[j];
                            btn.style.display = 'flex';
                            btn.style.visibility = 'visible';
                            btn.style.opacity = '1';
                        }
                    }
                    
                    // Hide any visible raw HTML content
                    var formGroup = textContent.querySelector('.form-group');
                    if (formGroup) {
                        var childNodes = Array.prototype.slice.call(formGroup.childNodes);
                        for (var k = 0; k < childNodes.length; k++) {
                            var node = childNodes[k];
                            if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
                                node.textContent = '';
                            } else if (node.nodeType === Node.ELEMENT_NODE && 
                                      !node.classList.contains('tox-tinymce') && 
                                      node.tagName !== 'LABEL' && 
                                      !node.matches('textarea[id^="id_text_content"]')) {
                                // Hide any non-editor, non-label elements
                                node.style.display = 'none';
                            }
                        }
                    }
                    
                    // Trigger TinyMCE to resize and refresh
                    if (typeof tinymce !== 'undefined' && tinymce.editors) {
                        var editors = tinymce.editors;
                        for (var l = 0; l < editors.length; l++) {
                            if (editors[l].id.includes('text_content')) {
                                editors[l].fire('ResizeEditor');
                                break;
                            }
                        }
                    }
                } else {
                    console.log('TinyMCE editor not found, reinitializing...');
                    
                    // If TinyMCE editor is not found, try to reinitialize it
                    if (typeof tinymce !== 'undefined') {
                        var textareas = textContent.querySelectorAll('textarea');
                        if (textareas && textareas.length > 0) {
                            tinymce.init({
                                selector: '#' + textareas[0].id,
                                height: 450,
                                menubar: 'edit view insert format tools table',
                                skin: 'oxide',
                                plugins: 'advlist autolink link image lists charmap preview anchor searchreplace visualblocks code fullscreen insertdatetime media table wordcount aiwriter',
                                toolbar: 'formatselect bold italic underline strikethrough | forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat | link image media table | code fullscreen aiwriter',
                                toolbar_mode: 'wrap',
                                toolbar_sticky: true,
                                toolbar_location: 'top',
                                branding: false,
                                promotion: false,
                                statusbar: false,
                                resize: 'both',
                                elementpath: true
                            });
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error in forceTextContentVisibility:', error);
        }
    }
    
    // Function to show/hide content fields
    function toggleContentFields(selectedType) {
        try {
            console.log('=== toggleContentFields called ===');
            console.log('Original selectedType:', selectedType);
            
            // Normalize selected type for consistency
            var normalizedType = selectedType.toLowerCase();
            console.log('Normalized type:', normalizedType);
            
            // Define content types that should hide the Instructions field
            var hideInstructionsTypes = ['video', 'document', 'text', 'audio', 'web', 'embedvideo', 'scorm', 'quiz', 'assignment', 'conference', 'discussion'];
            
            console.log('hideInstructionsTypes:', hideInstructionsTypes);
            console.log('Should hide instructions?', hideInstructionsTypes.indexOf(normalizedType) !== -1);
            
            // Handle Description field visibility - always show description field
            var descriptionField = document.querySelector('label[for*="description"]');
            if (descriptionField) {
                var descriptionDiv = descriptionField.closest('div');
                if (descriptionDiv) {
                    descriptionDiv.style.display = 'block';
                    console.log('Showing Description field for content type:', normalizedType);
                }
            }
            
            // Handle Instructions field visibility
            var instructionsField = document.querySelector('label[for*="instructions"]') || 
                                   document.querySelector('label[for="id_instructions"]');
            if (instructionsField) {
                var instructionsDiv = instructionsField.closest('div');
                if (instructionsDiv) {
                    if (hideInstructionsTypes.indexOf(normalizedType) !== -1) {
                        // Hide instructions field
                        instructionsDiv.style.display = 'none';
                        console.log('Hiding Instructions field for content type:', normalizedType);
                    } else {
                        instructionsDiv.style.display = 'block';
                        console.log('Showing Instructions field for content type:', normalizedType);
                    }
                }
            }
            
            // Additional fallback: Force hide instructions elements if needed
            if (hideInstructionsTypes.indexOf(normalizedType) !== -1) {
                var allInstructionsElements = document.querySelectorAll('[id*="instructions"], [name*="instructions"], [for*="instructions"]');
                allInstructionsElements.forEach(function(element) {
                    if (element.tagName === 'LABEL' || element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
                        var parentDiv = element.closest('div');
                        if (parentDiv) {
                            parentDiv.style.display = 'none';
                        }
                    }
                });
                console.log('FALLBACK: Hiding instructions elements for:', normalizedType);
            }
            
            // Special case for Assignment - always force display
            if (selectedType && normalizedType === 'assignment') {
                console.log('TOGGLE: Special handling for Assignment content type');
                var assignmentField = document.getElementById('assignment-content');
                if (assignmentField) {
                    // Force visibility with !important
                    assignmentField.setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important;');
                    assignmentField.classList.add('active');
                    
                    // Also make select visible
                    var assignmentSelect = assignmentField.querySelector('select[name="assignment"]');
                    if (assignmentSelect) {
                        assignmentSelect.setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important;');
                        
                        // Try to select option based on hidden field
                        var assignmentIdField = document.querySelector('input[name="assignment_id"]');
                        if (assignmentIdField && assignmentIdField.value) {
                            var option = assignmentSelect.querySelector('option[value="' + assignmentIdField.value + '"]');
                            if (option) {
                                option.selected = true;
                                console.log('TOGGLE: Selected assignment option:', option.textContent);
                            }
                        }
                    }
                    
                    return; // Skip the rest of the function
                }
            }
            
            console.log('Toggling content field for type:', selectedType, 'normalized to:', normalizedType);
            
            // Hide all content fields first
            if (contentFields && contentFields.length > 0) {
                for (var i = 0; i < contentFields.length; i++) {
                    var field = contentFields[i];
                    field.classList.remove('active');
                    
                    // Explicitly hide fields with inline styles when switching away
                    field.style.display = 'none';
                    field.style.visibility = 'hidden';
                    field.style.opacity = '0';
                }
            }
            
            // Determine the correct field ID based on normalized type
            var fieldId = normalizedType + '-content';
            console.log('Looking for field with ID:', fieldId);
            
            // Show only the selected content field
            var selectedField = document.getElementById(fieldId);
            if (selectedField) {
                console.log('Found field, making it active');
                selectedField.classList.add('active');
                selectedField.style.display = 'block';
                selectedField.style.visibility = 'visible';
                selectedField.style.opacity = '1';
                
                // Special handling for text content with TinyMCE editor
                if (fieldId === 'text-content') {
                    console.log('Text content selected, using enhanced visibility function');
                    // Use our enhanced function to ensure TinyMCE is fully visible
                    forceTextContentVisibility();
                }
            } else {
                console.warn('No content field found with ID:', fieldId);
            }
        } catch (error) {
            console.error('Error in toggleContentFields:', error);
        }
    }
    
    // Add event listeners to all content type radio buttons
    if (contentTypeRadios && contentTypeRadios.length > 0) {
        for (var i = 0; i < contentTypeRadios.length; i++) {
            var radio = contentTypeRadios[i];
            radio.addEventListener('change', function() {
                if (this.checked) {
                    console.log('Content type changed to:', this.value);
                    
                    // First clear any auto-filled content for the new content type
                    forceClearHiddenFields();
                    
                    // Then apply field visibility rules
                    toggleContentFields(this.value);
                }
            });
        }
    }
    
    // Function to force clear hidden fields
    function forceClearHiddenFields() {
        console.log('Force clearing any hidden description/instruction fields to prevent auto-fill');
        
        // Always clear description and instruction fields for content types that shouldn't have them
        var hideBothTypes = ['text', 'quiz', 'assignment', 'conference', 'discussion'];
        var showDescriptionOnlyTypes = ['video', 'audio', 'document', 'web', 'embedvideo', 'scorm'];
        
        // Get current selected content type
        var selectedContentType = document.querySelector('input[name="content_type"]:checked');
        if (selectedContentType) {
            var normalizedType = selectedContentType.value.toLowerCase();
            
            // If it's a content type that should hide fields, clear them
            if (hideBothTypes.indexOf(normalizedType) !== -1) {
                // Clear description field
                var descriptionInputs = document.querySelectorAll('textarea[name*="description"], input[name*="description"]');
                descriptionInputs.forEach(function(input) {
                    input.value = '';
                });
                
                // Clear instruction fields  
                var instructionInputs = document.querySelectorAll('textarea[name*="instructions"], input[name*="instructions"]');
                instructionInputs.forEach(function(input) {
                    input.value = '';
                });
                
                console.log('Cleared description and instruction fields for:', normalizedType);
            } else if (showDescriptionOnlyTypes.indexOf(normalizedType) !== -1) {
                // Clear only instruction fields for description-only types
                var instructionInputs = document.querySelectorAll('textarea[name*="instructions"], input[name*="instructions"]');
                instructionInputs.forEach(function(input) {
                    input.value = '';
                });
                
                console.log('Cleared instruction fields for:', normalizedType);
            }
        }
    }
    
    // Check if there is a pre-selected content type
    var selectedContentType = document.querySelector('input[name="content_type"]:checked');
    if (selectedContentType) {
        console.log('Content type already selected:', selectedContentType.value);
        console.log('Calling toggleContentFields with:', selectedContentType.value);
        
        // First clear any auto-filled content
        forceClearHiddenFields();
        
        // Then apply field visibility rules
        toggleContentFields(selectedContentType.value);
    } else {
        console.log('No content type pre-selected');
        // Check all content type radio buttons
        var allRadios = document.querySelectorAll('input[name="content_type"]');
        console.log('Found content type radios:', allRadios.length);
        allRadios.forEach(function(radio, index) {
            console.log('Radio', index + ':', radio.value, 'checked:', radio.checked);
        });
    }
    
    // Function to validate URL
    function isValidUrl(url) {
        try {
            new URL(url);
            return true;
        } catch (e) {
            return false;
        }
    }
    
    // Function to display field error
    function displayFieldError(fieldName, errorMessage) {
        var field = document.querySelector('[name="' + fieldName + '"]');
        if (field) {
            // Add error class to the field
            field.classList.add('border-red-500');
            
            // Create error message element if it doesn't exist
            var errorEl = field.parentNode.querySelector('.error-message');
            if (!errorEl) {
                errorEl = document.createElement('p');
                errorEl.className = 'text-red-500 text-sm mt-1 error-message';
                field.parentNode.appendChild(errorEl);
            }
            
            errorEl.textContent = errorMessage;
        }
    }
    
    // Function to display global error
    function displayGlobalError(errorMessage) {
        var formContainer = document.querySelector('form').parentNode;
        
        // Create error alert if it doesn't exist
        var errorAlert = formContainer.querySelector('.global-error');
        if (!errorAlert) {
            errorAlert = document.createElement('div');
            errorAlert.className = 'bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4 global-error';
            formContainer.insertBefore(errorAlert, formContainer.firstChild);
        }
        
        errorAlert.textContent = errorMessage;
    }
    
    // Check if we should update the topic section select field (for course edit page)
    var topicSectionField = document.getElementById('topic_section');
    var sectionIdField = document.querySelector('input[name="section"]');
    
    if (topicSectionField && sectionIdField && sectionIdField.value) {
        var sectionId = sectionIdField.value;
        var sectionOption = topicSectionField.querySelector('option[value="' + sectionId + '"]');
        
        if (sectionOption) {
            sectionOption.selected = true;
        }
    }
    
    // Handle topic form submission and validation
    var topicForm = document.getElementById('topicForm');
    if (topicForm) {
        console.log('Found topic form, setting up submission handler');
        
        topicForm.addEventListener('submit', function(event) {
            var isValid = true;
            var selectedContentType = document.querySelector('input[name="content_type"]:checked');
            
            if (!selectedContentType) {
                displayGlobalError('Please select a content type');
                isValid = false;
            } else {
                var contentType = selectedContentType.value;
                
                // Validate based on content type
                switch (contentType.toLowerCase()) {
                    case 'web':
                        var webUrl = document.querySelector('input[name="web_url"]').value;
                        if (!webUrl || !isValidUrl(webUrl)) {
                            displayFieldError('web_url', 'Please enter a valid URL (including http:// or https://)');
                            isValid = false;
                        }
                        break;
                    
                    case 'quiz':
                        var quizId = document.querySelector('select[name="quiz"]').value;
                        if (!quizId) {
                            displayFieldError('quiz', 'Please select a quiz');
                            isValid = false;
                        }
                        break;
                    
                    case 'assignment':
                        var assignmentId = document.querySelector('select[name="assignment"]').value;
                        if (!assignmentId) {
                            displayFieldError('assignment', 'Please select an assignment');
                            isValid = false;
                        }
                        break;
                    
                    // Add validation for other content types if needed
                }
            }
            
            if (!isValid) {
                event.preventDefault();
            }
        });
    }
    
    // Support for local storage to save form data
    if (topicForm) {
        // Get a unique key for this form
        var formKey = topicForm.getAttribute('data-form-id') || 'topic_form';
        
        // Save form data to localStorage when any input changes
        topicForm.addEventListener('input', function(event) {
            var formData = {};
            var formInputs = topicForm.querySelectorAll('input, select, textarea');
            
            for (var i = 0; i < formInputs.length; i++) {
                var input = formInputs[i];
                
                // Skip radio buttons that aren't checked
                if (input.type === 'radio' && !input.checked) continue;
                
                // Skip submit buttons
                if (input.type === 'submit') continue;
                
                // Store the values
                if (input.type === 'checkbox') {
                    formData[input.name] = input.checked;
                } else if (input.tagName === 'SELECT' && input.multiple) {
                    var selectedOptions = [];
                    for (var j = 0; j < input.options.length; j++) {
                        if (input.options[j].selected) {
                            selectedOptions.push(input.options[j].value);
                        }
                    }
                    formData[input.name] = selectedOptions;
                } else {
                    formData[input.name] = input.value;
                }
            }
            
            // Store the data
            localStorage.setItem(formKey, JSON.stringify(formData));
        });
        
        // Restore form data when the page loads
        window.addEventListener('load', function() {
            // Check if this is an edit operation (existing topic) vs create operation (new topic)
            var topicIdField = document.querySelector('input[name="topic_id"]');
            var isEditMode = topicIdField && topicIdField.value && topicIdField.value.trim() !== '';
            
            // Additional check - look for URL patterns that indicate create vs edit
            var currentPath = window.location.pathname;
            var isCreatePage = currentPath.includes('/create') || currentPath.includes('/add');
            
            // Only restore localStorage data for edit operations, not for new topic creation
            if (!isEditMode || isCreatePage) {
                console.log('Create mode detected (no topic_id or create URL) - not restoring localStorage data to ensure clean form');
                console.log('Topic ID field:', topicIdField ? topicIdField.value : 'not found');
                console.log('Current path:', currentPath);
                console.log('Is create page:', isCreatePage);
                
                // Clear any existing localStorage data for create operations to prevent confusion
                localStorage.removeItem(formKey);
                // Also clear any old entries with different formKey patterns
                var keysToRemove = [];
                for (var i = 0; i < localStorage.length; i++) {
                    var key = localStorage.key(i);
                    if (key && key.indexOf('topic') !== -1) {
                        keysToRemove.push(key);
                    }
                }
                for (var j = 0; j < keysToRemove.length; j++) {
                    localStorage.removeItem(keysToRemove[j]);
                }
                console.log('Cleared localStorage entries:', keysToRemove);
                return;
            }
            
            var savedData = localStorage.getItem(formKey);
            
            if (savedData) {
                try {
                    var formData = JSON.parse(savedData);
                    console.log('Edit mode detected - Form data restored from localStorage');
                    
                    // Apply the saved data to form fields
                    for (var fieldName in formData) {
                        if (formData.hasOwnProperty(fieldName)) {
                            var fieldValue = formData[fieldName];
                            var field = topicForm.querySelector('[name="' + fieldName + '"]');
                            
                            if (field) {
                                if (field.type === 'checkbox') {
                                    field.checked = fieldValue;
                                } else if (field.type === 'radio') {
                                    var radioField = topicForm.querySelector('[name="' + fieldName + '"][value="' + fieldValue + '"]');
                                    if (radioField) {
                                        radioField.checked = true;
                                        // Trigger change event to show/hide content fields
                                        var event = new Event('change');
                                        radioField.dispatchEvent(event);
                                    }
                                } else if (field.tagName === 'SELECT' && field.multiple && Array.isArray(fieldValue)) {
                                    for (var i = 0; i < field.options.length; i++) {
                                        field.options[i].selected = fieldValue.includes(field.options[i].value);
                                    }
                                } else {
                                    field.value = fieldValue;
                                }
                            }
                        }
                    }
                } catch (error) {
                    console.error('Error restoring form data:', error);
                }
            }
        });
        
        // Clear form data from localStorage when the form is successfully submitted
        topicForm.addEventListener('submit', function() {
            localStorage.removeItem(formKey);
        });
    }
    
    // Extra check when window is fully loaded
    window.addEventListener('load', function() {
        console.log('Window loaded - ensuring content types are properly displayed');
        
        // Handle content field visibility after load
        var selectedContentType = document.querySelector('input[name="content_type"]:checked');
        if (selectedContentType) {
            console.log('Content type selected on page load:', selectedContentType.value);
            toggleContentFields(selectedContentType.value);
        } else {
            console.log('No content type selected on page load');
        }
        
        // If this is an edit form for an existing topic, ensure content fields are visible
        var topicIdField = document.querySelector('input[name="topic_id"]');
        if (topicIdField && topicIdField.value) {
            console.log('This is an edit form for existing topic ID:', topicIdField.value);
            
            // Special check for assignment content
            var assignmentIdField = document.querySelector('input[name="assignment_id"]');
            if (assignmentIdField && assignmentIdField.value) {
                console.log('Found assignment ID:', assignmentIdField.value);
                
                var assignmentField = document.getElementById('assignment-content');
                if (assignmentField) {
                    assignmentField.style.display = 'block';
                    assignmentField.style.visibility = 'visible';
                    assignmentField.style.opacity = '1';
                    assignmentField.classList.add('active');
                    
                    // Set assignment select value
                    var assignmentSelect = document.querySelector('select[name="assignment"]');
                    if (assignmentSelect) {
                        var option = assignmentSelect.querySelector('option[value="' + assignmentIdField.value + '"]');
                        if (option) {
                            option.selected = true;
                        }
                    }
                }
            }
            
            // Special check for quiz content
            var quizIdField = document.querySelector('input[name="quiz_id"]');
            if (quizIdField && quizIdField.value) {
                console.log('Found quiz ID:', quizIdField.value);
                
                var quizField = document.getElementById('quiz-content');
                if (quizField) {
                    quizField.style.display = 'block';
                    quizField.style.visibility = 'visible';
                    quizField.style.opacity = '1';
                    quizField.classList.add('active');
                    
                    // Set quiz select value
                    var quizSelect = document.querySelector('select[name="quiz"]');
                    if (quizSelect) {
                        var option = quizSelect.querySelector('option[value="' + quizIdField.value + '"]');
                        if (option) {
                            option.selected = true;
                        }
                    }
                }
            }
        }
    });
});
