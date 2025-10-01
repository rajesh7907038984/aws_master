/**
 * CV Data Extraction JavaScript Module
 * Handles CV file upload and automatic data extraction functionality
 * for the user form in the LMS
 */

document.addEventListener('DOMContentLoaded', function() {
    // Get CSRF token
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

    const csrfToken = getCookie('csrftoken') || document.querySelector('[name=csrfmiddlewaretoken]')?.value;

    // Get form elements
    const cvFileInput = document.getElementById('id_cv_file');
    const cvFileNameSpan = document.getElementById('cv-file-name');
    const cvExtractionStatus = document.getElementById('cv-extraction-status');
    
    // Form field mappings for extracted data
    const fieldMappings = {
        // Personal Information
        'given_name': 'id_given_name',
        'family_name': 'id_family_name', 
        'email': 'id_email',
        'phone_number': 'id_phone_number',
        // Address fields
        'address_line1': 'id_address_line1',
        'city': 'id_city',
        'postcode': 'id_postcode',
        'country': 'id_country'
    };

    if (!cvFileInput) {
        console.log('CV file input not found on this page');
        return;
    }

    // Handle file selection and update display name
    cvFileInput.addEventListener('change', function(event) {
        const file = event.target.files[0];
        
        if (file) {
            // Update file name display
            if (cvFileNameSpan) {
                cvFileNameSpan.textContent = file.name;
            }
            
            // Only process PDF files
            if (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
                // Show processing status
                showExtractionStatus('Extracting data from CV...');
                
                // Process the CV file
                extractCVData(file);
            } else {
                console.log('Non-PDF file selected, skipping CV extraction');
                hideExtractionStatus();
            }
        } else {
            // Reset file name display
            if (cvFileNameSpan) {
                cvFileNameSpan.textContent = 'No file chosen';
            }
            hideExtractionStatus();
        }
    });

    /**
     * Show CV extraction status with message
     */
    function showExtractionStatus(message) {
        if (cvExtractionStatus) {
            const statusText = cvExtractionStatus.querySelector('span');
            if (statusText) {
                statusText.textContent = message || 'Extracting data from CV...';
            }
            cvExtractionStatus.classList.remove('hidden');
        }
    }

    /**
     * Hide CV extraction status
     */
    function hideExtractionStatus() {
        if (cvExtractionStatus) {
            cvExtractionStatus.classList.add('hidden');
        }
    }

    /**
     * Extract data from CV file using the backend API
     */
    function extractCVData(file) {
        // Create FormData to send file
        const formData = new FormData();
        formData.append('cv_file', file);

        // Make AJAX request to extraction endpoint
        fetch('/users/api/extract-cv-data/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
            },
            body: formData
        })
        .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
        .then(data => {
            hideExtractionStatus();
            
            if (data.status === 'success' && data.data) {
                console.log('CV data extracted successfully:', data.data);
                populateFormFields(data.data);
                showSuccessMessage('CV data extracted successfully!');
            } else {
                console.error('CV extraction failed:', data.message || 'Unknown error');
                showErrorMessage(data.message || 'Failed to extract CV data');
            }
        })
        .catch(error => {
            console.error('Error extracting CV data:', error);
            hideExtractionStatus();
            showErrorMessage('An error occurred while extracting CV data');
        });
    }

    /**
     * Populate form fields with extracted CV data
     */
    function populateFormFields(extractedData) {
        try {
            // Populate personal information fields
            if (extractedData.personal_info) {
                const personalInfo = extractedData.personal_info;
                
                // Map basic fields
                Object.keys(fieldMappings).forEach(field => {
                    const elementId = fieldMappings[field];
                    const element = document.getElementById(elementId);
                    
                    if (element && personalInfo[field]) {
                        // Only populate if field is empty to avoid overwriting existing data
                        if (!element.value.trim()) {
                            element.value = personalInfo[field];
                            // Trigger change event for any listeners
                            element.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                });

                // Handle nested address fields
                if (personalInfo.address) {
                    const address = personalInfo.address;
                    Object.keys(address).forEach(field => {
                        const elementId = fieldMappings[field];
                        const element = document.getElementById(elementId);
                        
                        if (element && address[field]) {
                            // Only populate if field is empty
                            if (!element.value.trim()) {
                                element.value = address[field];
                                element.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }
                    });
                }
            }

            // Handle education data (if there are education fields in the form)
            if (extractedData.education && extractedData.education.length > 0) {
                console.log('Education data found:', extractedData.education);
                // Education fields would be handled here if they exist in the form
                // This could be extended based on the specific form structure
            }

            // Handle employment data (if there are employment fields in the form)
            if (extractedData.employment && extractedData.employment.length > 0) {
                console.log('Employment data found:', extractedData.employment);
                // Employment fields would be handled here if they exist in the form
                // This could be extended based on the specific form structure
            }

        } catch (error) {
            console.error('Error populating form fields:', error);
            showErrorMessage('Error populating form with extracted data');
        }
    }

    /**
     * Show success message to user
     */
    function showSuccessMessage(message) {
        // Create or update success notification
        showNotification(message, 'success');
    }

    /**
     * Show error message to user
     */
    function showErrorMessage(message) {
        // Create or update error notification
        showNotification(message, 'error');
    }

    /**
     * Show notification message with appropriate styling
     */
    function showNotification(message, type) {
        // Remove any existing notifications
        const existingNotification = document.querySelector('.cv-extraction-notification');
        if (existingNotification) {
            existingNotification.remove();
        }

        // Create notification element
        const notification = document.createElement('div');
        notification.className = `cv-extraction-notification fixed top-4 right-4 p-4 rounded-md shadow-lg z-50 max-w-md ${
            type === 'success' 
                ? 'bg-green-100 border border-green-400 text-green-700' 
                : 'bg-red-100 border border-red-400 text-red-700'
        }`;
        
        notification.innerHTML = `
            <div class="flex items-center">
                <div class="flex-shrink-0">
                    <svg class="h-5 w-5 ${type === 'success' ? 'text-green-400' : 'text-red-400'}" viewBox="0 0 20 20" fill="currentColor">
                        ${type === 'success' 
                            ? '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />'
                            : '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />'
                        }
                    </svg>
                </div>
                <div class="ml-3">
                    <p class="text-sm font-medium">${message}</p>
                </div>
                <div class="ml-auto pl-3">
                    <button type="button" class="inline-flex text-sm" onclick="this.parentElement.parentElement.parentElement.remove()">
                        <span class="sr-only">Close</span>
                        <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                        </svg>
                    </button>
                </div>
            </div>
        `;

        // Add to page
        document.body.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }

    console.log('CV extraction JavaScript initialized');
});
