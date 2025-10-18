/**
 * Course Edit - Javascript functionality for the course edit page
 */

// Robust error handler to prevent JavaScript crashes
window.addEventListener('error', function(event) {
    if (event.error && event.error.message && event.error.message.includes('entries')) {
        event.preventDefault();
        return true;
    }
});

// Global cleanup tracking for course edit
window.CourseEditCleanup = {
    listeners: [],
    timeouts: [],
    intervals: [],
    
    addListener: function(element, event, handler) {
        element.addEventListener(event, handler);
        this.listeners.push({ element, event, handler });
    },
    
    addTimeout: function(callback, delay) {
        var timeoutId = setTimeout(callback, delay);
        this.timeouts.push(timeoutId);
        return timeoutId;
    },
    
    addInterval: function(callback, delay) {
        var intervalId = setInterval(callback, delay);
        this.intervals.push(intervalId);
        return intervalId;
    },
    
    cleanup: function() {
        // Remove all event listeners
        var self = this;
        this.listeners.forEach(function(listener) {
            var element = listener.element;
            var event = listener.event;
            var handler = listener.handler;
            element.removeEventListener(event, handler);
        });
        this.listeners = [];
        
        // Clear all timeouts
        this.timeouts.forEach(function(timeoutId) {
            clearTimeout(timeoutId);
        });
        this.timeouts = [];
        
        // Clear all intervals
        this.intervals.forEach(function(intervalId) {
            clearInterval(intervalId);
        });
        this.intervals = [];
        
        // Cleanup TinyMCE editors
        if (window.tinymce) {
            window.tinymce.remove();
        }
    }
};

// Course edit page functionality
document.addEventListener('DOMContentLoaded', function() {
    
    // Initialize file upload handlers
    initializeFileUploads();
    
    // Initialize existing image preview
    initializeExistingImagePreview();
    
    // Set up event listeners for modal buttons
    initializeModalButtons();

    // Add a small delay to ensure all elements are ready
    var initTimeout = window.CourseEditCleanup.addTimeout(function() {
        try {
            initializeTabButtons();
        } catch (error) {
        }
        
        try {
            // Initialize topic title truncation
            truncateTopicTitles();
        } catch (error) {
        }
        
        try {
            // Initialize form change detection
            initFormChangeDetection();
        } catch (error) {
        }
        
        try {
            // Initialize cancel button handler
            initializeCancelButton();
        } catch (error) {
        }
        
    }, 300);
    
    // Create global function to mark form as changed
    window.markFormAsChanged = function() {
        if (typeof formHasUnsavedChanges !== 'undefined') {
            formHasUnsavedChanges = true;
            
            // Create a simple notification if one doesn't exist
            if (typeof showUnsavedChangesNotification !== 'function') {
                // Create a fallback notification function
                window.showUnsavedChangesNotification = function() {
                    var notificationBanner = document.getElementById('unsaved-changes-notification');
                    if (notificationBanner) {
                        notificationBanner.classList.remove('hidden');
                        setTimeout(function() {
                            notificationBanner.classList.remove('-translate-y-full');
                        }, 10);
                    } else {
                        // Create a simple notification banner if it doesn't exist
                        var newBanner = document.createElement('div');
                        newBanner.id = 'unsaved-changes-notification';
                        newBanner.className = 'fixed top-0 left-0 right-0 bg-yellow-500 text-white text-center py-3 z-50 shadow-md';
                        // Use safe HTML setting to prevent XSS
                        if (window.SafeHTMLUtils) {
                            window.SafeHTMLUtils.setSafeInnerHTML(newBanner, '<div class="container mx-auto px-4"><strong>Unsaved Changes!</strong> Please update course before leaving this page.</div>');
                        } else {
                            newBanner.innerHTML = '<div class="container mx-auto px-4"><strong>Unsaved Changes!</strong> Please update course before leaving this page.</div>';
                        }
                        document.body.appendChild(newBanner);
                    }
                };
            }
            
            // Show the notification
            if (typeof showUnsavedChangesNotification === 'function') {
                showUnsavedChangesNotification();
            }
            return true;
        } else {
            // Set a global flag that can be checked later
            window.formHasUnsavedChanges = true;
            return false;
        }
    };
});

// Track if form has unsaved changes
var formHasUnsavedChanges = false;
var formInitialState = {};
var editorsInitialized = new Set(); // Track which editors have been initialized
var isFormSubmitting = false; // Track if form is currently being submitted

// Function to initialize cancel button handler
function initializeCancelButton() {
    var cancelButton = document.getElementById('cancel-edit-button');
    if (cancelButton) {
        cancelButton.addEventListener('click', function(e) {
            if (formHasUnsavedChanges) {
                // If there are unsaved changes, show confirmation dialog
                if (!confirm('You have unsaved changes. Are you sure you want to leave this page?')) {
                    // User cancelled, prevent navigation
                    e.preventDefault();
                    return false;
                }
                // User confirmed, allow navigation to proceed
            }
        });
    }
}

