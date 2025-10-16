/**
 * TinyMCE Initialization Script for Course Edit Page
 * Handles proper loading and initialization of TinyMCE editors
 */

// Function to wait for TinyMCE to be available
function waitForTinyMCE(callback, maxAttempts = 50) {
    let attempts = 0;
    
    function checkTinyMCE() {
        attempts++;
        
        if (typeof tinymce !== 'undefined' && tinymce.init) {
            callback();
        } else if (attempts < maxAttempts) {
            setTimeout(checkTinyMCE, 100);
        } else {
        }
    }
    
    checkTinyMCE();
}

// Function to initialize TinyMCE editors
function initializeTinyMCEEditors() {
    
    const textareas = document.querySelectorAll('textarea.tinymce-editor');
    
    if (textareas.length === 0) {
        // Check all textareas for debugging
        const allTextareas = document.querySelectorAll('textarea');
        allTextareas.forEach(function(ta, index) {
                id: ta.id,
                className: ta.className,
                name: ta.name
            });
        });
        return;
    }
    
    textareas.forEach(function(textarea) {
        if (!textarea.id) {
            textarea.id = 'tinymce-' + Math.random().toString(36).substr(2, 9);
        }
        
        
        // Get config from data attribute
        const configData = textarea.getAttribute('data-tinymce-config');
        let config = {};
        
        try {
            if (configData) {
                config = JSON.parse(configData);
            }
        } catch (e) {
        }
        
        // Set default config if none provided
        if (Object.keys(config).length === 0) {
            config = {
                height: 400,
                menubar: true,
                statusbar: false,
                plugins: [
                    'advlist', 'autolink', 'lists', 'link', 'image', 'charmap', 'preview',
                    'anchor', 'searchreplace', 'visualblocks', 'code', 'fullscreen',
                    'insertdatetime', 'media', 'table', 'wordcount'
                ],
                toolbar: 'undo redo | blocks | bold italic forecolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat',
                content_style: 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }'
            };
        }
        
        // Set required options
        config.selector = '#' + textarea.id;
        config.base_url = '/static/tinymce_editor/tinymce/';
        config.branding = false;
        config.promotion = false;
        
        // Initialize TinyMCE with error handling
        try {
            tinymce.init(config).then(function(editors) {
                if (editors && editors.length > 0) {
                }
            }).catch(function(error) {
            });
        } catch (error) {
        }
    });
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    
    waitForTinyMCE(function() {
        initializeTinyMCEEditors();
    });
}); 