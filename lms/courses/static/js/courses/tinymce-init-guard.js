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
            console.log('TinyMCE is ready, initializing editors...');
            callback();
        } else if (initializationAttempts < maxAttempts) {
            console.log(`Waiting for TinyMCE... attempt ${initializationAttempts}/${maxAttempts}`);
            setTimeout(() => waitForTinyMCE(callback, maxAttempts), 200);
        } else {
            console.error('TinyMCE failed to load after maximum attempts');
            // Try to load TinyMCE dynamically as fallback
            loadTinyMCEDynamically(callback);
        }
    }
    
    // Fallback: Load TinyMCE dynamically
    function loadTinyMCEDynamically(callback) {
        console.log('Attempting to load TinyMCE dynamically...');
        
        // Check if script already exists
        if (document.querySelector('script[src*="tinymce.min.js"]')) {
            console.log('TinyMCE script already exists, waiting for it to load...');
            setTimeout(() => waitForTinyMCE(callback, 10), 1000);
            return;
        }
        
        const script = document.createElement('script');
        script.src = '/static/tinymce_editor/tinymce/tinymce.min.js';
        script.onload = function() {
            console.log('TinyMCE loaded dynamically');
            setTimeout(() => waitForTinyMCE(callback, 10), 500);
        };
        script.onerror = function() {
            console.error('Failed to load TinyMCE dynamically');
        };
        document.head.appendChild(script);
    }
    
    // Initialize TinyMCE editors
    function initializeTinyMCEEditors() {
        if (tinymceInitialized) {
            console.log('TinyMCE already initialized, skipping');
            return;
        }
        
        console.log('Initializing TinyMCE editors...');
        
        // Find all textareas with tinymce-editor class
        const textareas = document.querySelectorAll('textarea.tinymce-editor:not([data-tinymce-initialized])');
        console.log(`Found ${textareas.length} textareas to initialize`);
        
        if (textareas.length === 0) {
            console.log('No textareas found for TinyMCE initialization');
            tinymceInitialized = true;
            return;
        }
        
        // Initialize each textarea
        textareas.forEach(function(textarea) {
            initializeSingleEditor(textarea);
        });
        
        tinymceInitialized = true;
        console.log('TinyMCE initialization completed');
    }
    
    // Initialize a single TinyMCE editor
    function initializeSingleEditor(textarea) {
        // Ensure textarea has an ID
        if (!textarea.id) {
            textarea.id = 'tinymce-' + Math.random().toString(36).substr(2, 9);
        }
        
        // Mark as being initialized
        textarea.setAttribute('data-tinymce-initialized', 'true');
        
        console.log('Initializing TinyMCE for:', textarea.id);
        
        // Get configuration from data attribute
        let config = {};
        try {
            const configData = textarea.getAttribute('data-tinymce-config');
            if (configData) {
                config = JSON.parse(configData);
            }
        } catch (e) {
            console.warn('Failed to parse TinyMCE config for', textarea.id, ':', e);
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
                console.log('TinyMCE editor setup completed for:', editor.id);
            }
        };
        
        // Merge with custom config
        const finalConfig = Object.assign({}, defaultConfig, config);
        
        // Initialize TinyMCE
        try {
            tinymce.init(finalConfig).then(function(editors) {
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
    }
    
    // Reinitialize function for external use
    window.reinitializeTinyMCE = function() {
        console.log('Reinitializing TinyMCE...');
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
        console.log('DOM loaded, initializing TinyMCE...');
        waitForTinyMCE(initializeTinyMCEEditors);
    });
    
    // Also try to initialize if DOM is already loaded
    if (document.readyState === 'loading') {
        // DOM is still loading, wait for DOMContentLoaded
    } else {
        // DOM is already loaded
        console.log('DOM already loaded, initializing TinyMCE immediately...');
        waitForTinyMCE(initializeTinyMCEEditors);
    }
    
})();