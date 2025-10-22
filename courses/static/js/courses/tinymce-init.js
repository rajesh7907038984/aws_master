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
            console.log('TinyMCE loaded successfully after', attempts, 'attempts');
            callback();
        } else if (attempts < maxAttempts) {
            console.log('Waiting for TinyMCE to load, attempt:', attempts);
            setTimeout(checkTinyMCE, 100);
        } else {
            console.error('TinyMCE failed to load after', maxAttempts, 'attempts');
        }
    }
    
    checkTinyMCE();
}

// Function to initialize TinyMCE editors
function initializeTinyMCEEditors() {
    console.log('Initializing TinyMCE editors');
    
    const textareas = document.querySelectorAll('textarea.tinymce-editor');
    console.log('Found textareas with tinymce-editor class:', textareas.length);
    
    if (textareas.length === 0) {
        console.warn('No textareas with tinymce-editor class found');
        // Check all textareas for debugging
        const allTextareas = document.querySelectorAll('textarea');
        console.log('All textareas found:', allTextareas.length);
        allTextareas.forEach(function(ta, index) {
            console.log(`Textarea ${index}:`, {
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
        
        console.log('Initializing TinyMCE for:', textarea.id);
        
        // Get config from data attribute
        const configData = textarea.getAttribute('data-tinymce-config');
        let config = {};
        
        try {
            if (configData) {
                config = JSON.parse(configData);
            }
        } catch (e) {
            console.warn('Failed to parse TinyMCE config:', e);
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
                console.log('TinyMCE initialized successfully for:', textarea.id);
                if (editors && editors.length > 0) {
                    console.log('Editor instance created:', editors[0].id);
                }
            }).catch(function(error) {
                console.error('Failed to initialize TinyMCE for:', textarea.id, error);
            });
        } catch (error) {
            console.error('Error calling tinymce.init for:', textarea.id, error);
        }
    });
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, waiting for TinyMCE');
    
    waitForTinyMCE(function() {
        initializeTinyMCEEditors();
    });
}); 