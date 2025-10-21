/**
 * TinyMCE Initialization Guard Script
 * Ensures proper loading and initialization of TinyMCE editors
 */

(function() {
    'use strict';
    
    let tinymceInitialized = false;
    let initializationAttempts = 0;
    const MAX_ATTEMPTS = 30;
    
    // Function to check if TinyMCE is available
    function isTinyMCEReady() {
        return typeof tinymce !== 'undefined' && 
               typeof tinymce.init === 'function' &&
               typeof tinymce.get === 'function';
    }
    
    // Function to wait for TinyMCE with timeout
    function waitForTinyMCE(callback, maxAttempts = MAX_ATTEMPTS) {
        initializationAttempts++;
        
        if (isTinyMCEReady()) {
            callback();
        } else if (initializationAttempts < maxAttempts) {
            setTimeout(() => waitForTinyMCE(callback, maxAttempts), 200);
        } else {
            // Try to load TinyMCE dynamically as fallback
            loadTinyMCEDynamically(callback);
        }
    }
    
    // Fallback: Load TinyMCE dynamically
    function loadTinyMCEDynamically(callback) {
        
        // Check if script already exists
        if (document.querySelector('script[src*="tinymce.min.js"]')) {
            setTimeout(() => waitForTinyMCE(callback, 10), 1000);
            return;
        }
        
        const script = document.createElement('script');
        script.src = '/static/tinymce_editor/tinymce/tinymce.min.js';
        script.onload = function() {
            setTimeout(() => waitForTinyMCE(callback, 10), 500);
        };
        script.onerror = function() {
        };
        document.head.appendChild(script);
    }
    
    // Initialize TinyMCE editors
    function initializeTinyMCEEditors() {
        if (tinymceInitialized) {
            return;
        }
        
        
        // Find all textareas with tinymce-editor class
        const textareas = document.querySelectorAll('textarea.tinymce-editor:not([data-tinymce-initialized])');
        
        if (textareas.length === 0) {
            tinymceInitialized = true;
            return;
        }
        
        // Initialize each textarea
        textareas.forEach(function(textarea) {
            initializeSingleEditor(textarea);
        });
        
        tinymceInitialized = true;
    }
    
    // Initialize a single TinyMCE editor
    function initializeSingleEditor(textarea) {
        // Ensure textarea has an ID
        if (!textarea.id) {
            textarea.id = 'tinymce-' + Math.random().toString(36).substr(2, 9);
        }
        
        // Mark as being initialized
        textarea.setAttribute('data-tinymce-initialized', 'true');
        
        
        // Get configuration from data attribute
        let config = {};
        try {
            const configData = textarea.getAttribute('data-tinymce-config');
            if (configData) {
                config = JSON.parse(configData);
            }
        } catch (e) {
        }
        
        // Set default configuration
        const defaultConfig = {
            selector: '#' + textarea.id,
            height: 400,
            menubar: false,
            plugins: 'link image lists code fullscreen wordcount',
            toolbar: 'undo redo | formatselect | bold italic | bullist numlist | link image code fullscreen',
            content_style: 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
            branding: false,
            promotion: false,
            statusbar: true,
            resize: true,
            base_url: '/static/tinymce_editor/tinymce/',
            setup: function(editor) {
            }
        };
        
        // Merge with custom config
        const finalConfig = Object.assign({}, defaultConfig, config);
        
        // Initialize TinyMCE
        try {
            tinymce.init(finalConfig).then(function(editors) {
                if (editors && editors.length > 0) {
                }
            }).catch(function(error) {
            });
        } catch (error) {
        }
    }
    
    // Reinitialize function for external use
    window.reinitializeTinyMCE = function() {
        tinymceInitialized = false;
        initializationAttempts = 0;
        
        // Remove existing editors
        if (typeof tinymce !== 'undefined' && tinymce.editors) {
            tinymce.editors.forEach(function(editor) {
                tinymce.remove('#' + editor.id);
            });
        }
        
        // Reset initialization flags
        document.querySelectorAll('textarea[data-tinymce-initialized]').forEach(function(textarea) {
            textarea.removeAttribute('data-tinymce-initialized');
        });
        
        // Wait and reinitialize
        waitForTinyMCE(initializeTinyMCEEditors);
    };
    
    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        waitForTinyMCE(initializeTinyMCEEditors);
    });
    
    // Also try to initialize if DOM is already loaded
    if (document.readyState === 'loading') {
        // DOM is still loading, wait for DOMContentLoaded
    } else {
        // DOM is already loaded
        waitForTinyMCE(initializeTinyMCEEditors);
    }
    
})();