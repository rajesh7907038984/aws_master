/**
 * TinyMCE Plugin to fix toolbar visibility issues
 */

(function() {
    'use strict';
    
    console.log('Toolbar Fix Plugin loading...');
    
    tinymce.PluginManager.add('toolbarfix', function(editor) {
        console.log('Toolbar Fix Plugin initialized for editor:', editor.id);
        
        // Fix toolbar visibility after editor initialization
        editor.on('init', function() {
            console.log('Fixing toolbar visibility...');
            
            // Add a slight delay to let TinyMCE render fully
            setTimeout(function() {
                // Get all toolbar elements
                const container = editor.getContainer();
                const header = container.querySelector('.tox-editor-header');
                const toolbarOverlord = container.querySelector('.tox-toolbar-overlord');
                const toolbarPrimary = container.querySelector('.tox-toolbar__primary');
                const toolbarGroups = container.querySelectorAll('.tox-toolbar__group');
                
                // Fix container width
                container.style.width = '100%';
                container.style.maxWidth = '100%';
                
                // Fix header position
                if (header) {
                    header.style.display = 'block';
                    header.style.visibility = 'visible';
                    header.style.opacity = '1';
                    header.style.position = 'static';
                    header.style.width = '100%';
                    header.style.left = '0';
                }
                
                // Fix toolbar overlord position
                if (toolbarOverlord) {
                    toolbarOverlord.style.display = 'block';
                    toolbarOverlord.style.visibility = 'visible';
                    toolbarOverlord.style.opacity = '1';
                    toolbarOverlord.style.width = '100%';
                    toolbarOverlord.style.left = '0';
                }
                
                // Fix primary toolbar position
                if (toolbarPrimary) {
                    toolbarPrimary.style.display = 'flex';
                    toolbarPrimary.style.visibility = 'visible';
                    toolbarPrimary.style.opacity = '1';
                    toolbarPrimary.style.width = '100%';
                    toolbarPrimary.style.left = '0';
                    toolbarPrimary.style.justifyContent = 'flex-start';
                    toolbarPrimary.style.transform = 'none';
                }
                
                // Fix toolbar groups
                toolbarGroups.forEach(function(group) {
                    group.style.display = 'flex';
                    group.style.visibility = 'visible';
                    group.style.opacity = '1';
                    group.style.position = 'relative';
                    group.style.left = '0';
                });
                
                console.log('Toolbar visibility fixed');
                
                // Force editor to recalculate layout
                editor.fire('ResizeEditor');
                
                // Setup a resize observer to maintain toolbar position on window resize
                if (typeof ResizeObserver !== 'undefined') {
                    const resizeObserver = new ResizeObserver(function() {
                        // Reapply the same fixes
                        if (toolbarPrimary) {
                            toolbarPrimary.style.width = '100%';
                            toolbarPrimary.style.left = '0';
                            toolbarPrimary.style.transform = 'none';
                        }
                    });
                    
                    resizeObserver.observe(container);
                }
            }, 300);
        });
        
        // Also fix on editor resize events
        editor.on('ResizeEditor', function() {
            setTimeout(function() {
                const container = editor.getContainer();
                const toolbarPrimary = container.querySelector('.tox-toolbar__primary');
                
                if (toolbarPrimary) {
                    toolbarPrimary.style.width = '100%';
                    toolbarPrimary.style.left = '0';
                    toolbarPrimary.style.transform = 'none';
                }
            }, 100);
        });
        
        // Return plugin metadata
        return {
            getMetadata: function() {
                return {
                    name: 'Toolbar Fix',
                    url: 'https://example.com/toolbarfix'
                };
            }
        };
    });
})(); 