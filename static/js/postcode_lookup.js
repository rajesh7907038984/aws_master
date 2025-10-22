/**
 * Postcode Lookup JavaScript
 * Automatically looks up UK addresses when postcode is entered and provides address selection
 */

document.addEventListener('DOMContentLoaded', function() {
    const postcodeInput = document.querySelector('[name="current_postcode"]');
    const postcodeStatusElement = document.getElementById('postcode-lookup-status');
    const addressSelectorContainer = document.getElementById('address-selector-container');
    const addressSelector = document.getElementById('address-selector');
    const isNonUkCheckbox = document.querySelector('[name="is_non_uk_address"]');
    
    // Address field inputs
    const addressLine1Input = document.querySelector('[name="address_line1"]');
    const addressLine2Input = document.querySelector('[name="address_line2"]');
    const cityInput = document.querySelector('[name="city"]');
    const countyInput = document.querySelector('[name="county"]');
    const countryInput = document.querySelector('[name="country"]');

    if (!postcodeInput) {
        console.log('Postcode input not found');
        return;
    }

    console.log('Postcode lookup script loaded');

    let debounceTimeout;
    let currentPostcode = '';

    // Add event listener for postcode input
    postcodeInput.addEventListener('input', function(e) {
        const postcode = e.target.value.trim().toUpperCase();
        
        // Clear previous timeout
        clearTimeout(debounceTimeout);
        
        // Hide address selector if postcode is cleared
        if (!postcode) {
            if (addressSelectorContainer) {
                addressSelectorContainer.classList.add('hidden');
            }
            if (postcodeStatusElement) {
                postcodeStatusElement.classList.add('hidden');
            }
            return;
        }

        // Debounce the lookup to avoid too many API calls
        debounceTimeout = setTimeout(() => {
            if (postcode !== currentPostcode && postcode.length >= 5) {
                currentPostcode = postcode;
                performPostcodeLookup(postcode);
            }
        }, 800); // Wait 800ms after user stops typing
    });

    // Add event listener for address selection
    if (addressSelector) {
        addressSelector.addEventListener('change', function() {
            const selectedValue = this.value;
            
            if (selectedValue) {
                try {
                    const addressData = TypeSafety.safeJsonParse(selectedValue, {});
                    console.log('Selected address:', addressData);
                    
                    // Fill address fields
                    if (addressLine1Input) {
                        addressLine1Input.value = addressData.line_1 || '';
                    }
                    if (addressLine2Input) {
                        addressLine2Input.value = addressData.line_2 || '';
                    }
                    if (cityInput) {
                        cityInput.value = addressData.post_town || '';
                    }
                    if (countyInput) {
                        countyInput.value = addressData.county || '';
                    }
                    if (countryInput) {
                        countryInput.value = addressData.country || 'United Kingdom';
                    }
                    
                    // Trigger change events
                    [addressLine1Input, addressLine2Input, cityInput, countyInput, countryInput].forEach(input => {
                        if (input) {
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    });
                    
                    // Add visual indication
                    setTimeout(() => {
                        [addressLine1Input, addressLine2Input, cityInput, countyInput, countryInput].forEach(input => {
                            if (input && input.value) {
                                input.style.backgroundColor = '#f0f9ff';
                                input.style.borderColor = '#0ea5e9';
                                input.style.transition = 'all 0.3s ease';
                                
                                setTimeout(() => {
                                    input.style.backgroundColor = '';
                                    input.style.borderColor = '';
                                }, 2000);
                            }
                        });
                    }, 100);
                    
                    showNotification('Address populated from postcode lookup!', 'success');
                    
                } catch (error) {
                    console.error('Error parsing selected address:', error);
                }
            } else {
                console.log('User cleared address selection - manual entry mode');
            }
        });
    }

    // Handle non-UK address checkbox
    if (isNonUkCheckbox) {
        isNonUkCheckbox.addEventListener('change', function() {
            if (this.checked) {
                // Set placeholder postcode for non-UK addresses
                postcodeInput.value = 'ZZ99 9ZZ';
                
                // Hide any status messages and address selector
                if (postcodeStatusElement) {
                    postcodeStatusElement.classList.add('hidden');
                }
                if (addressSelectorContainer) {
                    addressSelectorContainer.classList.add('hidden');
                }
                
                // Focus on the address line 1 for manual entry
                if (addressLine1Input) addressLine1Input.focus();
            } else {
                // Clear postcode for UK addresses
                postcodeInput.value = '';
                
                // Hide any status messages and address selector
                if (postcodeStatusElement) {
                    postcodeStatusElement.classList.add('hidden');
                }
                if (addressSelectorContainer) {
                    addressSelectorContainer.classList.add('hidden');
                }
            }
        });
    }

    function performPostcodeLookup(postcode) {
        console.log('🔍 Starting postcode address lookup for:', postcode);
        
        // Basic UK postcode validation
        const postcodeRegex = /^[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}$/i;
        
        if (!postcodeRegex.test(postcode)) {
            console.log(' Invalid UK postcode format:', postcode);
            if (postcodeStatusElement) {
                postcodeStatusElement.classList.remove('hidden');
                postcodeStatusElement.innerHTML = `
                    <div class="flex items-center text-orange-700">
                        <svg class="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                        </svg>
                        <span>Invalid UK postcode format</span>
                    </div>
                `;
                setTimeout(() => {
                    postcodeStatusElement.classList.add('hidden');
                }, 3000);
            }
            return;
        }
        
        // Check if it's the special ZZ99 9ZZ code
        if (postcode.toUpperCase() === 'ZZ99 9ZZ') {
            console.log(' Skipping placeholder postcode');
            // Hide address selector for placeholder postcode
            if (addressSelectorContainer) {
                addressSelectorContainer.classList.add('hidden');
            }
            return;
        }
        
        console.log(' Valid postcode format, proceeding with address lookup');

        // Show loading status
        if (postcodeStatusElement) {
            postcodeStatusElement.classList.remove('hidden');
            postcodeStatusElement.innerHTML = `
                <div class="flex items-center">
                    <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500 mr-2"></div>
                    <span>Looking up addresses...</span>
                </div>
            `;
        }

        // Use our address lookup endpoint
        const apiUrl = `${window.POSTCODE_LOOKUP_URL || '/users/api/public/lookup-postcode-addresses/'}?postcode=${encodeURIComponent(postcode)}`;
        
        console.log(' Looking up addresses for postcode:', postcode, 'URL:', apiUrl);
        
        // Make the API call with retry logic
        function makeAPICall(retryCount = 0) {
            return fetch(apiUrl)
            .catch(error => {
                if (retryCount < 2) {
                    console.log(` Retry attempt ${retryCount + 1} for address lookup`);
                    return new Promise(resolve => setTimeout(resolve, 1000)).then(() => makeAPICall(retryCount + 1));
                }
                throw error;
            });
        }
        
        makeAPICall()
        .then(response => {
            console.log('API response status:', response.status);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('API response data:', data);
            
            if (data.status === 'success' && data.addresses && data.addresses.length > 0) {
                console.log(` Found ${data.addresses.length} addresses for postcode ${postcode}`);
                
                // Show success status
                if (postcodeStatusElement) {
                    postcodeStatusElement.innerHTML = `
                        <div class="flex items-center text-green-600">
                            <svg class="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                            </svg>
                            <span>Found ${data.addresses.length} address${data.addresses.length === 1 ? '' : 'es'}</span>
                        </div>
                    `;
                }
                
                // Populate address selector
                if (addressSelector) {
                    addressSelector.innerHTML = '<option value="">Please select an address...</option>';
                    
                    data.addresses.forEach(address => {
                        const option = document.createElement('option');
                        option.value = JSON.stringify(address);
                        option.textContent = address.display;
                        addressSelector.appendChild(option);
                    });
                }
                
                // Show address selector
                if (addressSelectorContainer) {
                    addressSelectorContainer.classList.remove('hidden');
                }
                
                // Hide status after 3 seconds
                setTimeout(() => {
                    if (postcodeStatusElement) {
                        postcodeStatusElement.classList.add('hidden');
                    }
                }, 3000);
                
            } else {
                throw new Error(data.message || 'No addresses found for this postcode');
            }
        })
        .catch(error => {
            console.error(' Postcode lookup error:', error);
            
            if (postcodeStatusElement) {
                postcodeStatusElement.innerHTML = `
                    <div class="flex items-center text-red-600">
                        <svg class="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                        </svg>
                        <span>Postcode lookup failed. Enter address manually.</span>
                    </div>
                `;
            }
            
            // Hide address selector on error
            if (addressSelectorContainer) {
                addressSelectorContainer.classList.add('hidden');
            }
            
            // Hide error status after 5 seconds
            setTimeout(() => {
                if (postcodeStatusElement) {
                    postcodeStatusElement.classList.add('hidden');
                }
            }, 5000);
        });
    }

    function showNotification(message, type) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 z-50 px-4 py-2 rounded-lg shadow-lg text-white font-medium ${
            type === 'success' ? 'bg-green-500' : 'bg-red-500'
        }`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        // Animate in
        setTimeout(() => {
            notification.style.transform = 'translateX(0)';
            notification.style.opacity = '1';
        }, 100);
        
        // Remove after 4 seconds
        setTimeout(() => {
            notification.style.transform = 'translateX(100%)';
            notification.style.opacity = '0';
            setTimeout(() => {
                if (notification.parentNode) {
                    document.body.removeChild(notification);
                }
            }, 300);
        }, 4000);
    }
}); 