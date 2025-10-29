// Utility function to get cookie value
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
            field.classList.remove('active');
        });

        // Show the appropriate content field based on the selected type
        let fieldId = selectedType + '-content';
        
        console.log('Looking for field with ID:', fieldId);
        const field = document.getElementById(fieldId);
        if (field) {
            console.log('Found field, displaying it');
            field.style.display = 'block';
            field.style.visibility = 'visible';
            field.style.opacity = '1';
            field.classList.add('active');
            
            // If it's a file input, ensure it's properly visible
            const fileInput = field.querySelector('input[type="file"]');
            if (fileInput) {
                console.log('Found file input, making it visible');
                fileInput.style.display = 'block';
                fileInput.style.visibility = 'visible';
                fileInput.style.opacity = '1';
                fileInput.style.position = 'static';
            }
            
            // Special handling for text content field to ensure TinyMCE is properly initialized
            if (selectedType === 'text') {
                console.log('Text content selected, ensuring TinyMCE is ready');
                setTimeout(function() {
                    // Force reinitialize TinyMCE for text content when field becomes visible
                    const textArea = field.querySelector('textarea');
                    if (textArea && typeof tinymce !== 'undefined') {
                        const editorId = textArea.id || 'id_text_content';
                        console.log('Looking for TinyMCE editor with ID:', editorId);
                        
                        if (tinymce.get(editorId)) {
                            console.log('TinyMCE already initialized for:', editorId);
                            // Make sure the editor container is visible and has proper height
                            const editor = tinymce.get(editorId);
                            const editorContainer = editor.getContainer();
                            if (editorContainer) {
                                editorContainer.style.display = 'block';
                                editorContainer.style.visibility = 'visible';
                                editorContainer.style.opacity = '1';
                                editorContainer.style.minHeight = '450px';
                                editorContainer.style.height = '450px';
                                
                                const iframe = editorContainer.querySelector('.tox-edit-area__iframe');
                                if (iframe) {
                                    iframe.style.minHeight = '400px';
                                    iframe.style.height = '400px';
                                }
                                console.log('TinyMCE container made visible with proper height');
                            }
                        } else {
                            console.log('TinyMCE not found for:', editorId, 'Initializing...');
                            // Initialize TinyMCE if not already done
                            if (typeof window.TinyMCEWidget !== 'undefined' && window.TinyMCEWidget.initialize) {
                                console.log('Using TinyMCEWidget to initialize');
                                window.TinyMCEWidget.initialize(textArea);
                            } else {
                                console.log('TinyMCEWidget not available, trying direct initialization');
                                // Direct TinyMCE initialization
                                tinymce.init({
                                    selector: '#' + editorId,
                                    height: 450,
                                    min_height: 450,
                                    menubar: true,
                                    statusbar: false,
                                    plugins: [
                                        'advlist', 'autolink', 'lists', 'link', 'image', 'charmap', 'preview',
                                        'anchor', 'searchreplace', 'visualblocks', 'code', 'fullscreen',
                                        'insertdatetime', 'media', 'table', 'wordcount'
                                    ],
                                    toolbar: 'undo redo | blocks | bold italic forecolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | removeformat',
                                    content_style: 'body { font-family:Helvetica,Arial,sans-serif; font-size:14px }',
                                    branding: false,
                                    promotion: false,
                                    base_url: '/static/tinymce_editor/tinymce/',
                                    setup: function(editor) {
                                        editor.on('init', function() {
                                            const container = editor.getContainer();
                                            if (container) {
                                                container.style.minHeight = '450px';
                                                container.style.height = '450px';
                                                const iframe = container.querySelector('.tox-edit-area__iframe');
                                                if (iframe) {
                                                    iframe.style.minHeight = '400px';
                                                    iframe.style.height = '400px';
                                                }
                                            }
                                        });
                                    }
                                }).then(function(editors) {
                                    console.log('TinyMCE initialized successfully for:', editorId);
                                    if (editors && editors.length > 0) {
                                        console.log('Editor instance created:', editors[0].id);
                                    }
                                }).catch(function(error) {
                                    console.error('Failed to initialize TinyMCE for:', editorId, error);
                                });
                            }
                        }
                    } else {
                        console.log('Textarea not found or TinyMCE not available');
                    }
                    
                    // Additional attempt to ensure visibility and height
                    setTimeout(function() {
                        if (typeof window.ensureTinyMCEVisible === 'function') {
                            window.ensureTinyMCEVisible();
                        }
                    }, 500);
                }, 200); // Increased timeout to ensure DOM is ready
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