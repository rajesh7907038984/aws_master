// File upload preview functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing file upload handlers');
    
    // Initialize existing file displays
    function initializeExistingFiles() {
        // Show existing course image
        const courseImagePreview = document.getElementById('course-image-preview');
        if (courseImagePreview && courseImagePreview.src && !courseImagePreview.src.includes('data:')) {
            courseImagePreview.classList.remove('hidden');
            // Also show the container if it's hidden
            const imageContainer = courseImagePreview.closest('.course-image-container');
            if (imageContainer) {
                imageContainer.classList.remove('hidden');
            }
        }
        
        // Show existing course video
        const courseVideoPreview = document.getElementById('course-video-preview');
        if (courseVideoPreview && courseVideoPreview.querySelector('source') && 
            courseVideoPreview.querySelector('source').src && 
            !courseVideoPreview.querySelector('source').src.includes('data:')) {
            courseVideoPreview.classList.remove('hidden');
        }
    }
    
    // Only initialize if not already initialized
    if (!window.fileUploadInitialized) {
        window.fileUploadInitialized = true;
        initializeExistingFiles();
    }
    
    // Course Image Upload
    const courseImageInput = document.querySelector('input[name="course_image"]');
    console.log('Course image input found:', !!courseImageInput);
    
    if (courseImageInput) {
        courseImageInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            console.log('Course image changed:', file?.name);
            
            if (file) {
                // Find the container
                const container = courseImageInput.closest('.file-upload-container');
                if (!container) {
                    console.error('Could not find container for course image');
                    return;
                }
                
                // Find or create a filename display element
                let filenameDisplay = container.querySelector('.selected-filename');
                if (!filenameDisplay) {
                    filenameDisplay = document.createElement('div');
                    filenameDisplay.className = 'selected-filename mt-2 text-sm font-medium text-blue-600';
                    container.appendChild(filenameDisplay);
                }
                
                // Update filename display
                filenameDisplay.textContent = `Selected: ${file.name}`;
                filenameDisplay.classList.remove('hidden');
                
                // Create or get the preview element
                let preview = document.getElementById('course-image-preview');
                if (!preview) {
                    preview = document.createElement('img');
                    preview.id = 'course-image-preview';
                    preview.className = 'mt-2 rounded-lg max-h-40 object-cover';
                    preview.alt = "Course image preview";
                    container.appendChild(preview);
                    console.log('Created new image preview element');
                }
                
                // Update the preview
                const reader = new FileReader();
                reader.onload = function(e) {
                    preview.src = e.target.result;
                    preview.classList.remove('hidden');
                    // Also show the container if it's hidden
                    const imageContainer = preview.closest('.course-image-container');
                    if (imageContainer) {
                        imageContainer.classList.remove('hidden');
                    }
                    console.log('Image preview updated');
                };
                reader.readAsDataURL(file);
            }
        });
    }
    
    // Course Video Upload
    const courseVideoInput = document.querySelector('input[name="course_video"]');
    console.log('Course video input found:', !!courseVideoInput);
    
    if (courseVideoInput) {
        courseVideoInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            console.log('Course video changed:', file?.name);
            
            if (file) {
                // Find the container
                const container = courseVideoInput.closest('.file-upload-container');
                if (!container) {
                    console.error('Could not find container for course video');
                    return;
                }
                
                // Find or create a filename display element
                let filenameDisplay = container.querySelector('.selected-filename');
                if (!filenameDisplay) {
                    filenameDisplay = document.createElement('div');
                    filenameDisplay.className = 'selected-filename mt-2 text-sm font-medium text-blue-600';
                    container.appendChild(filenameDisplay);
                }
                
                // Update filename display
                filenameDisplay.textContent = `Selected: ${file.name}`;
                filenameDisplay.classList.remove('hidden');
                
                // Create or get the preview element
                let preview = document.getElementById('course-video-preview');
                if (!preview) {
                    preview = document.createElement('video');
                    preview.id = 'course-video-preview';
                    preview.className = 'mt-2 rounded-lg max-h-40 w-full';
                    preview.controls = true;
                    container.appendChild(preview);
                    console.log('Created new video preview element');
                }
                
                // Update the preview
                const url = URL.createObjectURL(file);
                preview.src = url;
                preview.classList.remove('hidden');
                console.log('Video preview updated');
            }
        });
    }
    
    // Add a message to help diagnose any issues
    console.log('File upload initialization complete');
}); 