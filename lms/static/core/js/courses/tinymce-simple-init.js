/**
 * Simple TinyMCE Initialization for Course Edit Page
 * Works with global TinyMCE components
 */

(function() {
    'use strict';
    
    
    // Wait for DOM and global TinyMCE components to be ready
    function initializeWhenReady() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeWhenReady);
            return;
        }
        
        // Check if TinyMCE is available
        if (typeof tinymce === 'undefined') {
            setTimeout(initializeWhenReady, 200);
            return;
        }
        
        initializeTinyMCEEditors();
    }
    
    // Initialize TinyMCE editors using global components
    function initializeTinyMCEEditors() {
        
        // Use TinyMCE widget system if available
        if (typeof window.TinyMCEWidget !== 'undefined' && window.TinyMCEWidget.initializeAll) {
            window.TinyMCEWidget.initializeAll();
        }
        
        // Find any textareas that need manual initialization
        const textareas = document.querySelectorAll('textarea.tinymce-editor:not([data-tinymce-initialized])');
        
        textareas.forEach(function(textarea) {
            initializeSingleEditor(textarea);
        });
        
    }
    
    // Initialize a single editor
    function initializeSingleEditor(textarea) {
        if (!textarea.id) {
            textarea.id = 'tinymce-' + Math.random().toString(36).substr(2, 9);
        }
        
        textarea.setAttribute('data-tinymce-initialized', 'true');
        
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
            }
        };
        
        try {
            tinymce.init(config).then(function(editors) {
            }).catch(function(error) {
            });
        } catch (error) {
        }
    }
    
    // Reinitialize function for external use
    window.reinitializeTinyMCE = function() {
        
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
