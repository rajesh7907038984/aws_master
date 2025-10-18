/**
 * Dynamic Forms JavaScript
 * Handles dynamic form field interactions and visibility toggles
 */

document.addEventListener('DOMContentLoaded', function() {
    
    // Handle "Other" field visibility for various dropdowns
    handleOtherFieldVisibility();
    
    // Handle file input displays
    handleFileInputs();
});

function handleOtherFieldVisibility() {
    // Sex/Gender other field
    const sexField = document.querySelector('[name="sex"]');
    const sexOtherContainer = document.querySelector('.sex-other-container');
    
    if (sexField && sexOtherContainer) {
        sexField.addEventListener('change', function() {
            try {
                if (this.value === 'other') {
                    sexOtherContainer.style.display = 'block';
                } else {
                    sexOtherContainer.style.display = 'none';
                }
            } catch (error) {
                console.error('Error handling sex field change:', error);
            }
        });
        
        // Check initial state
        try {
            if (sexField.value === 'other') {
                sexOtherContainer.style.display = 'block';
            }
        } catch (error) {
            console.error('Error checking initial sex field state:', error);
        }
    }
    
    // Sexual orientation other field
    const orientationField = document.querySelector('[name="sexual_orientation"]');
    const orientationOtherContainer = document.querySelector('.sexual-orientation-other-container');
    
    if (orientationField && orientationOtherContainer) {
        orientationField.addEventListener('change', function() {
            try {
                if (this.value === 'other') {
                    orientationOtherContainer.style.display = 'block';
                } else {
                    orientationOtherContainer.style.display = 'none';
                }
            } catch (error) {
                console.error('Error handling orientation field change:', error);
            }
        });
        
        // Check initial state  
        try {
            if (orientationField.value === 'other') {
                orientationOtherContainer.style.display = 'block';
            }
        } catch (error) {
            console.error('Error checking initial orientation field state:', error);
        }
    }
    
    // Ethnicity other field
    const ethnicityField = document.querySelector('[name="ethnicity"]');
    const ethnicityOtherContainer = document.querySelector('.ethnicity-other-container');
    
    if (ethnicityField && ethnicityOtherContainer) {
        ethnicityField.addEventListener('change', function() {
            try {
                if (this.value === 'other') {
                    ethnicityOtherContainer.style.display = 'block';
                } else {
                    ethnicityOtherContainer.style.display = 'none';
                }
            } catch (error) {
                console.error('Error handling ethnicity field change:', error);
            }
        });
        
        // Check initial state
        try {
            if (ethnicityField.value === 'other') {
                ethnicityOtherContainer.style.display = 'block';
            }
        } catch (error) {
            console.error('Error checking initial ethnicity field state:', error);
        }
    }
}

function handleFileInputs() {
    // Handle all file inputs with custom styling
    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(input => {
        input.addEventListener('change', function(e) {
            try {
                const file = e.target.files[0];
                const fileName = file ? file.name : 'No file chosen';
                
                // Find the corresponding file name display element
                const fileNameElement = input.parentNode.parentNode.querySelector('.file-name');
                if (fileNameElement) {
                    fileNameElement.textContent = fileName;
                }
            } catch (error) {
                console.error('Error handling file input change:', error);
            }
        });
    });
} 