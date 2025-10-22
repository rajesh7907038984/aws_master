// This script adds color picker functionality to the course description editor
window.addEventListener('load', function() {
    console.log('Initializing improved color picker...');
    
    // Get references to the buttons and editor
    const textColorBtn = document.getElementById('text-color-btn');
    const bgColorBtn = document.getElementById('bg-color-btn');
    const editor = document.getElementById('custom-description-editor');
    const hiddenInput = document.getElementById('description-input');
    
    if (!textColorBtn || !bgColorBtn || !editor || !hiddenInput) {
        console.error('Missing required elements for color picker');
        return;
    }
    
    // Color palette
    const colors = [
        '#000000', '#434343', '#666666', '#999999', '#cccccc', '#ffffff',
        '#ff0000', '#ff8000', '#ffff00', '#80ff00', '#00ff00', '#00ff80', 
        '#00ffff', '#0080ff', '#0000ff', '#8000ff', '#ff00ff', '#ff0080',
        '#f4cccc', '#fce5cd', '#fff2cc', '#d9ead3', '#d0e0e3', '#cfe2f3'
    ];
    
    // Remove any existing event listeners by cloning and replacing
    const newTextColorBtn = textColorBtn.cloneNode(true);
    textColorBtn.parentNode.replaceChild(newTextColorBtn, textColorBtn);
    
    const newBgColorBtn = bgColorBtn.cloneNode(true);
    bgColorBtn.parentNode.replaceChild(newBgColorBtn, bgColorBtn);
    
    // Add our event listener for text color
    newTextColorBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        // Create and show color picker for text
        showColorPicker(newTextColorBtn, function(color) {
            applyTextColor(color);
            newTextColorBtn.style.borderBottom = `3px solid ${color}`;
        });
    });
    
    // Add our event listener for background color
    newBgColorBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        // Create and show color picker for background
        showColorPicker(newBgColorBtn, function(color) {
            applyBackgroundColor(color);
            newBgColorBtn.style.borderBottom = `3px solid ${color}`;
        });
    });
    
    // Function to show color picker
    function showColorPicker(button, callback) {
        // Remove any existing pickers
        removeColorPickers();
        
        // Create color picker
        const picker = document.createElement('div');
        picker.className = 'color-picker-popup';
        picker.style.position = 'absolute';
        picker.style.zIndex = '99999';
        picker.style.background = 'white';
        picker.style.border = '1px solid #ccc';
        picker.style.borderRadius = '4px';
        picker.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        picker.style.padding = '8px';
        picker.style.display = 'grid';
        picker.style.gridTemplateColumns = 'repeat(6, 1fr)';
        picker.style.gap = '4px';
        
        // Add color swatches
        colors.forEach(color => {
            const swatch = document.createElement('div');
            swatch.style.width = '20px';
            swatch.style.height = '20px';
            swatch.style.backgroundColor = color;
            swatch.style.border = '1px solid #ddd';
            swatch.style.borderRadius = '2px';
            swatch.style.cursor = 'pointer';
            swatch.title = color;
            
            // Hover effects
            swatch.addEventListener('mouseover', () => {
                swatch.style.transform = 'scale(1.2)';
                swatch.style.boxShadow = '0 0 5px rgba(0,0,0,0.2)';
                swatch.style.transition = 'all 0.1s ease';
            });
            
            swatch.addEventListener('mouseout', () => {
                swatch.style.transform = 'scale(1)';
                swatch.style.boxShadow = 'none';
            });
            
            // Click to apply color
            swatch.addEventListener('click', () => {
                callback(color);
                removeColorPickers();
            });
            
            picker.appendChild(swatch);
        });
        
        // Position the picker
        const rect = button.getBoundingClientRect();
        picker.style.top = (rect.bottom + window.scrollY + 5) + 'px';
        picker.style.left = (rect.left + window.scrollX) + 'px';
        
        // Add to DOM
        document.body.appendChild(picker);
        
        // Close when clicking outside
        setTimeout(() => {
            document.addEventListener('click', function closeHandler(e) {
                if (!picker.contains(e.target) && e.target !== button) {
                    removeColorPickers();
                    document.removeEventListener('click', closeHandler);
                }
            });
        }, 10);
    }
    
    // Function to remove color pickers
    function removeColorPickers() {
        const pickers = document.querySelectorAll('.color-picker-popup');
        pickers.forEach(picker => {
            if (picker && picker.parentNode) {
                picker.parentNode.removeChild(picker);
            }
        });
    }
    
    // Function to apply text color
    function applyTextColor(color) {
        // Focus the editor
        editor.focus();
        
        // Save current selection
        const selection = saveSelection();
        
        // Apply the color
        if (selection) {
            restoreSelection(selection);
            
            try {
                document.execCommand('foreColor', false, color);
                console.log('Text color applied:', color);
            } catch (e) {
                console.error('Error applying text color:', e);
            }
            
            // Update the hidden input
            updateHiddenInput();
        } else {
            console.log('No selection, creating a default one');
            // If no selection, select all content and apply
            selectAllContent();
            document.execCommand('foreColor', false, color);
            updateHiddenInput();
        }
    }
    
    // Function to apply background color
    function applyBackgroundColor(color) {
        // Focus the editor
        editor.focus();
        
        // Save current selection
        const selection = saveSelection();
        
        // Apply the color
        if (selection) {
            restoreSelection(selection);
            
            try {
                document.execCommand('hiliteColor', false, color);
                console.log('Background color applied:', color);
            } catch (e) {
                console.error('Error applying background color:', e);
                try {
                    document.execCommand('backColor', false, color);
                } catch (e2) {
                    console.error('Fallback also failed:', e2);
                }
            }
            
            // Update the hidden input
            updateHiddenInput();
        } else {
            console.log('No selection, creating a default one');
            // If no selection, select all content and apply
            selectAllContent();
            try {
                document.execCommand('hiliteColor', false, color);
            } catch (e) {
                document.execCommand('backColor', false, color);
            }
            updateHiddenInput();
        }
    }
    
    // Helper to save selection
    function saveSelection() {
        if (window.getSelection) {
            const sel = window.getSelection();
            if (sel.getRangeAt && sel.rangeCount) {
                return sel.getRangeAt(0);
            }
        }
        return null;
    }
    
    // Helper to restore selection
    function restoreSelection(range) {
        if (range) {
            if (window.getSelection) {
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            }
        }
    }
    
    // Helper to select all content
    function selectAllContent() {
        const range = document.createRange();
        range.selectNodeContents(editor);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
    }
    
    // Helper to update hidden input
    function updateHiddenInput() {
        if (editor && hiddenInput) {
            hiddenInput.value = JSON.stringify({
                delta: {},
                html: editor.innerHTML
            });
        }
    }
    
    console.log('Color picker initialization complete');
}); 