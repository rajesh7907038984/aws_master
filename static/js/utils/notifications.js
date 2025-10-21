/**
 * Utilities for showing notifications and toasts in the application
 */

/**
 * Show a toast notification
 * @param {string} message - The message to display in the toast
 * @param {string} type - Type of toast: 'success', 'error', 'warning', or 'info'
 * @param {number} duration - How long the toast should stay visible (ms)
 */
function showToast(message, type = 'success', duration = 3000) {
    try {
        // Ensure document.body exists
        if (!document.body) {
            return;
        }
        
        // Remove any existing toasts and unified notifications
        const existingToasts = document.querySelectorAll('.toast-notification, .unified-notification, .topic-notification');
        existingToasts.forEach(toast => {
            try {
                toast.remove();
            } catch (err) {
                console.warn('Failed to remove existing toast:', err);
            }
        });
        
        // Create toast element
        const toast = document.createElement('div');
        if (!toast) {
            return;
        }
        
        toast.className = `toast-notification fixed top-4 right-4 p-4 rounded-lg shadow-lg text-white transition-opacity duration-300 ease-in-out`;
        toast.style.zIndex = '100200';
        
        // Set background color based on type
        switch (type) {
            case 'success':
                toast.classList.add('bg-green-500');
                break;
            case 'error':
                toast.classList.add('bg-red-500');
                break;
            case 'warning':
                toast.classList.add('bg-yellow-500');
                break;
            case 'info':
            default:
                toast.classList.add('bg-blue-500');
                break;
        }
        
        // Add message - safely set text content
        if (message !== null && message !== undefined) {
            try {
                toast.textContent = message;
            } catch (err) {
                console.warn('Failed to set toast text content, using fallback:', err);
                // Fallback method
                toast.innerHTML = '';
                const textNode = document.createTextNode(String(message));
                toast.appendChild(textNode);
            }
        } else {
            // Default message if none provided
            toast.textContent = 'Notification';
        }
        
        // Add to document
        try {
            document.body.appendChild(toast);
        } catch (err) {
            console.error('Failed to append toast to document body:', err);
            return;
        }
        
        // Fade in effect
        setTimeout(() => {
            if (toast) {
                try {
                    toast.classList.add('opacity-100');
                } catch (err) {
                    console.warn('Failed to add opacity class to toast:', err);
                }
            }
        }, 10);
        
        // Remove after duration
        setTimeout(() => {
            if (!toast) return;
            
            // Fade out
            try {
                toast.classList.add('opacity-0');
            } catch (err) {
                console.warn('Failed to fade out toast, attempting direct removal:', err);
                // Try direct removal if fade fails
                try {
                    toast.remove();
                } catch (innerErr) {
                    console.error('Failed to remove toast directly:', innerErr);
                }
                return;
            }
            
            // Remove from DOM after transition
            setTimeout(() => {
                if (toast) {
                    try {
                        toast.remove();
                    } catch (err) {
                        console.warn('Failed to remove toast after transition:', err);
                    }
                }
            }, 300);
        }, duration);
    } catch (err) {
        console.error('Critical error in showToast function:', err);
    }
}

/**
 * Show a modal dialog
 * @param {Object} options - The options for the modal
 * @param {string} options.title - The title of the modal
 * @param {string} options.content - The HTML content of the modal
 * @param {Array} options.buttons - Array of button objects: {text, type, onClick}
 */
