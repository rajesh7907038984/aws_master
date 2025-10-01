// Email Configuration JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Toggle SMTP configuration visibility
    const smtpEnabledCheckbox = document.getElementById('smtp_enabled');
    const smtpConfigDiv = document.getElementById('smtp_config');
    
    if (smtpEnabledCheckbox && smtpConfigDiv) {
        smtpEnabledCheckbox.addEventListener('change', function() {
            if (this.checked) {
                smtpConfigDiv.style.display = 'block';
            } else {
                smtpConfigDiv.style.display = 'none';
            }
        });
    }
    
    // Handle form submission with loading state
    const emailForm = document.querySelector('form[action*="smtp_settings"], form input[name="form_type"][value="smtp_settings"]');
    if (emailForm) {
        emailForm.addEventListener('submit', function(e) {
            const submitButton = this.querySelector('button[type="submit"]');
            if (submitButton) {
                // Show loading state
                submitButton.disabled = true;
                const originalText = submitButton.innerHTML;
                submitButton.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Testing...';
                
                // Re-enable button after 10 seconds as fallback
                setTimeout(() => {
                    submitButton.disabled = false;
                    submitButton.innerHTML = originalText;
                }, 10000);
            }
        });
    }
    
    // Auto-populate common SMTP settings based on host
    const smtpHostInput = document.getElementById('smtp_host');
    const smtpPortInput = document.getElementById('smtp_port');
    const smtpTlsCheckbox = document.getElementById('smtp_use_tls');
    const smtpSslCheckbox = document.getElementById('smtp_use_ssl');
    
    if (smtpHostInput && smtpPortInput && smtpTlsCheckbox && smtpSslCheckbox) {
        smtpHostInput.addEventListener('blur', function() {
            const host = this.value.toLowerCase();
            
            if (host.includes('gmail.com')) {
                smtpPortInput.value = '587';
                smtpTlsCheckbox.checked = true;
                smtpSslCheckbox.checked = false;
            } else if (host.includes('office365.com') || host.includes('outlook.com')) {
                smtpPortInput.value = '587';
                smtpTlsCheckbox.checked = true;
                smtpSslCheckbox.checked = false;
            } else if (host.includes('yahoo.com')) {
                smtpPortInput.value = '587';
                smtpTlsCheckbox.checked = true;
                smtpSslCheckbox.checked = false;
            } else if (host.includes('mailgun.com')) {
                smtpPortInput.value = '587';
                smtpTlsCheckbox.checked = true;
                smtpSslCheckbox.checked = false;
            } else if (host.includes('sendgrid.com')) {
                smtpPortInput.value = '587';
                smtpTlsCheckbox.checked = true;
                smtpSslCheckbox.checked = false;
            }
        });
    }
    
    // Validate form before submission
    const emailFormValidation = document.querySelector('form input[name="form_type"][value="smtp_settings"]');
    if (emailFormValidation) {
        emailFormValidation.addEventListener('submit', function(e) {
            const smtpEnabled = document.getElementById('smtp_enabled').checked;
            
            if (smtpEnabled) {
                const smtpHost = document.getElementById('smtp_host').value.trim();
                const smtpUsername = document.getElementById('smtp_username').value.trim();
                const smtpFromEmail = document.getElementById('smtp_from_email').value.trim();
                
                if (!smtpHost) {
                    alert('Please enter an SMTP host.');
                    e.preventDefault();
                    return false;
                }
                
                if (!smtpUsername) {
                    alert('Please enter an SMTP username/email.');
                    e.preventDefault();
                    return false;
                }
                
                if (!smtpFromEmail) {
                    alert('Please enter a from email address.');
                    e.preventDefault();
                    return false;
                }
            }
        });
    }
});
