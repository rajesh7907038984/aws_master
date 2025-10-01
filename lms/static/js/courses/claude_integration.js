// Claude AI integration for course description editor
let CLAUDE_API_KEY = ""; // This will be set from the template

/**
 * Initialize Claude AI integration with the course description editor
 * @param {string} apiKey - Claude API key
 * @param {HTMLElement} editor - The editor element
 * @param {HTMLElement} hiddenInput - The hidden input field for storing editor content
 */
function initClaudeAI(apiKey, editor, hiddenInput) {
    if (!apiKey || !editor || !hiddenInput) {
        console.error('Missing required parameters for Claude AI integration');
        return;
    }

    CLAUDE_API_KEY = apiKey;
    
    // Create the AI button and add it to the toolbar
    const toolbar = document.querySelector('.custom-editor-toolbar');
    if (!toolbar) {
        console.error('Could not find editor toolbar');
        return;
    }
    
    // Create AI button
    const aiButton = document.createElement('button');
    aiButton.type = 'button';
    aiButton.title = 'Generate with AI';
    aiButton.innerHTML = '<i class="fas fa-robot"></i>';
    aiButton.className = 'ai-generate-btn';
    aiButton.style.backgroundColor = '#5436DA'; // Claude purple
    aiButton.style.color = 'white';
    
    // Add AI button to toolbar
    toolbar.appendChild(aiButton);
    
    // Add click event listener to the AI button
    aiButton.addEventListener('click', () => {
        showAIPromptModal(editor, hiddenInput);
    });
}

/**
 * Show modal dialog for entering an AI prompt
 * @param {HTMLElement} editor - The editor element
 * @param {HTMLElement} hiddenInput - The hidden input field
 */
