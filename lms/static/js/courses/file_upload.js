// File upload handlers
document.addEventListener('DOMContentLoaded', function() {
    // Initialize file preview handlers
    initializeExistingFiles();
    
    // Add event listeners to all file inputs
    document.querySelectorAll('input[type="file"]').forEach(input => {
        input.addEventListener('change', handleFilePreview);
    });
});

// Initialize existing files display
function initializeExistingFiles() {
    // Show existing course image if present
    const courseImage = document.querySelector('.course-image');
    if (courseImage) {
        const imageUrl = courseImage.dataset.imageUrl;
        if (imageUrl) {
            const preview = document.createElement('img');
            preview.src = imageUrl;
            preview.alt = 'Course Image';
            preview.className = 'w-full h-48 object-cover rounded-lg';
            courseImage.appendChild(preview);
        }
    }
    
    // Show existing course video if present
    const courseVideo = document.querySelector('.course-video');
    if (courseVideo) {
        const videoUrl = courseVideo.dataset.videoUrl;
        if (videoUrl) {
            const preview = document.createElement('video');
            preview.src = videoUrl;
            preview.controls = true;
            preview.className = 'w-full rounded-lg';
            courseVideo.appendChild(preview);
        }
    }
    
    // Show existing filenames if present
    document.querySelectorAll('.file-name').forEach(element => {
        const fileName = element.dataset.fileName;
        if (fileName) {
            element.textContent = fileName;
        }
    });
}

// Handle file preview
function handleFilePreview(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    const previewContainer = e.target.closest('.file-upload-container').querySelector('.preview-container');
    const fileNameElement = e.target.closest('.file-upload-container').querySelector('.file-name');
    
    // Clear previous preview
    previewContainer.innerHTML = '';
    fileNameElement.textContent = file.name;
    
    // Create preview based on file type
    if (file.type.startsWith('image/')) {
        const preview = document.createElement('img');
        preview.src = URL.createObjectURL(file);
        preview.alt = 'Preview';
        preview.className = 'w-full h-48 object-cover rounded-lg';
        previewContainer.appendChild(preview);
    } else if (file.type.startsWith('video/')) {
        const preview = document.createElement('video');
        preview.src = URL.createObjectURL(file);
        preview.controls = true;
        preview.className = 'w-full rounded-lg';
        previewContainer.appendChild(preview);
    } else if (file.type.startsWith('audio/')) {
        const preview = document.createElement('audio');
        preview.src = URL.createObjectURL(file);
        preview.controls = true;
        preview.className = 'w-full';
        previewContainer.appendChild(preview);
    } else {
        // For other file types, show a document icon
        const preview = document.createElement('div');
        preview.className = 'flex items-center justify-center w-full h-48 bg-gray-100 rounded-lg';
        preview.innerHTML = `
            <div class="text-center">
                <i class="fas fa-file-alt text-4xl text-gray-400"></i>
                <p class="mt-2 text-sm text-gray-500">${file.name}</p>
                <p class="text-xs text-gray-400">${formatFileSize(file.size)}</p>
            </div>
        `;
        previewContainer.appendChild(preview);
    }
}

// Format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Handle file upload progress
function handleUploadProgress(e) {
    const progressBar = e.target.closest('.file-upload-container').querySelector('.progress-bar');
    if (progressBar) {
        const progress = (e.loaded / e.total) * 100;
        progressBar.style.width = `${progress}%`;
    }
}

// Handle file upload completion
function handleUploadComplete(e) {
    const response = JSON.parse(e.target.response);
    if (response.status === 'success') {
        // Update UI with uploaded file
        const fileNameElement = e.target.closest('.file-upload-container').querySelector('.file-name');
        fileNameElement.textContent = response.file_name;
        
        // Show success message
        const successMessage = document.createElement('div');
        successMessage.className = 'mt-2 text-sm text-green-600';
        successMessage.textContent = 'File uploaded successfully!';
        e.target.closest('.file-upload-container').appendChild(successMessage);
        
        // Remove success message after 3 seconds
        setTimeout(() => {
            successMessage.remove();
        }, 3000);
    } else {
        throw new Error(response.message || 'Failed to upload file');
    }
}

// Handle file upload error
function handleUploadError(e) {
    console.error('Upload error:', e);
    const errorMessage = document.createElement('div');
    errorMessage.className = 'mt-2 text-sm text-red-600';
    errorMessage.textContent = 'An error occurred while uploading the file. Please try again.';
    e.target.closest('.file-upload-container').appendChild(errorMessage);
    
    // Remove error message after 3 seconds
    setTimeout(() => {
        errorMessage.remove();
    }, 3000);
} 