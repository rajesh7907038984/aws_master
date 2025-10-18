// Global variables
let tinyMCEInstance = null;

// Initialize TinyMCE
function initTinyMCE() {
    // Get the textarea element
    const textarea = document.getElementById('id_text_content');
    if (textarea && typeof tinymce !== 'undefined') {
        // Initialize TinyMCE
        tinymce.init({
            selector: '#id_text_content',
            height: 400,
            plugins: [
                'advlist', 'autolink', 'lists', 'link', 'image', 'charmap', 'preview',
                'anchor', 'searchreplace', 'visualblocks', 'code', 'fullscreen',
                'insertdatetime', 'table', 'help', 'wordcount'
            ],
            toolbar: 'undo redo | blocks | ' +
                'bold italic backcolor | alignleft aligncenter ' +
                'alignright alignjustify | bullist numlist outdent indent | ' +
                'removeformat | help',
            content_style: 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
            placeholder: 'Enter your content here...',
            setup: function (editor) {
                tinyMCEInstance = editor;
            }
        });
    }
}

// Update content fields visibility
function updateContentFields() {
    const contentTypeSelect = document.getElementById('content_type');
    const contentFields = document.querySelectorAll('.content-type-field');
    const selectedType = contentTypeSelect.value.toLowerCase();

    // Hide all content fields first
    contentFields.forEach(field => {
        field.style.display = 'none';
    });

    // Show the appropriate content field based on the selected type
    let fieldId = selectedType + '-content-field';
        
        const field = document.getElementById(fieldId);
        if (field) {
            field.style.display = 'block';
            field.style.visibility = 'visible';
            
            // If it's a file input, ensure it's properly visible
            const fileInput = field.querySelector('input[type="file"]');
            if (fileInput) {
                fileInput.style.display = 'block';
                fileInput.style.visibility = 'visible';
                fileInput.style.opacity = '1';
                fileInput.style.position = 'static';
            }
        } else {
        }
    }

// Handle file upload preview
function handleFileUpload(input) {
    const file = input.files[0];
    if (file) {
        const preview = input.parentElement.querySelector('.file-preview');
        if (preview) {
            preview.textContent = `Selected file: ${file.name}`;
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Initialize date fields
    if (typeof DateTimeShortcuts !== 'undefined') {
        DateTimeShortcuts.init();
    }

    // Get form elements
    const form = document.getElementById('create-topic-form');
    const contentTypeSelect = document.getElementById('content_type');
    const contentFields = document.querySelectorAll('.content-type-field');

    // Initialize file upload previews
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function() {
            handleFileUpload(this);
            
            if (this.id === 'content_file') {
                const file = this.files[0];
                if (file) {
                    const preview = this.parentElement.querySelector('.file-preview');
                    if (preview) {
                        preview.textContent = `Selected file: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
                        preview.classList.remove('hidden');
                    }
                }
            }
        });
    });

    // Handle topic form submission
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const contentType = formData.get('content_type');
            
            // Get TinyMCE content if it exists and content type is Text
            if (contentType === 'Text') {
                // Check if TinyMCE is active on the text_content field
                if (typeof tinymce !== 'undefined') {
                    const editor = tinymce.get('id_text_content');
                    if (editor) {
                        // Get content from TinyMCE editor
                        const content = editor.getContent();
                        formData.set('text_content', content);
                    }
                }
            }
            
            // Send AJAX request
            fetch(window.location.href, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // Close modal and refresh page
                    closeTopicModal();
                    window.location.reload();
                } else {
                    // Show error message
                    alert('Error creating topic: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                alert('Error creating topic. Please try again.');
            });
        });
    }

    // Initial update
    updateContentFields();

    // Update on change
    contentTypeSelect.addEventListener('change', updateContentFields);

    // Handle modal close
    const closeButton = document.getElementById('close-topic-modal');
    const cancelButton = document.getElementById('cancel-topic');
    const modal = document.getElementById('topic-modal');

    function closeModal() {
        if (modal) {
            modal.classList.add('hidden');
            // Reset form
            if (form) {
                form.reset();
                updateContentFields();
            }
        }
    }

    if (closeButton) {
        closeButton.addEventListener('click', closeModal);
    }

    if (cancelButton) {
        cancelButton.addEventListener('click', closeModal);
    }
}); 