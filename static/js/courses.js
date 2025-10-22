function handleImageUpload(input) {
    const fileInfo = document.getElementById('image-file-info');
    const imagePreview = document.getElementById('course-image-preview');
    
    if (input.files && input.files[0]) {
        const file = input.files[0];
        const fileSize = file.size / (1024 * 1024); // Convert to MB
        
        // File size check removed
        
        // Check file type
        if (!file.type.match('image.*')) {
            alert('Please upload an image file');
            input.value = '';
            return;
        }
        
        // Update UI
        fileInfo.textContent = `Selected: ${file.name} (${fileSize.toFixed(2)}MB)`;
        
        // Show preview
        const reader = new FileReader();
        reader.onload = function(e) {
            imagePreview.src = e.target.result;
            imagePreview.classList.remove('hidden');
            // Also show the container if it's hidden
            const imageContainer = imagePreview.closest('.course-image-container');
            if (imageContainer) {
                imageContainer.classList.remove('hidden');
            }
        };
        reader.readAsDataURL(file);
    } else {
        // Reset preview if no file selected
        fileInfo.textContent = 'PNG, JPG - All Sizes Supported';
        imagePreview.classList.add('hidden');
        // Also hide the container
        const imageContainer = imagePreview.closest('.course-image-container');
        if (imageContainer) {
            imageContainer.classList.add('hidden');
        }
    }
}

function handleVideoUpload(input) {
    const fileInfo = document.getElementById('video-file-info');
    const filenameDisplay = document.getElementById('video-filename-display');
    const videoPreview = document.getElementById('course-video-preview');
    
    if (input.files && input.files[0]) {
        const file = input.files[0];
        const fileSize = file.size / (1024 * 1024); // Convert to MB
        
        // File size check removed
        
        // Check file type
        if (!file.type.match('video.*')) {
            alert('Please upload a video file');
            input.value = '';
            return;
        }
        
        // Update UI
        fileInfo.textContent = `Selected: ${file.name} (${fileSize.toFixed(2)}MB)`;
        filenameDisplay.textContent = `Selected: ${file.name}`;
        filenameDisplay.classList.remove('hidden');
        
        // Show preview
        const videoUrl = URL.createObjectURL(file);
        videoPreview.querySelector('source').src = videoUrl;
        videoPreview.classList.remove('hidden');
        videoPreview.load();
    } else {
        // Reset preview if no file selected
        fileInfo.textContent = 'MP4, MOV - All Sizes Supported';
        filenameDisplay.classList.add('hidden');
        videoPreview.classList.add('hidden');
    }
} 