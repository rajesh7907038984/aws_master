/**
 * TinyMCE JSON Content Handler
 * Utility functions for handling JSON content in TinyMCE editors
 */

(function() {
    'use strict';
    
    // Store initialized content fields
    let processedContentFields = new Set();
    
    /**
     * Parse JSON content from a field
     * @param {string|object} rawContent - The raw content (JSON string or object)
     * @returns {string} - The HTML content to display in the editor
     */
    function parseContentJson(rawContent) {
        if (!rawContent) return '';
        
        try {
            // If it's already an object, stringify it first to ensure consistent handling
            if (typeof rawContent === 'object') {
                rawContent = JSON.stringify(rawContent);
            }
            
            // Parse the JSON content
            const contentData = JSON.parse(rawContent);
            
            // Return the HTML content if available
            if (contentData && contentData.html) {
                let htmlContent = contentData.html;
                
                // Fix malformed image URLs with extra quotes and slashes
                htmlContent = htmlContent.replace(/src="([^"]*)""/g, 'src="$1"');
                htmlContent = htmlContent.replace(/src="([^"]*)\/""/g, 'src="$1"');
                
                // Fix relative paths to media files
                htmlContent = htmlContent.replace(/src="\.\.\/\.\.\/media\//g, 'src="/media/');
                
                // Fix image URLs with wrong domain or protocol
                htmlContent = htmlContent.replace(/src="(https?:)?\/\/localhost:[0-9]+\/media\//g, 'src="/media/');
                htmlContent = htmlContent.replace(/src="(https?:)?\/\/127\.0\.0\.1:[0-9]+\/media\//g, 'src="/media/');
                
                // Make sure image URLs are properly formed
                htmlContent = htmlContent.replace(/<img([^>]*)src="([^"]*)"([^>]*)>/g, function(match, before, src, after) {
                    // Clean the URL
                    src = src.trim();
                    
                    // Ensure URL has proper protocol if it's a relative URL
                    if (src && !src.match(/^(https?:)?\/\//) && !src.startsWith('/')) {
                        src = '/' + src;
                    }
                    
                    return '<img' + before + 'src="' + src + '"' + after + '>';
                });
                
                return htmlContent;
            } else {
                return rawContent; // Fallback to raw content if no HTML property
            }
        } catch (e) {
            console.warn('Error parsing JSON content:', e);
            console.log('Raw content was:', rawContent);
            return rawContent; // Return original content on error
        }
    }
    
    /**
     * Create JSON content structure
     * @param {string} htmlContent - The HTML content from the editor
     * @returns {string} - Stringified JSON object with delta and html properties
     */
    function createContentJson(htmlContent) {
        // Clean up any malformed image URLs before storing
        if (htmlContent) {
            htmlContent = htmlContent.replace(/src="([^"]*)""/g, 'src="$1"');
            htmlContent = htmlContent.replace(/src="([^"]*)\/""/g, 'src="$1"');
            htmlContent = htmlContent.replace(/src="\.\.\/\.\.\/media\//g, 'src="/media/');
            
            // Fix image URLs with wrong domain or protocol
            htmlContent = htmlContent.replace(/src="(https?:)?\/\/localhost:[0-9]+\/media\//g, 'src="/media/');
            htmlContent = htmlContent.replace(/src="(https?:)?\/\/127\.0\.0\.1:[0-9]+\/media\//g, 'src="/media/');
            
            // Fix relative URLs in images
            htmlContent = htmlContent.replace(/<img([^>]*)src="([^"]*)"([^>]*)>/g, function(match, before, src, after) {
                // Clean the URL
                src = src.trim();
                
                // Ensure URL has proper protocol if it's a relative URL
                if (src && !src.match(/^(https?:)?\/\//) && !src.startsWith('/')) {
                    src = '/' + src;
                }
                
                return '<img' + before + 'src="' + src + '"' + after + '>';
            });
        }
        
        const jsonData = {
            delta: {},
            html: htmlContent
        };
        return JSON.stringify(jsonData);
    }
    
    /**
     * Process a TinyMCE editor field that contains JSON content
     * @param {HTMLElement} textareaElement - The textarea element to process
     */
    function processJsonContentField(textareaElement) {
        if (!textareaElement || processedContentFields.has(textareaElement.id)) {
            return; // Already processed or invalid element
        }
        
        // Get the raw content
        const rawContent = textareaElement.value;
        
        // Parse the content and update the textarea
        try {
            const parsedContent = parseContentJson(rawContent);
            textareaElement.value = parsedContent;
            processedContentFields.add(textareaElement.id);
            console.log(`Processed JSON content for ${textareaElement.id}`);
        } catch (e) {
            console.error(`Error processing JSON content for ${textareaElement.id}:`, e);
        }
    }
    
    /**
     * Setup form submission handler to convert HTML back to JSON
     * @param {HTMLFormElement} formElement - The form element
     * @param {Array} editorIds - Array of editor IDs to process
     */
    function setupFormSubmissionHandler(formElement, editorIds) {
        if (!formElement || !editorIds || !editorIds.length) {
            return;
        }
        
        formElement.addEventListener('submit', function(e) {
            if (typeof tinymce === 'undefined') {
                return; // TinyMCE not available
            }
            
            editorIds.forEach(function(editorId) {
                const editor = tinymce.get(editorId);
                if (editor) {
                    const htmlContent = editor.getContent();
                    const jsonContent = createContentJson(htmlContent);
                    
                    const inputElement = document.getElementById(editorId);
                    if (inputElement) {
                        inputElement.value = jsonContent;
                    }
                }
            });
        });
    }
    
    // Expose functions globally
    window.TinyMCEJsonHandler = {
        parseContentJson: parseContentJson,
        createContentJson: createContentJson,
        processJsonContentField: processJsonContentField,
        setupFormSubmissionHandler: setupFormSubmissionHandler
    };
})(); 