function showModal(options) {
    // Remove any existing modals
    const existingModals = document.querySelectorAll('.modal-overlay');
    existingModals.forEach(modal => modal.remove());
    
    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
    
    // Create modal element
    const modal = document.createElement('div');
    modal.className = 'modal-container bg-white rounded-lg shadow-xl max-w-md w-full mx-4 overflow-hidden transform transition-transform scale-95 opacity-0';
    
    // Build modal content safely
    const title = options.title || 'Confirmation';
    const content = options.content || '';
    const buttons = buildModalButtons(options.buttons || []);
    
    // Create elements safely to prevent XSS
    const header = document.createElement('div');
    header.className = 'modal-header border-b p-4';
    const titleEl = document.createElement('h3');
    titleEl.className = 'text-lg font-medium text-gray-900';
    titleEl.textContent = title;
    header.appendChild(titleEl);
    
    const contentEl = document.createElement('div');
    contentEl.className = 'modal-content p-4';
    contentEl.textContent = content;
    
    const footer = document.createElement('div');
    footer.className = 'modal-footer border-t p-4 flex justify-end space-x-3';
    footer.innerHTML = buttons; // This is safe as buildModalButtons returns sanitized HTML
    
    modal.appendChild(header);
    modal.appendChild(contentEl);
    modal.appendChild(footer);
    
    // Add to document
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Add event listener to close on background click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeModal();
        }
    });
    
    // Add keyboard listener to close on Escape
    const keyHandler = (e) => {
        if (e.key === 'Escape') {
            closeModal();
        }
    };
    document.addEventListener('keydown', keyHandler);
    
    // Animation in
    setTimeout(() => {
        modal.classList.remove('scale-95', 'opacity-0');
        modal.classList.add('scale-100', 'opacity-100');
    }, 10);
    
    // Add click handlers to buttons
    options.buttons?.forEach((button, index) => {
        const buttonEl = modal.querySelector('.modal-button-' + index);
        if (buttonEl && button.onClick) {
            buttonEl.addEventListener('click', () => {
                button.onClick();
                closeModal();
            });
        }
    });
    
    // Close function
    function closeModal() {
        // Animation out
        modal.classList.remove('scale-100', 'opacity-100');
        modal.classList.add('scale-95', 'opacity-0');
        overlay.classList.add('bg-opacity-0');
        
        // Remove from DOM after transition
        setTimeout(() => {
            overlay.remove();
            document.removeEventListener('keydown', keyHandler);
        }, 300);
    }
}

/**
 * Build HTML for modal buttons
 * @param {Array} buttons - Array of button objects
 * @returns {string} - HTML for buttons
 */
function buildModalButtons(buttons) {
    if (!buttons || buttons.length === 0) {
        // Default OK button
        return `<button class="modal-button-0 px-4 py-2 text-white rounded-md transition-colors bg-indigo-900 hover:bg-indigo-800">OK</button>`;
    }
    
    return buttons.map((button, index) => {
        let classes = 'modal-button-' + index + ' px-4 py-2 rounded-md transition-colors';
        
        // Apply styles based on button type
        switch (button.type) {
            case 'primary':
                classes += ' text-white';
                button.style = 'background-color: var(--brand-primary);';
                button.onmouseover = "this.style.backgroundColor='#141a4a'";
                button.onmouseout = "this.style.backgroundColor='var(--brand-primary)'";
                break;
            case 'danger':
                classes += ' bg-red-600 text-white hover:bg-red-700';
                break;
            case 'success':
                classes += ' bg-green-600 text-white hover:bg-green-700';
                break;
            case 'warning':
                classes += ' bg-yellow-600 text-white hover:bg-yellow-700';
                break;
            case 'secondary':
            default:
                classes += ' bg-gray-200 text-gray-800 hover:bg-gray-300';
                break;
        }
        
        const buttonText = button.text || 'Button';
        return '<button class="' + classes + '">' + buttonText + '</button>';
    }).join('');
}

/**
 * Show a notification (alias for showToast for backward compatibility)
 * @param {string} message - The message to display
 * @param {string} type - Type of notification: 'success', 'error', 'warning', or 'info'
 * @param {number} duration - How long the notification should stay visible (ms)
 */
function showNotification(message, type = 'success', duration = 3000) {
    return showToast(message, type, duration);
}

// Expose functions globally
window.showToast = showToast;
window.showModal = showModal;
window.showNotification = showNotification; 