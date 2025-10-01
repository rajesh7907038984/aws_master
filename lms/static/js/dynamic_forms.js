/**
 * Dynamic Forms JavaScript
 * Handles dynamic form field interactions and visibility toggles
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Dynamic forms script loaded');
    
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
            if (this.value === 'other') {
                sexOtherContainer.style.display = 'block';
            } else {
                sexOtherContainer.style.display = 'none';
            }
        });
        
        // Check initial state
        if (sexField.value === 'other') {
            sexOtherContainer.style.display = 'block';
        }
    }
    
    // Sexual orientation other field
    const orientationField = document.querySelector('[name="sexual_orientation"]');
    const orientationOtherContainer = document.querySelector('.sexual-orientation-other-container');
    
    if (orientationField && orientationOtherContainer) {
        orientationField.addEventListener('change', function() {
            if (this.value === 'other') {
                orientationOtherContainer.style.display = 'block';
            } else {
                orientationOtherContainer.style.display = 'none';
            }
        });
        
        // Check initial state  
        if (orientationField.value === 'other') {
            orientationOtherContainer.style.display = 'block';
        }
    }
    
    // Ethnicity other field
    const ethnicityField = document.querySelector('[name="ethnicity"]');
    const ethnicityOtherContainer = document.querySelector('.ethnicity-other-container');
    
    if (ethnicityField && ethnicityOtherContainer) {
        ethnicityField.addEventListener('change', function() {
            if (this.value === 'other') {
                ethnicityOtherContainer.style.display = 'block';
            } else {
                ethnicityOtherContainer.style.display = 'none';
            }
        });
        
        // Check initial state
        if (ethnicityField.value === 'other') {
            ethnicityOtherContainer.style.display = 'block';
        }
    }
}

function handleFileInputs() {
    // Handle all file inputs with custom styling
    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(input => {
        input.addEventListener('change', function(e) {
            const file = e.target.files[0];
            const fileName = file ? file.name : 'No file chosen';
            
            // Find the corresponding file name display element
            const fileNameElement = input.parentNode.parentNode.querySelector('.file-name');
            if (fileNameElement) {
                fileNameElement.textContent = fileName;
            }
            
            console.log('File selected:', fileName);
        });
    });
} 