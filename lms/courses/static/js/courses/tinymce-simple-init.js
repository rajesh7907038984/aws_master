/**
 * Simple TinyMCE Initialization for Course Edit Page
 * Works with global TinyMCE components
 */

(function() {
    'use strict';
    
    console.log('Course Edit Page: Simple TinyMCE initialization');
    
    // Wait for DOM and global TinyMCE components to be ready
    function initializeWhenReady() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeWhenReady);
            return;
        }
        
        // Check if TinyMCE is available
        if (typeof tinymce === 'undefined') {
            console.log('TinyMCE not available yet, waiting...');
            setTimeout(initializeWhenReady, 200);
            return;
        }
        
        console.log('TinyMCE is available, initializing editors...');
        initializeTinyMCEEditors();
    }
    
    // Initialize TinyMCE editors using global components
    function initializeTinyMCEEditors() {
        console.log('Initializing TinyMCE editors using global components...');
        
        // Use TinyMCE widget system if available
        if (typeof window.TinyMCEWidget !== 'undefined' && window.TinyMCEWidget.initializeAll) {
            console.log('Using TinyMCE widget system');
            window.TinyMCEWidget.initializeAll();
        }
        
        // Find any textareas that need manual initialization
        const textareas = document.querySelectorAll('textarea.tinymce-editor:not([data-tinymce-initialized])');
        console.log(`Found ${textareas.length} textareas for manual initialization`);
        
        textareas.forEach(function(textarea) {
            initializeSingleEditor(textarea);
        });
        
        console.log('TinyMCE initialization completed');
    }
    
    // Initialize a single editor
    function initializeSingleEditor(textarea) {
        if (!textarea.id) {
            textarea.id = 'tinymce-' + Math.random().toString(36).substr(2, 9);
        }
        
        textarea.setAttribute('data-tinymce-initialized', 'true');
        console.log('Initializing TinyMCE for:', textarea.id);
        
        const config = {
            selector: '#' + textarea.id,
            height: 450,
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
        
        try {
            tinymce.init(config).then(function(editors) {
                console.log('TinyMCE initialized successfully for:', textarea.id);
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
        
        // Reinitialize
        setTimeout(initializeTinyMCEEditors, 100);
    };
    
    // Start initialization
    initializeWhenReady();
    
})();