function showAIPromptModal(editor, hiddenInput) {
    // Create modal backdrop
    const backdrop = document.createElement('div');
    backdrop.className = 'ai-modal-backdrop';
    backdrop.style.position = 'fixed';
    backdrop.style.top = '0';
    backdrop.style.left = '0';
    backdrop.style.width = '100%';
    backdrop.style.height = '100%';
    backdrop.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
    backdrop.style.zIndex = '9999';
    backdrop.style.display = 'flex';
    backdrop.style.justifyContent = 'center';
    backdrop.style.alignItems = 'center';
    
    // Create modal container
    const modal = document.createElement('div');
    modal.className = 'ai-modal';
    modal.style.backgroundColor = 'white';
    modal.style.borderRadius = '8px';
    modal.style.padding = '20px';
    modal.style.width = '90%';
    modal.style.maxWidth = '600px';
    modal.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';
    modal.style.display = 'flex';
    modal.style.flexDirection = 'column';
    modal.style.gap = '15px';
    
    // Create modal header
    const header = document.createElement('div');
    header.className = 'ai-modal-header';
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';
    
    const title = document.createElement('h3');
    title.textContent = 'Generate with Claude AI';
    title.style.margin = '0';
    title.style.fontSize = '18px';
    title.style.fontWeight = '600';
    
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '&times;';
    closeBtn.style.background = 'none';
    closeBtn.style.border = 'none';
    closeBtn.style.fontSize = '24px';
    closeBtn.style.cursor = 'pointer';
    closeBtn.style.padding = '0';
    closeBtn.style.lineHeight = '1';
    closeBtn.style.color = '#666';
    
    header.appendChild(title);
    header.appendChild(closeBtn);
    
    // Create modal content
    const content = document.createElement('div');
    content.className = 'ai-modal-content';
    
    // Create prompt textarea
    const promptLabel = document.createElement('label');
    promptLabel.htmlFor = 'ai-prompt';
    promptLabel.textContent = 'What kind of content would you like Claude to generate?';
    promptLabel.style.display = 'block';
    promptLabel.style.marginBottom = '5px';
    promptLabel.style.fontWeight = '500';
    
    const promptInput = document.createElement('textarea');
    promptInput.id = 'ai-prompt';
    promptInput.placeholder = 'E.g., "Write a comprehensive course description for a beginner Python programming course" or "Create a list of learning objectives for a digital marketing course"';
    promptInput.rows = 4;
    promptInput.style.width = '100%';
    promptInput.style.padding = '10px';
    promptInput.style.borderRadius = '4px';
    promptInput.style.border = '1px solid #ddd';
    promptInput.style.resize = 'vertical';
    
    // Create options section
    const optionsDiv = document.createElement('div');
    optionsDiv.className = 'ai-options';
    optionsDiv.style.marginTop = '10px';
    
    // Create option to replace or append
    const replaceOption = document.createElement('div');
    replaceOption.className = 'ai-option';
    
    const replaceRadio = document.createElement('input');
    replaceRadio.type = 'radio';
    replaceRadio.name = 'ai-insertion-mode';
    replaceRadio.id = 'ai-replace';
    replaceRadio.value = 'replace';
    replaceRadio.checked = true;
    
    const replaceLabel = document.createElement('label');
    replaceLabel.htmlFor = 'ai-replace';
    replaceLabel.textContent = 'Replace current content';
    replaceLabel.style.marginLeft = '5px';
    
    replaceOption.appendChild(replaceRadio);
    replaceOption.appendChild(replaceLabel);
    
    const appendOption = document.createElement('div');
    appendOption.className = 'ai-option';
    appendOption.style.marginTop = '5px';
    
    const appendRadio = document.createElement('input');
    appendRadio.type = 'radio';
    appendRadio.name = 'ai-insertion-mode';
    appendRadio.id = 'ai-append';
    appendRadio.value = 'append';
    
    const appendLabel = document.createElement('label');
    appendLabel.htmlFor = 'ai-append';
    appendLabel.textContent = 'Append to current content';
    appendLabel.style.marginLeft = '5px';
    
    appendOption.appendChild(appendRadio);
    appendOption.appendChild(appendLabel);
    
    optionsDiv.appendChild(replaceOption);
    optionsDiv.appendChild(appendOption);
    
    // Add content to modal
    content.appendChild(promptLabel);
    content.appendChild(promptInput);
    content.appendChild(optionsDiv);
    
    // Create status div for showing loading and errors
    const statusDiv = document.createElement('div');
    statusDiv.className = 'ai-status';
    statusDiv.style.display = 'none';
    statusDiv.style.padding = '10px';
    statusDiv.style.borderRadius = '4px';
    statusDiv.style.marginTop = '10px';
    
    // Create footer with action buttons
    const footer = document.createElement('div');
    footer.className = 'ai-modal-footer';
    footer.style.display = 'flex';
    footer.style.justifyContent = 'flex-end';
    footer.style.gap = '10px';
    footer.style.marginTop = '10px';
    
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.style.backgroundColor = '#f3f4f6';
    cancelBtn.style.border = '1px solid #d1d5db';
    cancelBtn.style.color = '#374151';
    cancelBtn.style.padding = '8px 16px';
    cancelBtn.style.borderRadius = '4px';
    cancelBtn.style.cursor = 'pointer';
    
    const generateBtn = document.createElement('button');
    generateBtn.textContent = 'Generate';
    generateBtn.className = 'btn btn-primary';
    generateBtn.style.backgroundColor = '#5436DA';
    generateBtn.style.border = 'none';
    generateBtn.style.color = 'white';
    generateBtn.style.padding = '8px 16px';
    generateBtn.style.borderRadius = '4px';
    generateBtn.style.cursor = 'pointer';
    
    footer.appendChild(cancelBtn);
    footer.appendChild(generateBtn);
    
    // Assemble modal
    modal.appendChild(header);
    modal.appendChild(content);
    modal.appendChild(statusDiv);
    modal.appendChild(footer);
    backdrop.appendChild(modal);
    
    // Add to body
    document.body.appendChild(backdrop);
    
    // Focus the prompt input
    promptInput.focus();
    
    // Close modal when backdrop is clicked
    backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) {
            document.body.removeChild(backdrop);
        }
    });
    
    // Close modal when close button is clicked
    closeBtn.addEventListener('click', () => {
        document.body.removeChild(backdrop);
    });
    
    // Close modal when cancel button is clicked
    cancelBtn.addEventListener('click', () => {
        document.body.removeChild(backdrop);
    });
    
    // Handle generate button click
    generateBtn.addEventListener('click', async () => {
        const prompt = promptInput.value.trim();
        if (!prompt) {
            showStatus(statusDiv, 'Please enter a prompt for Claude AI', 'error');
            return;
        }
        
        // Get insertion mode
        const insertionMode = document.querySelector('input[name="ai-insertion-mode"]:checked').value;
        
        // Show loading indicator
        showStatus(statusDiv, 'Generating content with Claude AI...', 'loading');
        
        // Disable generate button
        generateBtn.disabled = true;
        generateBtn.textContent = 'Generating...';
        
        try {
            const generatedContent = await generateWithClaudeAI(prompt);
            
            // Update editor content
            if (insertionMode === 'replace') {
                editor.innerHTML = generatedContent;
            } else {
                editor.innerHTML += '<br>' + generatedContent;
            }
            
            // Update hidden input
            if (hiddenInput) {
                hiddenInput.value = JSON.stringify({
                    delta: {},
                    html: editor.innerHTML
                });
            }
            
            // Close modal
            document.body.removeChild(backdrop);
            
        } catch (error) {
            console.error('Error generating content with Claude AI:', error);
            showStatus(statusDiv, 'Error generating content: ' + error.message, 'error');
            
            // Re-enable generate button
            generateBtn.disabled = false;
            generateBtn.textContent = 'Generate';
        }
    });
}

