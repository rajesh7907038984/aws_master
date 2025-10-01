/**
 * TinyMCE Toolbar Fixer
 * This script ensures the TinyMCE toolbar is visible by applying styles directly to the DOM
 */

(function() {
    'use strict';
    
    console.log('TinyMCE Toolbar Fixer loading...');
    
    // Wait for TinyMCE to load
    function checkTinyMCE() {
        if (typeof tinymce !== 'undefined') {
            console.log('TinyMCE detected, setting up toolbar fixer');
            setupToolbarFixer();
        } else {
            setTimeout(checkTinyMCE, 100);
        }
    }
    
    // Setup the toolbar fixer
    function setupToolbarFixer() {
        // Add event listener for editor initialization
        tinymce.on('AddEditor', function(e) {
            const editor = e.editor;
            
            editor.on('init', function() {
                console.log('Fixing toolbar for editor:', editor.id);
                setTimeout(function() {
                    fixToolbar(editor);
                }, 300);
            });
            
            // Fix on post render as well
            editor.on('PostRender', function() {
                setTimeout(function() {
                    fixToolbar(editor);
                }, 300);
            });
        });
        
        // Fix toolbars for existing editors
        if (tinymce.activeEditor) {
            setTimeout(function() {
                if (tinymce.editors && Array.isArray(tinymce.editors)) {
                    tinymce.editors.forEach(function(editor) {
                        fixToolbar(editor);
                    });
                } else if (tinymce.activeEditor) {
                    // Fallback to just fixing the active editor if editors array is not available
                    fixToolbar(tinymce.activeEditor);
                }
            }, 300);
        }
    }
    
    // Fix toolbar visibility for a specific editor
    function fixToolbar(editor) {
        if (!editor || !editor.getContainer()) {
            return;
        }
        
        const container = editor.getContainer();
        
        // Get toolbar elements
        const header = container.querySelector('.tox-editor-header');
        const toolbarOverlord = container.querySelector('.tox-toolbar-overlord');
        const toolbarPrimary = container.querySelector('.tox-toolbar__primary');
        const toolbarGroups = container.querySelectorAll('.tox-toolbar__group');
        const buttons = container.querySelectorAll('.tox-tbtn');
        
        // Apply styles to show toolbar
        if (header) {
            header.style.display = 'block';
            header.style.visibility = 'visible';
            header.style.opacity = '1';
            header.style.position = 'static';
            header.style.zIndex = '10';
        }
        
        if (toolbarOverlord) {
            toolbarOverlord.style.display = 'block';
            toolbarOverlord.style.visibility = 'visible';
            toolbarOverlord.style.opacity = '1';
        }
        
        if (toolbarPrimary) {
            toolbarPrimary.style.display = 'flex';
            toolbarPrimary.style.visibility = 'visible';
            toolbarPrimary.style.opacity = '1';
            toolbarPrimary.style.flexWrap = 'wrap';
        }
        
        toolbarGroups.forEach(function(group) {
            group.style.display = 'flex';
            group.style.visibility = 'visible';
            group.style.opacity = '1';
        });
        
        buttons.forEach(function(button) {
            button.style.display = 'flex';
            button.style.visibility = 'visible';
            button.style.opacity = '1';
        });
        
        // Hide the overflow button
        const overflowButton = container.querySelector('[data-mce-name="overflow-button"]');
        if (overflowButton) {
            overflowButton.style.display = 'none';
        }
        
        console.log('Toolbar fixed for editor:', editor.id);
        
        // Force editor to redraw
        editor.fire('ResizeEditor');
    }
    
    // Start the fixer
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkTinyMCE);
    } else {
        checkTinyMCE();
    }
})(); 