/**
 * Title Field Handler
 * Manages the course title field functionality
 */

// Import field-specific CSS
import '../../css/form_fields/title_field.css';

// Initialization function
export function init() {
  const titleField = document.querySelector('#id_title');
  if (!titleField) return;

  // Character counter for title
  const maxLength = titleField.getAttribute('maxlength') || 255;
  const counterDiv = document.createElement('div');
  counterDiv.classList.add('text-xs', 'text-gray-500', 'mt-1');
  counterDiv.innerHTML = `<span class="current-count">0</span>/${maxLength} characters`;
  titleField.parentNode.appendChild(counterDiv);

  // Update character count
  const currentCount = counterDiv.querySelector('.current-count');
  titleField.addEventListener('input', function() {
    currentCount.textContent = this.value.length;
    
    // Change color when approaching limit
    if (this.value.length > (maxLength * 0.8)) {
      currentCount.classList.add('text-yellow-600');
    } else if (this.value.length > (maxLength * 0.95)) {
      currentCount.classList.remove('text-yellow-600');
      currentCount.classList.add('text-red-600');
    } else {
      currentCount.classList.remove('text-yellow-600', 'text-red-600');
    }
  });

  // Trigger initial count
  titleField.dispatchEvent(new Event('input'));
}

// Validate the title field
export function validate(titleField) {
  if (!titleField) return true;
  
  return titleField.value.trim().length > 0;
}

// Auto-initialize if this script is loaded directly
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
} 