// Function to initialize form change detection
function initFormChangeDetection() {
    var form = document.getElementById('courseCreateForm');
    if (!form) {
        // Retry after a delay in case the form is loaded dynamically
        setTimeout(function() {
            var retryForm = document.getElementById('courseCreateForm');
            if (retryForm) {
                initFormChangeDetection();
            }
        }, 1000);
        return;
    }
    
    // Store initial form state
    saveFormInitialState(form);
    
    // Create notification banner
    var notificationBanner = document.createElement('div');
    notificationBanner.id = 'unsaved-changes-notification';
    notificationBanner.className = 'fixed top-0 left-0 right-0 bg-yellow-500 text-white text-center py-3 z-50 shadow-md hidden transform -translate-y-full transition-transform duration-300';
    if (window.SafeHTMLUtils) {
        window.SafeHTMLUtils.setSafeInnerHTML(notificationBanner, '<div class="container mx-auto px-4 flex items-center justify-between">' +
            '<span><strong>Unsaved Changes!</strong> Please update course before leaving this page or your changes will be lost.</span>' +
            '<button id="dismiss-notification" class="bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-1 rounded transition">Dismiss</button>' +
            '</div>');
    } else {
        // Create notification content safely
        const container = document.createElement('div');
        container.className = 'container mx-auto px-4 flex items-center justify-between';
        
        const span = document.createElement('span');
        span.innerHTML = '<strong>Unsaved Changes!</strong> Please update course before leaving this page or your changes will be lost.';
        
        const button = document.createElement('button');
        button.id = 'dismiss-notification';
        button.className = 'bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-1 rounded transition';
        button.textContent = 'Dismiss';
        
        container.appendChild(span);
        container.appendChild(button);
        notificationBanner.appendChild(container);
    }
    document.body.appendChild(notificationBanner);
    
    // Add dismiss button functionality
    var dismissButton = document.getElementById('dismiss-notification');
    if (dismissButton) {
        dismissButton.addEventListener('click', function() {
            hideUnsavedChangesNotification();
        });
    }
    
    // Function to save initial form state
    function saveFormInitialState(form) {
        if (!form) {
            return;
        }
        
        try {
            var formData = new FormData(form);
            formInitialState = {};
            
            // Process all form fields with robust error handling
            if (formData && typeof formData.entries === 'function') {
                var entries = formData.entries();
                var entry = entries.next();
                while (!entry.done) {
                    var key = entry.value[0];
                    var value = entry.value[1];
                    formInitialState[key] = value;
                    entry = entries.next();
                }
            }
        } catch (error) {
            formInitialState = {};
        }
        
        // Initialize TinyMCE editors properly
        initializeTinyMCEEditors();
        
        // Enhanced editor state saving with proper timing
        var saveEditorStates = function(attempt, maxAttempts) {
            attempt = attempt || 0;
            maxAttempts = maxAttempts || 3;
            
            // Quill editors removed - using TinyMCE only
            
            // CKEditor
            if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances) {
                try {
                    Object.keys(CKEDITOR.instances).forEach(editorId => {
                        var editor = CKEDITOR.instances[editorId];
                        if (editor && typeof editor.getData === 'function') {
                            formInitialState[editorId] = editor.getData();
                        }
                    });
                } catch (error) {
                }
            }
            
            // Summernote
            if (typeof jQuery !== 'undefined' && typeof jQuery.fn.summernote !== 'undefined') {
                try {
                    jQuery('.summernote').each(function() {
                        var editorId = this.id;
                        if (editorId) {
                            var content = jQuery(this).summernote('code');
                            formInitialState[editorId] = content;
                        }
                    });
                } catch (error) {
                }
            }
            
            // ContentEditable elements (fallback)
            var contentEditableElements = document.querySelectorAll('[contenteditable="true"]');
            contentEditableElements.forEach(element => {
                if (element.id && !formInitialState[element.id]) {
                    formInitialState[element.id] = element.innerHTML;
                }
            });
        };
        
        // Save non-TinyMCE editors
        saveEditorStates();
        
        // Retry after delays for late-initializing editors (excluding TinyMCE)
        setTimeout(function() { saveEditorStates(1); }, 2000);
        setTimeout(function() { saveEditorStates(2); }, 5000);
    }
    
    // Initialize TinyMCE editors with proper timing
    function initializeTinyMCEEditors() {
        if (typeof tinymce === 'undefined') {
            return;
        }
        
        
        // Function to handle editor initialization
        var handleEditorInit = function(editor) {
            if (!editor || !editor.id) {
                return;
            }
            
            // Prevent duplicate initialization
            if (editorsInitialized.has(editor.id)) {
                return;
            }
            
            editorsInitialized.add(editor.id);
            
            // Save initial state only when editor is fully ready
            if (typeof editor.getContent === 'function') {
                var initialContent = editor.getContent();
                formInitialState[editor.id] = initialContent;
            }
            
            // Set up change detection
            setupTinyMCEChangeDetection(editor);
        };
        
        // Handle already initialized editors
        if (tinymce.editors && tinymce.editors.length > 0) {
            tinymce.editors.forEach(editor => {
                if (editor.initialized) {
                    handleEditorInit(editor);
                } else {
                    // Wait for editor to be initialized
                    editor.on('init', () => handleEditorInit(editor));
                }
            });
        }
        
        // Listen for new editors being added
        if (typeof tinymce.on === 'function') {
            tinymce.on('AddEditor', function(e) {
                
                // Wait for editor to be fully initialized
                e.editor.on('init', function() {
                    handleEditorInit(e.editor);
                });
            });
        }
    }
    
    // Set up change detection for a TinyMCE editor
    function setupTinyMCEChangeDetection(editor) {
        if (!editor || typeof editor.on !== 'function') {
            return;
        }
        
        
        // Debounced change handler
        var changeTimeout = null;
        var handleEditorChange = function(eventType) {
            clearTimeout(changeTimeout);
            changeTimeout = setTimeout(function() {
                // Only trigger if content actually changed
                if (typeof editor.getContent === 'function') {
                    var currentContent = editor.getContent();
                    var initialContent = formInitialState[editor.id] || '';
                    
                    if (currentContent !== initialContent) {
                        updateFormChangedState();
                    } else {
                    }
                } else {
                    updateFormChangedState();
                }
            }, 100);
        };
        
        // Attach event handlers (only content changing events)
        editor.on('change', () => handleEditorChange('change'));
        editor.on('paste', () => handleEditorChange('paste'));
        editor.on('Undo', () => handleEditorChange('undo'));
        editor.on('Redo', () => handleEditorChange('redo'));
    }

    // Enhanced form change checking
    function checkFormChanged() {
        try {
            if (!form) {
                return false;
            }
            
            // Check regular form fields with robust error handling
            var formData = new FormData(form);
            if (formData && typeof formData.entries === 'function') {
                var entries = formData.entries();
                var entry = entries.next();
                while (!entry.done) {
                    var key = entry.value[0];
                    var value = entry.value[1];
                    var initialValue = formInitialState[key] || '';
                    if (value !== initialValue) {
                        return true;
                    }
                    entry = entries.next();
                }
            }
            
            // Enhanced editor content checking
            return checkEditorsChanged();
        } catch (error) {
            return false;
        }
    }
    
    // Enhanced editor change detection
    function checkEditorsChanged() {
        try {
            // Check TinyMCE editors
            if (typeof tinymce !== 'undefined' && tinymce.editors) {
                for (var editor of tinymce.editors) {
                    if (editor && typeof editor.getContent === 'function') {
                        var currentContent = editor.getContent();
                        var initialContent = formInitialState[editor.id] || '';
                        if (currentContent !== initialContent) {
                            return true;
                        }
                    }
                }
            }
            
            // Quill editors removed - using TinyMCE only
            
            // Check CKEditor
            if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances) {
                for (var editorId of Object.keys(CKEDITOR.instances)) {
                    var editor = CKEDITOR.instances[editorId];
                    if (editor && typeof editor.getData === 'function') {
                        var currentContent = editor.getData();
                        var initialContent = formInitialState[editorId] || '';
                        if (currentContent !== initialContent) {
                            return true;
                        }
                    }
                }
            }
            
            // Check Summernote
            if (typeof jQuery !== 'undefined' && typeof jQuery.fn.summernote !== 'undefined') {
                var summernoteEditors = jQuery('.summernote');
                for (var i = 0; i < summernoteEditors.length; i++) {
                    var element = summernoteEditors[i];
                    if (element.id) {
                        var currentContent = jQuery(element).summernote('code');
                        var initialContent = formInitialState[element.id] || '';
                        if (currentContent !== initialContent) {
                            return true;
                        }
                    }
                }
            }
            
            // Check ContentEditable elements (fallback)
            var contentEditableElements = document.querySelectorAll('[contenteditable="true"]');
            for (var element of contentEditableElements) {
                if (element.id) {
                    var currentContent = element.innerHTML;
                    var initialContent = formInitialState[element.id] || '';
                    if (currentContent !== initialContent) {
                        return true;
                    }
                }
            }
            
            return false;
        } catch (error) {
            return false;
        }
    }
    
    // Function to show notification
    function showUnsavedChangesNotification() {
        var notification = document.getElementById('unsaved-changes-notification');
        if (notification) {
            notification.classList.remove('hidden');
            setTimeout(function() {
                notification.classList.remove('-translate-y-full');
            }, 10);
        }
        enhanceSubmitButton();
    }
    
    // Function to hide notification
    function hideUnsavedChangesNotification() {
        var notification = document.getElementById('unsaved-changes-notification');
        if (notification) {
            notification.classList.add('-translate-y-full');
            setTimeout(function() {
                notification.classList.add('hidden');
            }, 300);
        }
    }
    
    // Function to update form changed state
    function updateFormChangedState() {
        var hasChanged = checkFormChanged();
        if (hasChanged && !formHasUnsavedChanges) {
            formHasUnsavedChanges = true;
            showUnsavedChangesNotification();
        } else if (!hasChanged && formHasUnsavedChanges) {
            formHasUnsavedChanges = false;
            hideUnsavedChangesNotification();
        }
    }
    
    // Function to enhance submit button appearance
    function enhanceSubmitButton() {
        var submitButton = document.getElementById('course-submit-button');
        if (submitButton) {
            // Change button color to green and add pulsing effect
            submitButton.classList.remove('bg-blue-600', 'hover:bg-blue-700', 'focus:ring-blue-600');
            submitButton.classList.add('bg-green-600', 'hover:bg-green-700', 'focus:ring-green-600', 'shadow-md');
            
            // Add a checkmark icon if not already present
            if (!submitButton.querySelector('svg')) {
                var checkmarkIcon = document.createElement('span');
                checkmarkIcon.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 inline-block mr-1" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                    </svg>
                `;
                submitButton.prepend(checkmarkIcon);
            }
        }
    }
    
    // Get all form elements for change detection
    var formElements = form.querySelectorAll('input, select, textarea');
    
    // Add change and input listeners to all form elements
    formElements.forEach(element => {
        // Special debugging for description field
        if (element.name === 'description' || element.id === 'id_description') {
        }
        
        // Listen for change events
        element.addEventListener('change', function() {
            if (element.name === 'description' || element.id === 'id_description') {
            }
            updateFormChangedState();
        });
        
        // For text inputs and textareas, also listen for input events
        if (element.tagName === 'INPUT' && (element.type === 'text' || element.type === 'number' || element.type === 'email' || element.type === 'hidden') || 
            element.tagName === 'TEXTAREA') {
            element.addEventListener('input', function() {
                if (element.name === 'description' || element.id === 'id_description') {
                }
                updateFormChangedState();
            });
            
            // Additional specific handler for description field
            if (element.name === 'description' || element.id === 'id_description') {
                element.addEventListener('keyup', function() {
                    updateFormChangedState();
                });
            }
        }
        
        // For select elements, ensure we catch all changes
        if (element.tagName === 'SELECT') {
            element.addEventListener('input', function() {
                updateFormChangedState();
            });
        }
    });
    
    // Additional specific detection for description field by multiple selectors
    var descriptionSelectors = [
        '#id_description',
        'textarea[name="description"]',
        '[name="description"]',
        'textarea.description',
        '.description textarea'
    ];
    
    // Fixed forEach to use function syntax for better compatibility
    descriptionSelectors.forEach(function(selector) {
        var element = document.querySelector(selector);
        if (element) {
            
            // Add comprehensive event listeners
            ['input', 'change', 'keyup', 'paste', 'blur'].forEach(function(eventType) {
                element.addEventListener(eventType, function() {
                    updateFormChangedState();
                });
            });
        }
    });
    
    // Enhanced debugging for the form state
    setTimeout(function() {
        
        var descriptionField = form.querySelector('#id_description') || form.querySelector('[name="description"]');
        if (descriptionField) {
            // Description field found
                id: descriptionField.id,
                name: descriptionField.name,
                tagName: descriptionField.tagName,
                type: descriptionField.type,
                value: (descriptionField.value && descriptionField.value.substring) ? 
                    descriptionField.value.substring(0, 50) + '...' : '...'
            });
        }
        
        // Check if form initial state was properly saved
        if (descriptionField && formInitialState[descriptionField.name]) {
        }
    }, 1000);
    
    // Listen for file input changes
    var fileInputs = form.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function() {
            formHasUnsavedChanges = true;
            showUnsavedChangesNotification();
        });
    });
    
    // For custom editors - contentEditable elements
    var contentEditableElements = document.querySelectorAll('[contenteditable="true"]');
    contentEditableElements.forEach(element => {
        element.addEventListener('input', function() {
            formHasUnsavedChanges = true;
            showUnsavedChangesNotification();
        });
    });
    
    // Set up other editors (non-TinyMCE) with proper timing
    function setupOtherEditors() {
        // Quill editor setup removed - using TinyMCE only
        
        // CKEditor setup
        if (typeof CKEDITOR !== 'undefined' && CKEDITOR.instances) {
            Object.keys(CKEDITOR.instances).forEach(editorId => {
                var editor = CKEDITOR.instances[editorId];
                
                // Listen for changes
                editor.on('change', function() {
                    updateFormChangedState();
                });
                
                editor.on('key', function() {
                    updateFormChangedState();
                });
            });
        }
        
        // Summernote setup
        if (typeof jQuery !== 'undefined' && typeof jQuery.fn.summernote !== 'undefined') {
            jQuery('.summernote').each(function() {
                var editorId = this.id;
                
                // Listen for changes
                jQuery(this).on('summernote.change', function() {
                    updateFormChangedState();
                });
            });
        }
    }
    
    // Initialize other editors with delay
    setTimeout(setupOtherEditors, 1000);
    setTimeout(setupOtherEditors, 3000);
    
    // Set up beforeunload event to warn before leaving page with unsaved changes
    window.CourseEditCleanup.addListener(window, 'beforeunload', function(e) {
        // Don't show confirmation if form is being submitted
        if (formHasUnsavedChanges && !isFormSubmitting) {
            // Standard way to show confirmation dialog when leaving page
            var message = 'You have unsaved changes. Are you sure you want to leave this page?';
            e.preventDefault(); // Required for some browsers
            e.returnValue = message; // Required for most browsers
            return message; // For older browsers
        }
    });
    
    // Also handle link clicks to prevent navigation if there are unsaved changes
    document.addEventListener('click', function(e) {
        // Check if the clicked element is a link (or inside a link)
        var link = e.target.closest('a');
        
        if (link && formHasUnsavedChanges) {
            // Don't intercept form submission links or same-page anchors
            var href = link.getAttribute('href');
            if (href && href !== '#' && !href.startsWith('#') && !link.hasAttribute('data-bypass-warning')) {
                // If this is an external link or page navigation
                if (confirm('You have unsaved changes. Are you sure you want to leave this page?')) {
                    // User confirmed, allow navigation to proceed
                    return true;
                } else {
                    // User cancelled, prevent navigation
                    e.preventDefault();
                    return false;
                }
            }
        }
    });
    
    // Reset flag when form is submitted
    form.addEventListener('submit', function() {
        isFormSubmitting = true;
        formHasUnsavedChanges = false;
        hideUnsavedChangesNotification();
    });
    
}

// Function to truncate topic titles to first 4 characters + ellipsis
function truncateTopicTitles() {
    // Get all topic titles
    var topicTitles = document.querySelectorAll('.topic-title');
    topicTitles.forEach(title => {
        // Get the full title from the title attribute
        var fullTitle = title.getAttribute('title');
        if (fullTitle && fullTitle.length > 4) {
            // Keep only first 4 characters + ellipsis
            title.textContent = fullTitle.substring(0, 4) + '...';
        }
    });
    
    // Handle section names - display full name without truncation
    var sectionNames = document.querySelectorAll('.section-name');
    sectionNames.forEach(name => {
        // Get the full name from the title attribute
        var fullName = name.getAttribute('title');
        if (!fullName || fullName.trim() === '') {
            // If section name is empty, use "Section"
            name.textContent = "Section";
        } else {
            // Show full section name without truncation
            name.textContent = fullName;
        }
    });
}

function initializeModalButtons() {
    // Add Category button
    var addCategoryBtn = document.getElementById('add-category-btn');
    if (addCategoryBtn) {
        addCategoryBtn.addEventListener('click', function(e) {
            e.preventDefault();
            showCategoryModal();
        });
    } else {
    }
    
    // Cancel button in category modal
    var cancelCategoryBtn = document.querySelector('#popup-container .btn-cancel');
    if (cancelCategoryBtn) {
        cancelCategoryBtn.addEventListener('click', function(e) {
            e.preventDefault();
            hideCategoryModal();
        });
    }
}

function initializeFileUploads() {
    // Course image upload
    var courseImageInput = document.querySelector('input[name="course_image"]');
    if (courseImageInput) {
        courseImageInput.addEventListener('change', handleImageUpload);
    }
    
    // Course video upload
    var courseVideoInput = document.querySelector('input[name="course_video"]');
    if (courseVideoInput) {
        courseVideoInput.addEventListener('change', handleVideoUpload);
    }
    
    // Ensure existing videos load correctly
    var videoPlayer = document.getElementById('course-video-preview');
    if (videoPlayer) {
        // Check if it's a video element, if not, replace it with a proper video element
        if (videoPlayer.tagName.toLowerCase() !== 'video' || typeof videoPlayer.load !== 'function') {
            
            // Get parent element
            var parentElement = videoPlayer.parentElement;
            
            // Create a new video element with the same attributes
            var newVideoPlayer = document.createElement('video');
            newVideoPlayer.id = 'course-video-preview';
            
            // Copy classes
            if (videoPlayer.className) {
                newVideoPlayer.className = videoPlayer.className;
            }
            
            // Set video attributes
            newVideoPlayer.controls = true;
            newVideoPlayer.style.width = '100%';
            newVideoPlayer.style.maxHeight = '300px';
            
            // Replace the old element with the new video element
            if (parentElement) {
                parentElement.replaceChild(newVideoPlayer, videoPlayer);
                videoPlayer = newVideoPlayer;
            }
        }
        
        try {
            // Force video reload
            videoPlayer.load();
            
            // Add event listeners to monitor video state
            videoPlayer.addEventListener('error', function(e) {
            });
            
            videoPlayer.addEventListener('loadeddata', function() {
            });
        } catch (error) {
        }
    }
}

function initializeExistingImagePreview() {
    
    var imagePreview = document.getElementById('course-image-preview');
    var imageContainer = document.querySelector('.course-image-container');

    // Image preview elements
        imagePreview: !!imagePreview,
        imageContainer: !!imageContainer
    });
    
    // Check if there's an existing image
    if (imagePreview && imagePreview.src && !imagePreview.src.includes('data:') && imagePreview.src !== window.location.href) {
        
        // Ensure the container is visible
        if (imageContainer) {
            imageContainer.classList.remove('hidden');
            imageContainer.style.display = 'block';
        }
        
        // Ensure the image itself is visible
        imagePreview.classList.remove('hidden');
        imagePreview.style.display = 'block';
        
        // Add error handling for broken images
        imagePreview.onerror = function() {
            this.style.display = 'none';
            
            // Show user-friendly error message
            var errorDiv = document.createElement('div');
            errorDiv.className = 'image-error-message bg-red-50 border border-red-200 rounded-md p-3 mt-2';
            errorDiv.innerHTML = `
                <div class="flex items-center">
                    <i class="fas fa-exclamation-triangle text-red-400 mr-2"></i>
                    <span class="text-red-700 text-sm">Image failed to load. This may be due to S3 permissions or network issues.</span>
                </div>
            `;
            
            // Insert error message after the image container
            var imageContainer = this.closest('.course-image-container');
            if (imageContainer && imageContainer.parentNode) {
                imageContainer.parentNode.insertBefore(errorDiv, imageContainer.nextSibling);
            }
        };
        
        // Add load success handler
        imagePreview.onload = function() {
        };
    } else {
    }
}

function handleImageUpload(e) {
    // Handle both event object and direct input element
    var input = e.target || e;
    var fileInfo = document.getElementById('image-file-info');
    var imagePreview = document.getElementById('course-image-preview');
    
    // Debug logging removed for production
    
    // Check if input has files property and is a file input
    if (input && input.files && input.files[0]) {
        var file = input.files[0];
        var fileSize = file.size / (1024 * 1024); // Convert to MB
        
        // Check file type
        if (!file.type.match('image.*')) {
            if (typeof showToast === 'function') {
            showToast('Please upload an image file', 'error');
        }
            input.value = '';
            return;
        }
        
        // Validate using the comprehensive security validator
        if (typeof SecureFilenameValidator !== 'undefined') {
            var validator = SecureFilenameValidator.createCategoryValidator('image', 10);
            var result = validator.validateFile(file);
            if (!result.valid) {
                // Show user-friendly error messages
                var errorMsg = result.errors.join('\n\n');
                if (typeof showToast === 'function') {
                    showToast('File Validation Error: ' + errorMsg + ' Please choose a different file or rename your file using simple characters.', 'error');
                } else {
                    // File validation error handled by showToast
                }
                input.value = '';
                return;
            }
        }
        
        // Update UI
        fileInfo.textContent = 'Selected: ' + file.name + ' (' + fileSize.toFixed(2) + 'MB)';

        
        // Show preview
        var reader = new FileReader();
        reader.onload = function(e) {
            imagePreview.src = e.target.result;
            imagePreview.classList.remove('hidden');
            // Also show the container if it's hidden
            var imageContainer = imagePreview.closest('.course-image-container');
            if (imageContainer) {
                imageContainer.classList.remove('hidden');
            }
        };
        reader.readAsDataURL(file);
    } else {
        // Reset preview if no file selected
        fileInfo.textContent = 'JPG, PNG, GIF, WEBP • Max 10MB • Use simple filenames';

        imagePreview.classList.add('hidden');
        // Also hide the container
        var imageContainer = imagePreview.closest('.course-image-container');
        if (imageContainer) {
            imageContainer.classList.add('hidden');
        }
    }
}

function handleVideoUpload(e) {
    var input = e.target;
    var fileInfo = document.getElementById('video-file-info');
    var filenameDisplay = document.getElementById('video-filename-display');
    var videoPreviewContainer = document.getElementById('course-video-preview');
    
    if (!videoPreviewContainer) {
        return;
    }
    
    if (input.files && input.files[0]) {
        var file = input.files[0];
        var fileSize = file.size / (1024 * 1024); // Convert to MB
        
        // Check file type
        if (!file.type.match('video.*')) {
            if (typeof showToast === 'function') {
                showToast('Please upload a video file', 'error');
            } else {
                // Video file validation error handled by showToast
            }
            input.value = '';
            return;
        }
        
        // Validate using the comprehensive security validator
        if (typeof SecureFilenameValidator !== 'undefined') {
            var validator = SecureFilenameValidator.createCategoryValidator('video', 500);
            var result = validator.validateFile(file);
            if (!result.valid) {
                // Show user-friendly error messages
                var errorMsg = result.errors.join('\n\n');
                if (typeof showToast === 'function') {
                    showToast('File Validation Error: ' + errorMsg + ' Please choose a different file or rename your file using simple characters.', 'error');
                } else {
                    // File validation error handled by showToast
                }
                input.value = '';
                return;
            }
        }
        
        // Update UI
        fileInfo.textContent = 'Selected: ' + file.name + ' (' + fileSize.toFixed(2) + 'MB)';

        
        // Show preview
        var videoUrl = URL.createObjectURL(file);
        
        // Make sure it's a video element and has source
        if (videoPreviewContainer.tagName.toLowerCase() === 'video') {
            var sourceElement = videoPreviewContainer.querySelector('source');
            if (!sourceElement) {
                sourceElement = document.createElement('source');
                sourceElement.type = 'video/mp4';
                videoPreviewContainer.appendChild(sourceElement);
            }
            sourceElement.src = videoUrl;
            
            // Set video properties and ensure it appears
            videoPreviewContainer.classList.remove('hidden');
            videoPreviewContainer.style.display = 'block';
            videoPreviewContainer.muted = false;
            videoPreviewContainer.controls = true;
            videoPreviewContainer.load();
            
            // Force video reload
            videoPreviewContainer.parentElement.classList.remove('hidden');
            
            // Try to ensure video is playable
            videoPreviewContainer.onloadeddata = function() {
            };
        } else {
        }
    } else {
        // Reset preview if no file selected
        fileInfo.textContent = 'MP4, WEBM, OGG • Max 500MB • Use simple filenames';

        if (videoPreviewContainer) {
            videoPreviewContainer.classList.add('hidden');
        }
    }
}

function removeImage() {
    var courseImageInput = document.querySelector('input[name="course_image"]');
    var fileInfo = document.getElementById('image-file-info');
    var imagePreview = document.getElementById('course-image-preview');
    var imageContainer = document.querySelector('.course-image-container');
    
    // Debug logging
    
    // Reset input
    if (courseImageInput) {
        courseImageInput.value = '';
    }
    
    // Reset UI
    if (fileInfo) {
        fileInfo.textContent = 'PNG, JPG - All Sizes Supported';
    }
    
    if (imagePreview) {
        imagePreview.classList.add('hidden');
        // Also hide the container
        var imageContainer = imagePreview.closest('.course-image-container');
        if (imageContainer) {
            imageContainer.classList.add('hidden');
        }
    }
    
    // Set a hidden input to indicate image should be removed
    var removeImageInput = document.getElementById('remove_image');
    
    if (!removeImageInput) {
        removeImageInput = document.createElement('input');
        removeImageInput.type = 'hidden';
        removeImageInput.id = 'remove_image';
        removeImageInput.name = 'remove_image';
        removeImageInput.value = 'true';
        
        if (courseImageInput && courseImageInput.parentNode) {
            courseImageInput.parentNode.appendChild(removeImageInput);
        } else {
            // Fallback - add to form
            var form = document.querySelector('form');
            if (form) {
                form.appendChild(removeImageInput);
            } else {
            }
        }
    } else {
        removeImageInput.value = 'true';
    }

    // Hide the image container if it exists
    if (imageContainer) {
        imageContainer.classList.add('hidden');
    }
    
    return false; // Prevent default action if called from onclick
}

// Add event listeners as backup for the remove buttons
document.addEventListener('DOMContentLoaded', function() {
    // Remove image button
    var removeImageBtn = document.getElementById('remove-image-btn');
    if (removeImageBtn) {
        removeImageBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            removeImage();
            return false;
        });
    } else {
    }
    
    // Remove video buttons (both existing and new)
    var removeVideoBtnExisting = document.getElementById('remove-video-btn-existing');
    var removeVideoBtnNew = document.getElementById('remove-video-btn-new');
    
    if (removeVideoBtnExisting) {
        removeVideoBtnExisting.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            removeVideo();
            return false;
        });
    }
    
    if (removeVideoBtnNew) {
        removeVideoBtnNew.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            removeVideo();
            return false;
        });
    }
    
    if (!removeVideoBtnExisting && !removeVideoBtnNew) {
    }
});

function removeVideo() {
    var courseVideoInput = document.querySelector('input[name="course_video"]');
    var fileInfo = document.getElementById('video-file-info');
    var filenameDisplay = document.getElementById('video-filename-display');
    var videoPreviewContainer = document.getElementById('course-video-preview');
    var videoContainer = document.querySelector('.course-video-container');
    
    // Reset input
    if (courseVideoInput) {
        courseVideoInput.value = '';
    }
    
    // Reset UI
    if (fileInfo) {
        fileInfo.textContent = 'MP4, MOV - All Sizes Supported';
    }
    
    if (filenameDisplay) {

    }
    
    if (videoPreviewContainer) {
        // Reset video source
        var sourceElement = videoPreviewContainer.querySelector('source');
        if (sourceElement) {
            sourceElement.src = '';
        }
        
        // Hide video preview
        videoPreviewContainer.classList.add('hidden');
        
        if (videoPreviewContainer.parentElement) {
            videoPreviewContainer.parentElement.classList.add('hidden');
        }
        
        videoPreviewContainer.load(); // Force reload
    }
    
    // Set a hidden input to indicate video should be removed
    var removeVideoInput = document.getElementById('remove_video');
    
    if (!removeVideoInput) {
        removeVideoInput = document.createElement('input');
        removeVideoInput.type = 'hidden';
        removeVideoInput.id = 'remove_video';
        removeVideoInput.name = 'remove_video';
        removeVideoInput.value = 'true';
        
        if (courseVideoInput && courseVideoInput.parentNode) {
            courseVideoInput.parentNode.appendChild(removeVideoInput);
        } else {
            // Fallback - add to form
            var form = document.querySelector('form');
            if (form) {
                form.appendChild(removeVideoInput);
            } else {
            }
        }
    } else {
        removeVideoInput.value = 'true';
    }

    // Hide the video container if it exists
    if (videoContainer) {
        videoContainer.classList.add('hidden');
    }
    
    return false; // Prevent default action if called from onclick
}

function handleFormSubmit(e) {
    
    // Get all form elements
    var form = document.getElementById('courseCreateForm');
    if (!form) {
        return true; // Allow form to submit normally if not found
    }
    
    // Check if title is provided
    var titleInput = document.getElementById('title');
    if (titleInput && !titleInput.value.trim()) {
        if (typeof showToast === 'function') {
            showToast('Please enter a course title', 'error');
        } else {
            // Course title validation error handled by showToast
        }
        titleInput.focus();
        return false;
    }
    
    // Set form submitting flag and reset unsaved changes flag
    isFormSubmitting = true;
    formHasUnsavedChanges = false;
    
    // Hide notification if it exists
    var notification = document.getElementById('unsaved-changes-notification');
    if (notification) {
        notification.classList.add('-translate-y-full', 'hidden');
    }
    
    // Disable the submit button and show loading state
    var submitButton = document.getElementById('course-submit-button');
    if (submitButton) {
        submitButton.disabled = true;
        submitButton.innerHTML = 'Updating...';
    }
    
    return true;
}

// Expose handleFormSubmit globally
window.handleFormSubmit = handleFormSubmit;

// Modal management functions
function showSectionModal() {
    var modal = document.getElementById('add-section-modal');
    if (modal) {
        modal.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
        
        // Focus on first input
        setTimeout(function() {
            var firstInput = modal.querySelector('input[type="text"]');
            if (firstInput) firstInput.focus();
        }, 100);
    }
}

function hideSectionModal() {
    var modal = document.getElementById('add-section-modal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
        
        // Reset form
        var form = modal.querySelector('form');
        if (form) form.reset();
    }
}

function showMoveTopicModal(topicId) {
    var modal = document.getElementById('move-topic-modal');
    var topicIdInput = document.getElementById('topic_id_to_move');
    
    if (modal && topicIdInput) {
        // Set the topic ID
        topicIdInput.value = topicId;
        
        // Show the modal
        modal.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
    }
}

function hideMoveTopicModal() {
    var modal = document.getElementById('move-topic-modal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
    }
}

function showCategoryModal() {
    var modal = document.getElementById('popup-container');
    if (modal) {
        modal.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
        
        // Focus on first input
        setTimeout(function() {
            var firstInput = modal.querySelector('input[type="text"]');
            if (firstInput) firstInput.focus();
        }, 100);
    }
}

function hideCategoryModal() {
    var modal = document.getElementById('popup-container');
    if (modal) {
        modal.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
    }
}

// Expose modal functions globally
window.showSectionModal = showSectionModal;
window.hideSectionModal = hideSectionModal;
window.showMoveTopicModal = showMoveTopicModal;
window.hideMoveTopicModal = hideMoveTopicModal;
window.showCategoryModal = showCategoryModal;
window.hideCategoryModal = hideCategoryModal;

// Initialize tab functionality
function initializeTabButtons() {
    try {
        var tabButtons = document.querySelectorAll('.tab-btn');
        if (tabButtons.length === 0) {
            return;
        }
        
        tabButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                
                try {
                    // Remove active class from all buttons
                    document.querySelectorAll('.tab-btn').forEach(btn => {
                        btn.classList.remove('active');
                        btn.classList.remove('border-blue-600');
                        btn.classList.add('text-gray-500');
                    });
                    
                    // Hide all tab contents
                    document.querySelectorAll('.tab-content').forEach(content => {
                        content.classList.remove('active');
                        content.style.display = 'none';
                    });
                    
                    // Add active class to clicked button
                    this.classList.add('active');
                    this.classList.add('border-blue-600');
                    this.classList.remove('text-gray-500');
                    
                    // Show corresponding content
                    var target = this.getAttribute('data-tab-target');
                    if (target) {
                        var targetContent = document.querySelector(target);
                        if (targetContent) {
                            targetContent.classList.add('active');
                            targetContent.style.display = 'block';
                        } else {
                        }
                    }
                } catch (error) {
                }
            });
        });
    } catch (error) {
    }
}

// Make functions available globally
window.initFormChangeDetection = initFormChangeDetection;
window.markFormAsChanged = function() {
    formHasUnsavedChanges = true;
    showUnsavedChangesNotification();
};

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (window.CourseEditCleanup) {
        window.CourseEditCleanup.cleanup();
    }
});