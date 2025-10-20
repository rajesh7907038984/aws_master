// File preview functionality for different file types
document.addEventListener('DOMContentLoaded', function() {
    
    // Initialize existing file displays
    function initializeExistingFiles() {
        // Show existing course image
        const courseImagePreview = document.getElementById('course-image-preview');
        if (courseImagePreview && courseImagePreview.src) {
            courseImagePreview.classList.remove('hidden');
        }
        
        // Show existing course video
        const courseVideoPreview = document.getElementById('course-video-preview');
        if (courseVideoPreview && courseVideoPreview.src) {
            courseVideoPreview.classList.remove('hidden');
        }
        
        // Show existing filenames
        
        const videoFilenameDisplay = document.getElementById('video-filename-display');
        if (videoFilenameDisplay && videoFilenameDisplay.textContent.trim() !== '') {
            videoFilenameDisplay.classList.remove('hidden');
        }
    }
    
    // Call initialization function
    initializeExistingFiles();
    
    // Generic file preview handler
    function handleFilePreview(input, fileType) {
        try {
            if (!input || !input.files) {
                console.warn('Invalid file input provided');
                return;
            }
            
            const container = input.closest('.file-upload-container');
            if (!container) {
                console.warn('File upload container not found');
                return;
            }
            
            // Find or create a filename display element
            let filenameDisplay = container.querySelector('.selected-filename');
            if (!filenameDisplay) {
                filenameDisplay = document.createElement('div');
                filenameDisplay.className = 'selected-filename mt-2 text-sm font-medium text-blue-600';
                container.appendChild(filenameDisplay);
            }
            
            // Find or create a preview element
            let preview = container.querySelector('.file-preview');
            if (!preview) {
                preview = document.createElement('div');
                preview.className = 'file-preview mt-2';
                container.appendChild(preview);
            }
        
        if (input.files && input.files[0]) {
            const file = input.files[0];
            const fileSize = file.size / (1024 * 1024); // Convert to MB
            
            // Update filename display
            if (filenameDisplay) {
                filenameDisplay.textContent = `Selected: ${file.name} (${fileSize.toFixed(2)}MB)`;
                filenameDisplay.classList.remove('hidden');
            }
            
            // Handle different file types
            switch(fileType) {
                case 'image':
                    if (!preview.querySelector('img')) {
                        const img = document.createElement('img');
                        img.className = 'rounded-lg max-h-40 object-cover';
                        img.alt = 'Image preview';
                        preview.appendChild(img);
                    }
                    const img = preview.querySelector('img');
                    if (img) {
                        const reader = new FileReader();
                        reader.onload = function(e) {
                            if (img && preview) {
                                img.src = e.target.result;
                                preview.classList.remove('hidden');
                            }
                        };
                        reader.readAsDataURL(file);
                    }
                    break;
                    
                case 'video':
                    if (!preview.querySelector('video')) {
                        const video = document.createElement('video');
                        video.className = 'rounded-lg max-h-40 w-full';
                        video.controls = true;
                        const source = document.createElement('source');
                        video.appendChild(source);
                        preview.appendChild(video);
                    }
                    const video = preview.querySelector('video');
                    if (video) {
                        const videoUrl = URL.createObjectURL(file);
                        const source = video.querySelector('source');
                        if (source) {
                            source.src = videoUrl;
                            video.load();
                            preview.classList.remove('hidden');
                        }
                    }
                    break;
                    
                case 'audio':
                    if (!preview.querySelector('audio')) {
                        const audio = document.createElement('audio');
                        audio.className = 'w-full';
                        audio.controls = true;
                        const source = document.createElement('source');
                        audio.appendChild(source);
                        preview.appendChild(audio);
                    }
                    const audio = preview.querySelector('audio');
                    if (audio) {
                        const audioUrl = URL.createObjectURL(file);
                        const source = audio.querySelector('source');
                        if (source) {
                            source.src = audioUrl;
                            audio.load();
                            preview.classList.remove('hidden');
                        }
                    }
                    break;
                    
                case 'document':
                    if (window.SafeHTMLUtils) {
                        window.SafeHTMLUtils.setSafeInnerHTML(preview, `
                            <div class="flex items-center space-x-2 p-2 bg-gray-50 rounded-lg">
                                <i class="fas fa-file text-gray-500"></i>
                                <span class="text-sm text-gray-700">${window.SafeHTMLUtils.escapeHTML(file.name)}</span>
                            </div>
                        `);
                    } else {
                        preview.innerHTML = `
                            <div class="flex items-center space-x-2 p-2 bg-gray-50 rounded-lg">
                                <i class="fas fa-file text-gray-500"></i>
                                <span class="text-sm text-gray-700">${file.name}</span>
                            </div>
                        `;
                    }
                    preview.classList.remove('hidden');
                    break;
            }
        } else {
            // If no file selected, hide preview
            if (preview) {
                preview.classList.add('hidden');
            }
            if (filenameDisplay) {
                filenameDisplay.classList.add('hidden');
            }
        }
        } catch (error) {
            console.error('Error handling file preview:', error);
        }
    }
    
    // Add event listeners to all file inputs
    document.querySelectorAll('input[type="file"]').forEach(input => {
        input.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                // Determine file type
                let fileType = 'document';
                if (file.type.startsWith('image/')) {
                    fileType = 'image';
                } else if (file.type.startsWith('video/')) {
                    fileType = 'video';
                } else if (file.type.startsWith('audio/')) {
                    fileType = 'audio';
                }
                handleFilePreview(this, fileType);
            }
        });
    });
}); 