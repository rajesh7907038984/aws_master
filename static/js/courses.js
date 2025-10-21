function handleImageUpload(input) {
    try {
        const fileInfo = document.getElementById('image-file-info');
        const imagePreview = document.getElementById('course-image-preview');
        
        if (input.files && input.files[0]) {
            const file = input.files[0];
            const fileSize = file.size / (1024 * 1024); // Convert to MB
            
            // File size validation (max 50MB for images)
            if (fileSize > 50) {
                alert('Image file size must be less than 50MB');
                input.value = '';
                return;
            }
            
            // Check file type
            if (!file.type.match('image.*')) {
                alert('Please upload an image file');
                input.value = '';
                return;
            }
            
            // Update UI
            if (fileInfo) {
                fileInfo.textContent = `Selected: ${file.name} (${fileSize.toFixed(2)}MB)`;
            }
            
            // Show preview
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    if (imagePreview) {
                        imagePreview.src = e.target.result;
                        imagePreview.classList.remove('hidden');
                        // Also show the container if it's hidden
                        const imageContainer = imagePreview.closest('.course-image-container');
                        if (imageContainer) {
                            imageContainer.classList.remove('hidden');
                        }
                    }
                } catch (error) {
                    console.error('Error loading image preview:', error);
                }
            };
            reader.onerror = function(error) {
                console.error('Error reading file:', error);
                alert('Error reading the selected file. Please try again.');
            };
            reader.readAsDataURL(file);
        } else {
            // Reset preview if no file selected
            if (fileInfo) {
                fileInfo.textContent = 'PNG, JPG - All Sizes Supported';
            }
            if (imagePreview) {
                imagePreview.classList.add('hidden');
                // Also hide the container
                const imageContainer = imagePreview.closest('.course-image-container');
                if (imageContainer) {
                    imageContainer.classList.add('hidden');
                }
            }
        }
    } catch (error) {
        console.error('Error handling image upload:', error);
    }
}

function handleVideoUpload(input) {
    try {
        const fileInfo = document.getElementById('video-file-info');
        const filenameDisplay = document.getElementById('video-filename-display');
        const videoPreview = document.getElementById('course-video-preview');
        
        if (input.files && input.files[0]) {
            const file = input.files[0];
            const fileSize = file.size / (1024 * 1024); // Convert to MB
            
            // File size validation (max 200MB for videos)
            if (fileSize > 200) {
                alert('Video file size must be less than 200MB');
                input.value = '';
                return;
            }
            
            // Check file type
            if (!file.type.match('video.*')) {
                alert('Please upload a video file');
                input.value = '';
                return;
            }
            
            // Update UI
            if (fileInfo) {
                fileInfo.textContent = `Selected: ${file.name} (${fileSize.toFixed(2)}MB)`;
            }
            if (filenameDisplay) {
                filenameDisplay.textContent = `Selected: ${file.name}`;
                filenameDisplay.classList.remove('hidden');
            }
            
            // Show preview
            const videoUrl = URL.createObjectURL(file);
            if (videoPreview) {
                const source = videoPreview.querySelector('source');
                if (source) {
                    // Clean up previous URL to prevent memory leak
                    if (source.src && source.src.startsWith('blob:')) {
                        URL.revokeObjectURL(source.src);
                    }
                    source.src = videoUrl;
                }
                videoPreview.classList.remove('hidden');
                videoPreview.load();
            }
        } else {
            // Reset preview if no file selected
            if (fileInfo) {
                fileInfo.textContent = 'MP4, MOV - All Sizes Supported';
            }
            if (filenameDisplay) {
                filenameDisplay.classList.add('hidden');
            }
            if (videoPreview) {
                videoPreview.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('Error handling video upload:', error);
    }
} 