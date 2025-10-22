document.addEventListener('DOMContentLoaded', function() {
    // Initialize date fields
    if (typeof DateTimeShortcuts !== 'undefined') {
        DateTimeShortcuts.init();
    }

    // Get form elements
    const form = document.getElementById('create-topic-form');
    const contentTypeSelect = document.getElementById('content_type');
    const contentFields = document.querySelectorAll('.content-type-field');
    let quillInstance = null;

    // Initialize Quill
    function initQuill() {
        // Get the textarea element
        const textarea = document.getElementById('id_text_content');
        if (textarea) {
            // Create a container for Quill
            const quillContainer = document.createElement('div');
            quillContainer.id = 'quill-editor';
            quillContainer.style.height = '400px';
            textarea.parentNode.insertBefore(quillContainer, textarea);
            
            // Initialize Quill
            quillInstance = new Quill('#quill-editor', {
                theme: 'snow',
                modules: {
                    toolbar: [
                        ['bold', 'italic', 'underline', 'strike'],
                        ['blockquote', 'code-block'],
                        [{ 'header': 1 }, { 'header': 2 }],
                        [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                        [{ 'script': 'sub'}, { 'script': 'super' }],
                        [{ 'indent': '-1'}, { 'indent': '+1' }],
                        [{ 'direction': 'rtl' }],
                        [{ 'size': ['small', false, 'large', 'huge'] }],
                        [{ 'header': [1, 2, 3, 4, 5, 6, false] }],
                        [{ 'color': [] }, { 'background': [] }],
                        [{ 'font': [] }],
                        [{ 'align': [] }],
                        ['clean'],
                        ['link', 'image']
                    ],
                    clipboard: {
                        // Prevent automatic URL creation on paste/selection
                        matchVisual: false
                    }
                },
                placeholder: 'Enter your content here...',
                formats: [
                    'bold', 'italic', 'underline', 'strike',
                    'blockquote', 'code-block', 'header', 'list',
                    'script', 'indent', 'direction', 'size',
                    'color', 'background', 'font', 'align',
                    'link', 'image'
                ]
            });

            // Disable automatic link detection
            quillInstance.clipboard.addMatcher(Node.TEXT_NODE, function(node, delta) {
                return delta;
            });

            // Set initial content if any
            if (textarea.value) {
                quillInstance.root.innerHTML = textarea.value;
            }

            // Update textarea on change
            quillInstance.on('text-change', function() {
                textarea.value = quillInstance.root.innerHTML;
            });
        }
    }

    // Update content fields visibility
    function updateContentFields() {
        const selectedType = contentTypeSelect.value.toLowerCase();
        console.log('Selected content type:', selectedType);

        // Hide all content fields first
        contentFields.forEach(field => {
            field.style.display = 'none';
        });

        // Show the appropriate content field based on the selected type
        let fieldId = selectedType + '-content-field';
        
        console.log('Looking for field with ID:', fieldId);
        const field = document.getElementById(fieldId);
        if (field) {
            console.log('Found field, displaying it');
            field.style.display = 'block';
            field.style.visibility = 'visible';
            
            // If it's a file input, ensure it's properly visible
            const fileInput = field.querySelector('input[type="file"]');
            if (fileInput) {
                console.log('Found file input, making it visible');
                fileInput.style.display = 'block';
                fileInput.style.visibility = 'visible';
                fileInput.style.opacity = '1';
                fileInput.style.position = 'static';
            }
        } else {
            console.log('Field not found for ID:', fieldId);
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

    // Initialize file upload previews
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function() {
            handleFileUpload(this);
            
            // Special handling for SCORM file
            if (this.id === 'content_file') {
                const file = this.files[0];
                if (file) {
                    const preview = document.getElementById('scorm-file-preview');
                    if (preview) {
                        preview.textContent = `Selected file: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
                        preview.classList.remove('hidden');
                    }
                    console.log('SCORM file selected:', file.name);
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
                        console.log('Setting text_content with TinyMCE content');
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
                console.error('Error:', error);
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