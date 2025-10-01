/**
 * Existing Content Loader for Edit Forms
 * Ensures that previously added data renders properly in edit pages
 */

(function() {
    'use strict';
    
    // Track loaded content to prevent duplicates
    const loadedContent = new Set();
    
    /**
     * Enhanced TinyMCE content loading with proper timing
     */
    function loadTinyMCEContent(editorId, content) {
        if (!content || !content.trim()) {
            console.log(`No content to load for editor: ${editorId}`);
            return;
        }
        
        const editor = tinymce.get(editorId);
        if (!editor) {
            console.warn(`TinyMCE editor not found: ${editorId}`);
            return;
        }
        
        // Check if content is already loaded to prevent overwrites
        const contentKey = `${editorId}_${content.substring(0, 50)}`;
        if (loadedContent.has(contentKey)) {
            console.log(`Content already loaded for editor: ${editorId}`);
            return;
        }
        
        console.log(`Loading content into TinyMCE editor ${editorId}: ${content.length} chars`);
        
        // Set content with proper timing
        if (editor.initialized) {
            editor.setContent(content);
            loadedContent.add(contentKey);
        } else {
            editor.on('init', function() {
                editor.setContent(content);
                loadedContent.add(contentKey);
                console.log(`Content loaded after editor init: ${editorId}`);
            });
        }
    }
    
    /**
     * Ensure existing image previews are visible
     */
    function ensureImagePreviewVisible(imageId, containerId = null) {
        const image = document.getElementById(imageId);
        if (!image) return;
        
        const container = containerId ? document.getElementById(containerId) : image.closest('.image-container, .course-image-container');
        
        if (image.src && !image.src.includes('data:') && image.src !== window.location.href) {
            console.log(`Making existing image visible: ${imageId}`);
            
            if (container) {
                container.classList.remove('hidden');
                container.style.display = 'block';
            }
            
            image.classList.remove('hidden');
            image.style.display = 'block';
            
            // Add error handling
            image.onerror = function() {
                console.error(`Failed to load image: ${this.src}`);
                this.style.display = 'none';
                
                // Show error message
                const errorDiv = document.createElement('div');
                errorDiv.className = 'image-error-message bg-red-50 border border-red-200 rounded-md p-3 mt-2';
                errorDiv.innerHTML = `
                    <div class="flex items-center">
                        <i class="fas fa-exclamation-triangle text-red-400 mr-2"></i>
                        <span class="text-red-700 text-sm">Image failed to load. This may be due to S3 permissions or network issues.</span>
                    </div>
                `;
                
                if (container && container.parentNode) {
                    container.parentNode.insertBefore(errorDiv, container.nextSibling);
                }
            };
        }
    }
    
    /**
     * Ensure existing video previews are visible
     */
    function ensureVideoPreviewVisible(videoId, containerId = null) {
        const video = document.getElementById(videoId);
        if (!video) return;
        
        const container = containerId ? document.getElementById(containerId) : video.closest('.video-container, .course-video-container');
        
        if (video.src || video.querySelector('source[src]')) {
            console.log(`Making existing video visible: ${videoId}`);
            
            if (container) {
                container.classList.remove('hidden');
                container.style.display = 'block';
            }
            
            video.classList.remove('hidden');
            video.style.display = 'block';
            
            // Force video reload
            video.load();
        }
    }
    
    /**
     * Load existing form data with proper timing
     */
    function loadExistingFormData(formId, data) {
        const form = document.getElementById(formId);
        if (!form || !data) return;
        
        console.log(`Loading existing form data for: ${formId}`);
        
        // Wait for form to be ready
        setTimeout(() => {
            Object.keys(data).forEach(fieldName => {
                const field = form.querySelector(`[name="${fieldName}"]`);
                if (!field) return;
                
                const value = data[fieldName];
                
                if (field.type === 'checkbox') {
                    field.checked = value;
                } else if (field.type === 'radio') {
                    const radioField = form.querySelector(`[name="${fieldName}"][value="${value}"]`);
                    if (radioField) {
                        radioField.checked = true;
                        // Trigger change event
                        const event = new Event('change', { bubbles: true });
                        radioField.dispatchEvent(event);
                    }
                } else if (field.tagName === 'SELECT' && field.multiple && Array.isArray(value)) {
                    for (let i = 0; i < field.options.length; i++) {
                        field.options[i].selected = value.includes(field.options[i].value);
                    }
                } else {
                    field.value = value;
                }
                
                console.log(`Set field ${fieldName} to:`, value);
            });
        }, 100);
    }
    
    /**
     * Initialize all existing content on page load
     */
    function initializeExistingContent() {
        console.log('Initializing existing content for edit forms...');
        
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeExistingContent);
            return;
        }
        
        // Wait for TinyMCE to be available
        if (typeof tinymce === 'undefined') {
            setTimeout(initializeExistingContent, 500);
            return;
        }
        
        // Find all elements with existing content data
        const contentElements = document.querySelectorAll('[data-existing-content]');
        contentElements.forEach(element => {
            const content = element.getAttribute('data-existing-content');
            const editorId = element.id;
            
            if (content && editorId) {
                loadTinyMCEContent(editorId, content);
            }
        });
        
        // Find all image previews that should be visible
        const imagePreviews = document.querySelectorAll('[data-existing-image]');
        imagePreviews.forEach(img => {
            const imageId = img.id;
            const containerId = img.getAttribute('data-container-id');
            ensureImagePreviewVisible(imageId, containerId);
        });
        
        // Find all video previews that should be visible
        const videoPreviews = document.querySelectorAll('[data-existing-video]');
        videoPreviews.forEach(video => {
            const videoId = video.id;
            const containerId = video.getAttribute('data-container-id');
            ensureVideoPreviewVisible(videoId, containerId);
        });
        
        console.log('Existing content initialization complete');
    }
    
    // Expose functions globally
    window.ExistingContentLoader = {
        loadTinyMCEContent,
        ensureImagePreviewVisible,
        ensureVideoPreviewVisible,
        loadExistingFormData,
        initializeExistingContent
    };
    
    // Auto-initialize
    initializeExistingContent();
    
})();
