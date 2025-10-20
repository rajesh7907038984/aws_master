/**
 * Image Field Handler
 * Manages the course image upload field with preview functionality
 */
document.addEventListener('DOMContentLoaded', function() {
  const imageField = document.querySelector('#id_image');
  if (!imageField) return;

  // Create image preview container if it doesn't exist
  let previewContainer = document.querySelector('.image-preview');
  if (!previewContainer) {
    previewContainer = document.createElement('div');
    previewContainer.classList.add('image-preview', 'mt-2', 'rounded', 'overflow-hidden', 'hidden');
    imageField.parentNode.appendChild(previewContainer);
  }

  // Create preview image element
  const previewImage = document.createElement('img');
  previewImage.classList.add('w-full', 'h-auto', 'max-h-48', 'object-cover');
  previewContainer.appendChild(previewImage);

  // Handle file selection
  imageField.addEventListener('change', function(e) {
    const file = this.files[0];
    if (file) {
      const reader = new FileReader();
      
      reader.onload = function(event) {
        previewImage.src = event.target.result;
        previewContainer.classList.remove('hidden');
        
        // Add remove button if it doesn't exist
        if (!document.querySelector('.remove-image-btn')) {
          const removeBtn = document.createElement('button');
          removeBtn.textContent = 'Remove Image';
          removeBtn.classList.add('remove-image-btn', 'mt-2', 'text-sm', 'text-red-600', 'hover:text-red-800', 'focus:outline-none');
          removeBtn.type = 'button';
          
          removeBtn.addEventListener('click', function() {
            // Clear the file input
            imageField.value = '';
            previewContainer.classList.add('hidden');
            previewImage.src = '';
            this.remove();
          });
          
          previewContainer.parentNode.insertBefore(removeBtn, previewContainer.nextSibling);
        }
      };
      
      reader.readAsDataURL(file);
    } else {
      previewContainer.classList.add('hidden');
      previewImage.src = '';
      
      // Remove the remove button if it exists
      const removeBtn = document.querySelector('.remove-image-btn');
      if (removeBtn) {
        removeBtn.remove();
      }
    }
  });

  // Check if there's an existing image
  if (imageField.dataset.currentImage) {
    previewImage.src = imageField.dataset.currentImage;
    previewContainer.classList.remove('hidden');
  }
}); 