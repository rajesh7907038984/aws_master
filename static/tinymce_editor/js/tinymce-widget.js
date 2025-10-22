/**
 * TinyMCE Widget JavaScript for Django Integration
 * Automatically initializes TinyMCE editors on textareas with 'tinymce-editor' class
 */

(function() {
    'use strict';

    // Store initialized editors
    let initializedEditors = new Set();
    let retryAttempts = 0;
    const MAX_RETRY_ATTEMPTS = 10;

    /**
     * Initialize TinyMCE editor on a textarea element
     * @param {HTMLElement} textarea - The textarea element to initialize
     */
    function initializeTinyMCE(textarea) {
        if (initializedEditors.has(textarea.id)) {
            return; // Already initialized
        }

        // Get configuration from data attribute
        let config = {};
        try {
            const configData = textarea.getAttribute('data-tinymce-config');
            if (configData) {
                config = JSON.parse(configData);
            }
        } catch (e) {
            console.warn('Failed to parse TinyMCE config:', e);
        }

        // Set target selector
        config.selector = '#' + textarea.id;
        
        // Add base URL for TinyMCE assets
        config.base_url = '/static/tinymce_editor/tinymce/';
        
        // Set default configurations
        config.branding = false;
        config.promotion = false;
        config.license_key = 'gpl';
        
        // Status bar configuration - Updated to support custom footer options
        if (config.custom_footer === true || textarea.getAttribute('data-custom-footer') === 'true') {
            config.statusbar = true;
            config.elementpath = false;
            config.wordcount = true;
            config.path = false;
            config.help = false; // Explicitly disable help feature
            
            // Add custom footer options
            config.setup = config.setup || function() {};
            let originalSetup = config.setup;
            
            config.setup = function(editor) {
                // Call the original setup function
                if (typeof originalSetup === 'function') {
                    originalSetup(editor);
                }
                
                // Add custom footer buttons after editor is initialized
                editor.on('init', function() {
                    // Get the statusbar element
                    const statusbar = editor.getContainer().querySelector('.tox-statusbar');
                    
                    if (statusbar) {
                        // Create custom footer buttons container
                        const customFooter = document.createElement('div');
                        customFooter.className = 'tox-statusbar__custom-footer';
                        customFooter.style.cssText = 'display: flex; margin-left: auto;';
                        
                        // Create word count display
                        const wordCountElem = document.createElement('div');
                        wordCountElem.className = 'tox-statusbar__wordcount';
                        wordCountElem.innerHTML = '0 words';
                        
                        // Create character count display
                        const charCountElem = document.createElement('div');
                        charCountElem.className = 'tox-statusbar__charcount';
                        charCountElem.style.cssText = 'margin-left: 15px;';
                        charCountElem.innerHTML = '0 characters';
                        
                        // Add elements to footer
                        customFooter.appendChild(wordCountElem);
                        customFooter.appendChild(charCountElem);
                        
                        // Clear existing items to make room for our custom ones
                        const existingItems = statusbar.querySelectorAll('.tox-statusbar__text-container, .tox-statusbar__path, .tox-statusbar__branding');
                        existingItems.forEach(item => {
                            item.style.display = 'none';
                        });
                        
                        // Specifically target and remove the "Press ⌥0 for help" text and its container
                        const helpTextContainer = statusbar.querySelector('.tox-statusbar__help');
                        if (helpTextContainer) {
                            helpTextContainer.style.display = 'none';
                        }
                        
                        const helpText = statusbar.querySelector('.tox-statusbar__help-text');
                        if (helpText) {
                            helpText.style.display = 'none';
                            // Also try to remove the parent if it's not already hidden
                            if (helpText.parentElement && helpText.parentElement.style.display !== 'none') {
                                helpText.parentElement.style.display = 'none';
                            }
                        }
                        
                        // Add custom footer to statusbar
                        statusbar.appendChild(customFooter);
                        
                        // Update counts when content changes
                        const updateCounts = function() {
                            const text = editor.getContent({format: 'text'});
                            const charCount = text.length;
                            const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
                            
                            wordCountElem.innerHTML = wordCount + ' words';
                            charCountElem.innerHTML = charCount + ' characters';
                        };
                        
                        // Update immediately and on content changes
                        updateCounts();
                        editor.on('change keyup paste', updateCounts);
                    }
                });
            };
        } else {
            config.statusbar = config.statusbar || false;  // Default to false if not explicitly set
        }
        
        // Initialize external_plugins if not already set
        if (!config.external_plugins) {
            config.external_plugins = {};
        }
        
        // Add custom CSS for fixes
        if (!config.content_css) {
            config.content_css = '/static/tinymce_editor/css/tinymce-fixes.css,/static/tinymce_editor/css/force-toolbar.css';
        } else {
            config.content_css += ',/static/tinymce_editor/css/tinymce-fixes.css,/static/tinymce_editor/css/force-toolbar.css';
        }
        
        // Add custom CSS to the editor container
        if (!config.content_style) {
            config.content_style = 'body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, Cantarell, "Helvetica Neue", sans-serif; font-size: 16px; }';
        }
        
        // Use inline editing mode to ensure toolbar is visible
        config.inline = false;
        config.fixed_toolbar_container = '#tinymce-toolbar-container-' + textarea.id;
        
        // Ensure toolbar settings
        config.toolbar_location = 'top';
        config.toolbar_sticky = false;
        config.toolbar_mode = 'wrap';
        
        // Remove file and help from menubar if present
        if (config.menubar && typeof config.menubar === 'string') {
            const menuItems = config.menubar.split(' ');
            config.menubar = menuItems.filter(item => item !== 'file' && item !== 'help').join(' ');
        } else if (config.menubar === true) {
            // If menubar is set to true, set it to a string without file menu
            config.menubar = 'edit view insert format tools';
        }
        
        // Remove help plugin if present
        if (config.plugins && Array.isArray(config.plugins)) {
            config.plugins = config.plugins.filter(plugin => plugin !== 'help');
        }
        
        // Remove help from toolbar if present
        if (config.toolbar && typeof config.toolbar === 'string') {
            config.toolbar = config.toolbar.replace(/\|\s*help/g, '')
                                          .replace(/help\s*\|/g, '')
                                          .replace(/\s*help\s*/g, ' ')
                                          .trim();
        }
        
        // Ensure plugins is an array
        if (!config.plugins) {
            config.plugins = [];
        } else if (typeof config.plugins === 'string') {
            // Convert string to array
            config.plugins = config.plugins.split(' ').filter(p => p.trim());
        } else if (!Array.isArray(config.plugins)) {
            // If it's neither string nor array, initialize as empty array
            config.plugins = [];
        }
        
        // Note: paste plugin is built into TinyMCE 7.x core, no need to explicitly add it
        // Remove paste from plugins array if it exists (it's not needed as external plugin)
        if (config.plugins.indexOf('paste') !== -1) {
            config.plugins = config.plugins.filter(plugin => plugin !== 'paste');
        }
        
        // Set improved paste configuration for TinyMCE 7.0 compatibility
        config.paste_as_text = config.paste_as_text !== undefined ? config.paste_as_text : false;
        config.paste_data_images = config.paste_data_images !== undefined ? config.paste_data_images : true;
        
        // Add custom paste preprocessing function if needed
        if (!config.paste_preprocess) {
            config.paste_preprocess = function(plugin, args) {
                // Custom paste preprocessing logic can be added here
                // Configure paste filtering functionality
                return args;
            };
        }
        
        // Ensure AI Writer plugin is included
        if (config.plugins.indexOf('aiwriter') === -1) {
            config.plugins.push('aiwriter');
        }
        
        // Ensure AI Writer is in the toolbar
        if (!config.toolbar) {
            config.toolbar = 'aiwriter';
        } else if (config.toolbar.indexOf('aiwriter') === -1) {
            config.toolbar += ' | aiwriter';
        }
        
        // Ensure external plugins includes aiwriter
        if (!config.external_plugins) {
            config.external_plugins = {};
        }
        
        // Use full path for aiwriter plugin
        config.external_plugins.aiwriter = '/static/tinymce_editor/js/plugins/aiwriter/plugin.js';
        
        // Remove plugins from the plugins array if they are defined as external plugins
        if (config.plugins && Array.isArray(config.plugins) && config.external_plugins) {
            const externalPluginNames = Object.keys(config.external_plugins);
            config.plugins = config.plugins.filter(plugin => !externalPluginNames.includes(plugin));
        }
        
        // Configure external plugin paths - ensure no trailing slashes
        if (config.plugins) {
            // Only add media plugin if it's explicitly in the plugins array and not already configured
            if (config.plugins.includes('media') && !config.external_plugins.media) {
                // Use base_url if available, otherwise use absolute path
                if (config.base_url) {
                    config.external_plugins.media = config.base_url.replace(/\/$/, '') + '/plugins/media/plugin.min.js';
                } else {
                    config.external_plugins.media = '/static/tinymce_editor/tinymce/plugins/media/plugin.min.js';
                }
            }
            // Remove media from plugins array since it's defined as external
            if (config.external_plugins && config.external_plugins.media) {
                config.plugins = config.plugins.filter(plugin => plugin !== 'media');
            }
            
            if (config.plugins.includes('image') && !config.external_plugins.image) {
                if (config.base_url) {
                    config.external_plugins.image = config.base_url.replace(/\/$/, '') + '/plugins/image/plugin.min.js';
                } else {
                    config.external_plugins.image = '/static/tinymce_editor/tinymce/plugins/image/plugin.min.js';
                }
                // Remove image from plugins array since it's defined as external
                config.plugins = config.plugins.filter(plugin => plugin !== 'image');
            }
        }
        
        // Override file browser callback to disable default browser
        config.file_browser_callback = function(field_name, url, type, win) {
            // Disable default file browser - force use of our file_picker_callback
            return false;
        };
        
        // Add proper handlers for TinyMCE 7.0 compatibility
        config.images_upload_handler = function(blobInfo, success, failure, progress) {
            const formData = new FormData();
            formData.append('file', blobInfo.blob(), blobInfo.filename());
            
            const xhr = new XMLHttpRequest();
            xhr.open('POST', config.images_upload_url || '/tinymce/upload_image/');
            
            // Add CSRF token
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
            if (csrfToken) {
                xhr.setRequestHeader('X-CSRFToken', csrfToken.value);
            }
            
            xhr.onload = function() {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success && response.url) {
                            success(response.url);
                        } else {
                            failure(response.error || 'Upload failed');
                        }
                    } catch (e) {
                        failure('Invalid response format');
                    }
                } else {
                    failure('Upload failed: ' + xhr.statusText);
                }
            };
            
            xhr.onerror = function() {
                failure('Network error during upload');
            };
            
            xhr.send(formData);
        };
        
        config.media_upload_handler = function(blobInfo, success, failure, progress) {
            const formData = new FormData();
            formData.append('file', blobInfo.blob(), blobInfo.filename());
            
            const xhr = new XMLHttpRequest();
            xhr.open('POST', config.media_upload_url || '/tinymce/upload_media_file/');
            
            // Add CSRF token
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
            if (csrfToken) {
                xhr.setRequestHeader('X-CSRFToken', csrfToken.value);
            }
            
            xhr.onload = function() {
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.success && response.url) {
                            success(response.url);
                        } else {
                            failure(response.error || 'Upload failed');
                        }
                    } catch (e) {
                        failure('Invalid response format');
                    }
                } else {
                    failure('Upload failed: ' + xhr.statusText);
                }
            };
            
            xhr.onerror = function() {
                failure('Network error during upload');
            };
            
            xhr.send(formData);
        };
        
        config.media_url_resolver = function(data, resolve, reject) {
            resolve({src: data.url});
        };
        
        // Add file picker callback for image uploads
        config.file_picker_callback = function(callback, value, meta) {
            // Handle different types of file uploads
            if (meta.filetype === 'image') {
                // Create file input for images
                const input = document.createElement('input');
                input.setAttribute('type', 'file');
                input.setAttribute('accept', 'image/*');
                
                // When a file is selected
                input.onchange = function() {
                    const file = this.files[0];
                    
                    if (!file) {
                        return;
                    }
                    
                    console.log('Selected image file:', file.name);
                    
                    // Client-side file size validation for images (10MB = 10 * 1024 * 1024 bytes)
                    const maxSize = 10 * 1024 * 1024;
                    if (file.size > maxSize) {
                        const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);
                        alert(`Image too large! The selected image is ${fileSizeMB}MB. Maximum allowed size is 10MB. Please choose a smaller image.`);
                        return;
                    }
                    
                    // Create form data for upload
                    const formData = new FormData();
                    formData.append('file', file);
                    
                    // Upload the image
                    const xhr = new XMLHttpRequest();
                    
                    // Get the upload URL from config or use default
                    const uploadUrl = config.images_upload_url || '/tinymce/upload_image/';
                    console.log('Uploading image to:', uploadUrl);
                    
                    xhr.open('POST', uploadUrl);
                    
                    // Try to get CSRF token from cookie or form
                    const csrfToken = getCsrfToken();
                    if (csrfToken) {
                        console.log('CSRF token found, adding to request');
                        xhr.setRequestHeader('X-CSRFToken', csrfToken);
                    } else {
                        console.warn('No CSRF token found, trying to get from meta tag');
                        // Try to get CSRF token from meta tag
                        const metaToken = document.querySelector('meta[name="csrf-token"]');
                        if (metaToken) {
                            const metaTokenValue = metaToken.getAttribute('content');
                            console.log('Found CSRF token in meta tag:', metaTokenValue ? 'Yes' : 'No');
                            xhr.setRequestHeader('X-CSRFToken', metaTokenValue);
                        } else {
                            console.error('No CSRF token available - upload will likely fail');
                            console.log('Available CSRF sources:', {
                                cookie: document.cookie.includes('csrftoken='),
                                formInput: !!document.querySelector('input[name="csrfmiddlewaretoken"]'),
                                metaTag: !!document.querySelector('meta[name="csrf-token"]'),
                                windowCsrfToken: !!window.csrfToken,
                                windowCSRFToken: !!window.CSRF_TOKEN
                            });
                        }
                    }
                    
                    // Handle response
                    xhr.onload = function() {
                        if (xhr.status === 200) {
                            try {
                                const response = JSON.parse(xhr.responseText);
                                console.log('Upload successful, response:', response);
                                
                                if (response.success) {
                                    // Ensure we have alt and title text from the response or fallback to file name
                                    const altText = response.alt || file.name.replace(/\.[^/.]+$/, "");
                                    const titleText = response.title || file.name.replace(/\.[^/.]+$/, "");
                                    
                                    // Use location or url from response
                                    const imageUrl = response.location || response.url;
                                    
                                    if (imageUrl) {
                                        // Insert the image with alt and title attributes
                                        callback(imageUrl, { 
                                            alt: altText,
                                            title: titleText
                                        });
                                        console.log('Image inserted successfully:', imageUrl);
                                    } else {
                                        console.error('Invalid response: Missing image URL');
                                        alert('Error: Server response missing image URL');
                                    }
                                } else {
                                    console.error('Upload error from server:', response.error || 'Unknown error');
                                    alert('Error uploading image: ' + (response.error || 'Unknown error'));
                                }
                            } catch (e) {
                                console.error('Error parsing upload response:', e);
                                console.error('Response text:', xhr.responseText);
                                alert('Error: Invalid response from server');
                            }
                        } else {
                            console.error('Upload failed:', xhr.status, xhr.statusText);
                            try {
                                const response = JSON.parse(xhr.responseText);
                                console.error('Error details:', response);
                                alert('Upload failed: ' + (response.error || xhr.statusText));
                            } catch (e) {
                                console.error('Raw response:', xhr.responseText);
                                alert('Upload failed: ' + xhr.statusText);
                            }
                        }
                    };
                    
                    xhr.onerror = function() {
                        console.error('Network error during upload');
                        alert('Network error during image upload. Please check your internet connection and try again.');
                    };
                    
                    xhr.send(formData);
                };
                
                input.click();
            } else if (meta.filetype === 'media') {
                // Create file input for media files
                const input = document.createElement('input');
                input.setAttribute('type', 'file');
                input.setAttribute('accept', 'video/*,audio/*,.mp4,.webm,.mp3,.wav,.ogg,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.txt');
                
                // When a file is selected
                input.onchange = function() {
                    const file = this.files[0];
                    
                    if (!file) {
                        return;
                    }
                    
                    console.log('Selected media file:', file.name);
                    
                    // Client-side file size validation based on file type
                    const fileExtension = file.name.split('.').pop().toLowerCase();
                    const videoExtensions = ['mp4', 'mov', 'avi', 'wmv', 'mkv', 'webm', 'flv', 'm4v'];
                    let maxSize, sizeDescription;
                    
                    if (fileExtension === 'zip') {
                        // SCORM packages or archives - allow up to 600MB
                        maxSize = 600 * 1024 * 1024;
                        sizeDescription = '600MB';
                    } else if (videoExtensions.includes(fileExtension)) {
                        // Video files - 600MB limit
                        maxSize = 600 * 1024 * 1024;
                        sizeDescription = '600MB';
                    } else {
                        // Regular media files - 600MB limit
                        maxSize = 600 * 1024 * 1024;
                        sizeDescription = '600MB';
                    }
                    
                    if (file.size > maxSize) {
                        const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);
                        alert(`File too large! The selected file is ${fileSizeMB}MB. Maximum allowed size is ${sizeDescription}. Please choose a smaller file.`);
                        return;
                    }
                    
                    // Create form data for upload
                    const formData = new FormData();
                    formData.append('file', file);
                    
                    // Upload the media file
                    const xhr = new XMLHttpRequest();
                    
                    // Get the upload URL from config or use default
                    const uploadUrl = config.media_upload_url || '/tinymce/upload_media_file/';
                    console.log('Uploading media to:', uploadUrl);
                    
                    xhr.open('POST', uploadUrl);
                    
                    // Try to get CSRF token from cookie or form
                    const csrfToken = getCsrfToken();
                    if (csrfToken) {
                        console.log('CSRF token found, adding to request');
                        xhr.setRequestHeader('X-CSRFToken', csrfToken);
                    } else {
                        console.warn('No CSRF token found, trying to get from meta tag');
                        // Try to get CSRF token from meta tag
                        const metaToken = document.querySelector('meta[name="csrf-token"]');
                        if (metaToken) {
                            const metaTokenValue = metaToken.getAttribute('content');
                            console.log('Found CSRF token in meta tag:', metaTokenValue ? 'Yes' : 'No');
                            xhr.setRequestHeader('X-CSRFToken', metaTokenValue);
                        } else {
                            console.error('No CSRF token available - upload will likely fail');
                            console.log('Available CSRF sources:', {
                                cookie: document.cookie.includes('csrftoken='),
                                formInput: !!document.querySelector('input[name="csrfmiddlewaretoken"]'),
                                metaTag: !!document.querySelector('meta[name="csrf-token"]'),
                                windowCsrfToken: !!window.csrfToken,
                                windowCSRFToken: !!window.CSRF_TOKEN
                            });
                        }
                    }
                    
                    // Handle response
                    xhr.onload = function() {
                        if (xhr.status === 200) {
                            try {
                                const response = JSON.parse(xhr.responseText);
                                console.log('Upload successful, response:', response);
                                
                                if (response.location) {
                                    callback(response.location, { title: file.name, alt: file.name });
                                } else if (response.url) {
                                    callback(response.url, { title: response.filename || file.name, alt: response.filename || file.name });
                                } else {
                                    console.error('Invalid response format, missing location or url:', response);
                                    alert('Upload successful but response format is invalid. Please try again.');
                                }
                            } catch (e) {
                                console.error('Error parsing upload response:', e);
                            }
                        } else {
                            console.error('Upload failed:', xhr.status, xhr.statusText);
                            try {
                                const response = JSON.parse(xhr.responseText);
                                console.error('Error details:', response);
                                alert('Upload failed: ' + (response.error || xhr.statusText));
                            } catch (e) {
                                console.error('Raw response:', xhr.responseText);
                                alert('Upload failed: ' + xhr.statusText);
                            }
                        }
                    };
                    
                    xhr.onerror = function() {
                        console.error('Network error during upload');
                        alert('Network error during media upload. Please check your internet connection and try again.');
                    };
                    
                    xhr.send(formData);
                };
                
                input.click();
            }
        };
        
        // Handle form submission
        config.setup = function(editor) {
            editor.on('change', function() {
                editor.save(); // Save content back to textarea
            });
            
            // Add global file size validation for all file inputs
            editor.on('init', function() {
                // Monitor for any file inputs that get added to the DOM (including by TinyMCE dialogs)
                const addValidationToFileInputs = function() {
                    const allFileInputs = document.querySelectorAll('input[type="file"]:not([data-validation-added])');
                    
                    allFileInputs.forEach(function(input) {
                        // Mark as processed
                        input.setAttribute('data-validation-added', 'true');
                        
                        // Add change listener for file size validation
                        input.addEventListener('change', function() {
                            const file = this.files[0];
                            if (!file) return;
                            
                            let maxSize, fileType;
                            
                            // Determine file type and size limit based on accept attribute or file type
                            if (file.type.startsWith('image/') || this.accept.includes('image')) {
                                maxSize = 10 * 1024 * 1024; // 10MB for images
                                fileType = 'image';
                            } else {
                                // Set max size based on file type
                                const fileExtension = file.name.split('.').pop().toLowerCase();
                                const videoExtensions = ['mp4', 'mov', 'avi', 'wmv', 'mkv', 'webm', 'flv', 'm4v'];
                                if (fileExtension === 'zip') {
                                    maxSize = 600 * 1024 * 1024; // 600MB for SCORM packages/archives
                                    fileType = 'archive';
                                } else if (videoExtensions.includes(fileExtension)) {
                                    maxSize = 600 * 1024 * 1024; // 600MB for video files
                                    fileType = 'video';
                                } else {
                                    maxSize = 600 * 1024 * 1024; // 600MB for media/other files
                                    fileType = 'media file';
                                }
                            }
                            
                            if (file.size > maxSize) {
                                const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);
                                const maxSizeMB = (maxSize / (1024 * 1024)).toFixed(0);
                                
                                alert(`File too large! The selected ${fileType} is ${fileSizeMB}MB. Maximum allowed size is ${maxSizeMB}MB. Please choose a smaller file.`);
                                
                                // Clear the input
                                this.value = '';
                                return false;
                            }
                        });
                    });
                };
                
                // Run validation check when editor loads
                addValidationToFileInputs();
                
                // Monitor for new dialogs/DOM changes
                const observer = new MutationObserver(function(mutations) {
                    let shouldCheck = false;
                    mutations.forEach(function(mutation) {
                        if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                            shouldCheck = true;
                        }
                    });
                    if (shouldCheck) {
                        setTimeout(addValidationToFileInputs, 100);
                    }
                });
                
                // Start observing
                observer.observe(document.body, { childList: true, subtree: true });
            });
            
            // Ensure content is saved when form is submitted
            const form = textarea.closest('form');
            if (form) {
                form.addEventListener('submit', function() {
                    editor.save();
                });
            }
            
            // Add error handling for focus operations to prevent getRng errors
            editor.on('focus', function() {
                try {
                    // Ensure selection is available before any focus operations
                    if (editor.selection && editor.selection.getRng) {
                        // Selection is available, safe to perform focus operations
                        console.log(`Editor ${editor.id} focused successfully`);
                    }
                } catch (error) {
                    console.warn(`Focus error in editor ${editor.id}:`, error);
                }
            });
            
            // Add error handling for editor commands
            const originalExecCommand = editor.execCommand;
            editor.execCommand = function(cmd, ui, value) {
                try {
                    // Check if command involves selection operations
                    if (cmd === 'mceFocus' || cmd === 'mceResize') {
                        // Ensure editor is properly initialized
                        if (!editor.initialized || !editor.selection) {
                            console.warn(`Cannot execute ${cmd} - editor not properly initialized`);
                            return false;
                        }
                    }
                    return originalExecCommand.call(this, cmd, ui, value);
                } catch (error) {
                    console.warn(`Error executing command ${cmd}:`, error);
                    return false;
                }
            };
        };

        // Initialize TinyMCE
        if (typeof tinymce === 'undefined') {
            console.error('TinyMCE is not loaded yet');
            return;
        }
        
        tinymce.init(config).then(function(editors) {
            if (editors.length > 0) {
                initializedEditors.add(textarea.id);
                console.log('TinyMCE initialized for:', textarea.id);
            }
        }).catch(function(error) {
            console.error('Failed to initialize TinyMCE:', error);
        });
    }

    /**
     * Get CSRF token from cookie
     * @returns {string|null} CSRF token or null if not found
     */
    function getCsrfToken() {
        // Try to get from cookie
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='));
            
        if (cookieValue) {
            return cookieValue.split('=')[1];
        }
        
        // Try to get from form input
        const tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (tokenInput) {
            return tokenInput.value;
        }
        
        // For Django >= 4.0, check for the CSRF token in the DOM
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrfToken) {
            return csrfToken.value;
        }
        
        // Try to get from meta tag
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        if (metaToken) {
            return metaToken.getAttribute('content');
        }
        
        // Try to get from Django's CSRF token in window object
        if (window.csrfToken) {
            return window.csrfToken;
        }
        
        // Try to get from window.CSRF_TOKEN (set by base template)
        if (window.CSRF_TOKEN) {
            return window.CSRF_TOKEN;
        }
        
        // Last resort: try to get from Django's CSRF token function
        if (typeof getCookie === 'function') {
            return getCookie('csrftoken');
        }
        
        return null;
    }
    
    /**
     * Helper function to get cookie value (Django's getCookie function)
     */
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * Initialize all TinyMCE editors on the page
     */
    function initializeAllEditors() {
        if (typeof tinymce === 'undefined') {
            retryAttempts++;
            if (retryAttempts <= MAX_RETRY_ATTEMPTS) {
                if (retryAttempts === 1 || retryAttempts === MAX_RETRY_ATTEMPTS) {
                    // Only log first and last attempt to reduce console noise
                    console.warn(`TinyMCE not loaded yet, retrying in 100ms... (Attempt ${retryAttempts}/${MAX_RETRY_ATTEMPTS})`);
                }
                setTimeout(initializeAllEditors, 100);
            } else {
                console.log('TinyMCE not available, attempting dynamic load');
                // Try to load TinyMCE dynamically as a fallback
                loadTinyMCEDynamically();
            }
            return;
        }
        
        // Reset retry attempts when TinyMCE is available
        retryAttempts = 0;
        
        const textareas = document.querySelectorAll('textarea.tinymce-editor');
        textareas.forEach(function(textarea) {
            // Ensure textarea has an ID
            if (!textarea.id) {
                textarea.id = 'tinymce-' + Math.random().toString(36).substr(2, 9);
            }
            
            initializeTinyMCE(textarea);
        });
    }

    /**
     * Try to load TinyMCE dynamically as a fallback
     */
    function loadTinyMCEDynamically() {
        // First clean up any existing scripts that might be causing errors
        const existingScripts = document.querySelectorAll('script[src*="tinymce"]');
        existingScripts.forEach(script => {
            script.parentNode.removeChild(script);
        });
        
        const script = document.createElement('script');
        script.src = '/static/tinymce_editor/tinymce/tinymce.min.js';
        script.async = true;
        script.defer = true;
        
        script.onload = function() {
            console.log('TinyMCE loaded dynamically');
            // Set default license key for all TinyMCE instances
            if (typeof tinymce !== 'undefined') {
                tinymce.defaultSettings = tinymce.defaultSettings || {};
                tinymce.defaultSettings.license_key = 'gpl';
            }
            retryAttempts = 0; // Reset retry attempts
            setTimeout(initializeAllEditors, 100);
        };
        
        script.onerror = function(error) {
            console.error('Failed to load TinyMCE dynamically:', error);
            // Alert the user that there's an issue
            if (typeof alert === 'function') {
                alert('There was an error loading the editor. Please try refreshing the page.');
            }
        };
        
        document.head.appendChild(script);
    }

    /**
     * Destroy TinyMCE editor
     * @param {string} editorId - The ID of the editor to destroy
     */
    function destroyEditor(editorId) {
        if (typeof tinymce === 'undefined') {
            console.warn('TinyMCE not available for destroying editor:', editorId);
            return;
        }
        
        const editor = tinymce.get(editorId);
        if (editor) {
            editor.destroy();
            initializedEditors.delete(editorId);
        }
    }

    /**
     * Reinitialize editors (useful for AJAX content)
     */
    function reinitializeEditors() {
        if (typeof tinymce === 'undefined') {
            console.warn('TinyMCE not available for reinitializing editors');
            return;
        }
        
        // Remove any destroyed editors from our tracking
        initializedEditors.forEach(function(editorId) {
            if (!tinymce.get(editorId)) {
                initializedEditors.delete(editorId);
            }
        });
        
        // Initialize new editors
        retryAttempts = 0; // Reset retry attempts
        initializeAllEditors();
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeAllEditors);
    } else {
        initializeAllEditors();
    }

    // Handle Django admin inline forms
    if (typeof django !== 'undefined' && django.jQuery) {
        django.jQuery(document).on('formset:added', function(event, $row) {
            // Wait a bit for the DOM to be ready
            setTimeout(function() {
                const textareas = $row.find('textarea.tinymce-editor');
                textareas.each(function() {
                    if (!this.id) {
                        this.id = 'tinymce-' + Math.random().toString(36).substr(2, 9);
                    }
                    initializeTinyMCE(this);
                });
            }, 100);
        });

        django.jQuery(document).on('formset:removed', function(event, $row) {
            const textareas = $row.find('textarea.tinymce-editor');
            textareas.each(function() {
                if (this.id) {
                    destroyEditor(this.id);
                }
            });
        });
    }

    // Expose functions globally for manual control
    window.TinyMCEWidget = {
        initialize: initializeTinyMCE,
        initializeAll: initializeAllEditors,
        destroy: destroyEditor,
        reinitialize: reinitializeEditors,
        loadDynamically: loadTinyMCEDynamically
    };

})(); 