/**
 * Settings Field Handler
 * Manages the course settings panel and field controls
 */
document.addEventListener('DOMContentLoaded', function() {
  // Get modal elements
  const settingsModal = document.getElementById('settings-modal');
  const closeSettingsModal = document.querySelector('.close-settings-modal');
  const cancelSettingsBtn = document.querySelector('.cancel-settings-btn');
  const saveSettingsBtn = document.getElementById('save-settings-btn');

  // Handle settings button click
  const settingsButton = document.querySelector('[data-action="settings"]');
  if (settingsButton) {
    settingsButton.addEventListener('click', function() {
      settingsModal.classList.remove('hidden');
      document.body.classList.add('modal-open');
    });
  }

  // Handle modal close
  function closeModal() {
    settingsModal.classList.add('hidden');
    document.body.classList.remove('modal-open');
  }

  // Close modal event listeners
  if (closeSettingsModal) {
    closeSettingsModal.addEventListener('click', closeModal);
  }
  if (cancelSettingsBtn) {
    cancelSettingsBtn.addEventListener('click', closeModal);
  }

  // Handle settings tabs
  const settingsTabs = document.querySelectorAll('.settings-tab');
  const settingsTabContents = document.querySelectorAll('.settings-tab-content');
  
  settingsTabs.forEach(tab => {
    tab.addEventListener('click', function() {
      // Remove active class from all tabs
      settingsTabs.forEach(t => t.classList.remove('active'));
      
      // Add active class to clicked tab
      this.classList.add('active');
      
      // Hide all tab contents and prevent blank space
      settingsTabContents.forEach(content => {
        content.classList.remove('active');
        content.style.height = '0';
        content.style.overflow = 'hidden';
        content.style.padding = '0';
        content.style.margin = '0';
      });
      
      // Show corresponding tab content
      const target = this.dataset.target;
      if (target) {
        const targetContent = document.querySelector(`#${target}`);
        if (targetContent) {
          targetContent.classList.add('active');
          targetContent.style.height = 'auto';
          targetContent.style.overflow = 'visible';
          targetContent.style.padding = '';
          targetContent.style.margin = '';
        }
      }
    });
  });

  // Helper function to update field visibility
  function updateFieldVisibility(field, isVisible) {
    if (isVisible) {
      field.classList.remove('hidden');
    } else {
      field.classList.add('hidden');
    }
  }

  // Helper function to update enrollment key field
  function updateEnrollmentKeyField(enrollmentType) {
    if (enrollmentType === 'key') {
      enrollmentKeyField.classList.remove('hidden');
    } else {
      enrollmentKeyField.classList.add('hidden');
    }
  }

  // Helper function to update date field state
  function updateDateFieldState(dateField, isEnabled) {
    const inputs = dateField.querySelectorAll('input');
    inputs.forEach(input => {
      input.disabled = !isEnabled;
      
      if (isEnabled) {
        dateField.classList.remove('opacity-50');
      } else {
        dateField.classList.add('opacity-50');
      }
    });
  }

  // Handle save settings
  if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', function() {
      // Get all form values
      const formData = new FormData();
      formData.append('course_code', document.getElementById('settings_course_code').value);
      formData.append('language', document.getElementById('settings_language').value);
      formData.append('visibility', document.getElementById('settings_visibility').value);
      formData.append('start_date', document.getElementById('settings_start_date').value);
      formData.append('end_date', document.getElementById('settings_end_date').value);
      formData.append('schedule_type', document.getElementById('settings_schedule_type').value);
      formData.append('require_enrollment', document.getElementById('settings_require_enrollment').checked);
      formData.append('sequential_progression', document.getElementById('settings_sequential_progression').checked);
      formData.append('all_topics_complete', document.getElementById('settings_all_topics_complete').checked);
      formData.append('minimum_score', document.getElementById('settings_minimum_score').checked);
      formData.append('certificate_type', document.getElementById('settings_certificate_type').value);

      // Send AJAX request to save settings
      // Get CSRF token
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
                       document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
      
      if (!csrfToken) {
        console.error('CSRF token not found');
        alert('Security token not found. Please refresh the page and try again.');
        return;
      }
      
      fetch(window.location.href, {
        method: 'POST',
        body: formData,
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': csrfToken
        }
      })
      .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
      .then(data => {
        if (data.success) {
          // Show success message
          alert('Settings saved successfully');
          closeModal();
        } else {
          // Show error message
          alert('Error saving settings: ' + data.error);
        }
      })
      .catch(error => {
        console.error('Error:', error);
        alert('Error saving settings');
      });
    });
  }
}); 