/**
 * Show status message in the modal
 * @param {HTMLElement} statusDiv - The status div element
 * @param {string} message - The message to display
 * @param {string} type - The type of message (loading or error)
 */
function showStatus(statusDiv, message, type) {
    statusDiv.textContent = message;
    statusDiv.style.display = 'block';
    
    if (type === 'loading') {
        statusDiv.style.backgroundColor = '#e0f2fe';
        statusDiv.style.color = '#0369a1';
        statusDiv.style.border = '1px solid #bae6fd';
    } else if (type === 'error') {
        statusDiv.style.backgroundColor = '#fee2e2';
        statusDiv.style.color = '#b91c1c';
        statusDiv.style.border = '1px solid #fecaca';
    }
}

/**
 * Generate content with Claude AI
 * @param {string} prompt - The prompt to send to Claude AI
 * @returns {Promise<string>} - The generated HTML content
 */
async function generateWithClaudeAI(prompt) {
    try {
        console.log('Sending request to Claude AI proxy with key:', CLAUDE_API_KEY.substring(0, 10) + '...');
        
        // Get CSRF token
        const csrfToken = getCsrfToken();
        
        const response = await fetch('/courses/api/claude-ai-proxy/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Claude-API-Key': CLAUDE_API_KEY
            },
            body: JSON.stringify({
                model: 'claude-3-haiku-20240307',
                max_tokens: 1024,
                messages: [
                    {
                        role: 'user',
                        content: prompt
                    }
                ]
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Claude API error response:', errorText);
            
            try {
                const errorData = JSON.parse(errorText);
                // Check for credit balance errors
                if (errorData.error?.message?.includes('credit balance')) {
                    throw new Error('Insufficient Claude API credits. Please check your account at https://console.anthropic.com/settings/billing');
                } else if (errorData.error?.message) {
                    throw new Error(errorData.error.message);
                } else {
                    throw new Error('Failed to generate content');
                }
            } catch (parseError) {
                // If we couldn't parse the JSON or the error wasn't in the expected format
                if (errorText.includes('credit balance')) {
                    throw new Error('Insufficient Claude API credits. Please check your account at https://console.anthropic.com/settings/billing');
                } else {
                    throw new Error(`API error (${response.status}): ${errorText.substring(0, 100)}`);
                }
            }
        }

        const data = await response.json();
        console.log('Claude API response:', data);
        return data.content[0].text;
    } catch (error) {
        console.error('Error calling Claude API:', error);
        throw error;
    }
}

/**
 * Get CSRF token from cookies
 * @returns {string} - CSRF token
 */
function getCsrfToken() {
    const name = 'csrftoken';
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(';').shift();
    }
    return '';
}

// Export functions for use in other scripts
window.ClaudeAI = {
    init: initClaudeAI,
    generate: generateWithClaudeAI
}; 