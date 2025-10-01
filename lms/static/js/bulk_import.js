// Global variables to store the validated data
let validatedData = [];
let hasErrors = false;

// Show the bulk import modal
function showBulkImportModal() {
    console.log('Showing bulk import modal...');
    const modal = document.getElementById('bulkImportModal');
    console.log('Modal element:', modal);
    if (modal) {
        modal.classList.remove('hidden');
        console.log('Hidden class removed');
    } else {
        console.error('Modal element not found!');
    }
}

// Close the bulk import modal
function closeBulkImportModal() {
    console.log('Closing bulk import modal...');
    const modal = document.getElementById('bulkImportModal');
    console.log('Modal element:', modal);
    if (modal) {
        modal.classList.add('hidden');
        console.log('Hidden class added');
        resetForm();
    } else {
        console.error('Modal element not found!');
    }
}

// Reset the form state
function resetForm() {
    document.getElementById('file-upload').value = '';
    document.getElementById('previewSection').classList.add('hidden');
    document.getElementById('errorMessages').classList.add('hidden');
    document.getElementById('importButton').disabled = true;
    document.getElementById('previewTableBody').innerHTML = '';
    validatedData = [];
    hasErrors = false;
}

// Handle file upload and preview
document.getElementById('file-upload').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/users/validate-bulk-import/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });

        const data = await response.json();
        
        if (response.ok) {
            displayPreview(data.users);
            validatedData = data.users;
            hasErrors = data.has_errors;
            document.getElementById('importButton').disabled = hasErrors;
        } else {
            showError(data.error || 'An error occurred while processing the file.');
        }
    } catch (error) {
        showError('An error occurred while uploading the file.');
    }
});

// Display preview of uploaded data
function displayPreview(users) {
    const tableBody = document.getElementById('previewTableBody');
    tableBody.innerHTML = '';
    
    users.forEach((user, index) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap">
                <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                    ${user.is_valid ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}">
                    ${user.is_valid ? 'Valid' : 'Error'}
                </span>
            </td>
            <td class="px-4 py-4 whitespace-nowrap">
                <input type="text" value="${user.name}" 
                    class="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm
                    ${user.errors?.name ? 'border-red-300' : ''}"
                    onchange="updateUserData(${index}, 'name', this.value)">
            </td>
            <td class="px-4 py-4 whitespace-nowrap">
                <input type="email" value="${user.email}" 
                    class="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm
                    ${user.errors?.email ? 'border-red-300' : ''}"
                    onchange="updateUserData(${index}, 'email', this.value)">
            </td>
            <td class="px-4 py-4 whitespace-nowrap">
                <select class="w-full border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm
                    ${user.errors?.role ? 'border-red-300' : ''}"
                    onchange="updateUserData(${index}, 'role', this.value)">
                    <option value="learner" ${user.role === 'learner' ? 'selected' : ''}>Learner</option>
                    <option value="instructor" ${user.role === 'instructor' ? 'selected' : ''}>Instructor</option>
                    <option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin</option>
                    <option value="superadmin" ${user.role === 'superadmin' ? 'selected' : ''}>Superadmin</option>
                </select>
            </td>
            <td class="px-4 py-4 whitespace-nowrap text-right text-sm font-medium">
                <button onclick="deleteRow(${index})" class="text-red-600 hover:text-red-900">
                    Delete
                </button>
            </td>
        `;
        
        if (user.errors) {
            const errorTip = document.createElement('div');
            errorTip.className = 'text-xs text-red-600 mt-1';
            errorTip.textContent = Object.values(user.errors).join(', ');
            row.cells[1].appendChild(errorTip);
        }
        
        tableBody.appendChild(row);
    });

    document.getElementById('previewSection').classList.remove('hidden');
}

// Update user data in the validatedData array
function updateUserData(index, field, value) {
    validatedData[index][field] = value;
    validateAndUpdateUI();
}

// Delete a row from the preview table
function deleteRow(index) {
    validatedData.splice(index, 1);
    displayPreview(validatedData);
    validateAndUpdateUI();
}

// Validate the current data and update UI accordingly
async function validateAndUpdateUI() {
    try {
        const response = await fetch('/users/validate-bulk-data/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ users: validatedData })
        });

        const data = await response.json();
        if (response.ok) {
            validatedData = data.users;
            hasErrors = data.has_errors;
            document.getElementById('importButton').disabled = hasErrors;
            displayPreview(data.users);
        } else {
            showError(data.error || 'An error occurred while validating the data.');
        }
    } catch (error) {
        showError('An error occurred while validating the data.');
    }
}

// Submit the bulk import
async function submitBulkImport() {
    try {
        const response = await fetch('/users/bulk-import/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ users: validatedData })
        });

        const data = await response.json();
        if (response.ok) {
            closeBulkImportModal();
            // Refresh the user list
            window.location.reload();
        } else {
            showError(data.error || 'An error occurred while importing users.');
        }
    } catch (error) {
        showError('An error occurred while importing users.');
    }
}

// Show error message
function showError(message) {
    const errorDiv = document.getElementById('errorMessages');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

// Get CSRF token from cookies
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Handle drag and drop
const dropZone = document.querySelector('.border-dashed');
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, highlight, false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, unhighlight, false);
});

function highlight(e) {
    dropZone.classList.add('border-indigo-500');
}

function unhighlight(e) {
    dropZone.classList.remove('border-indigo-500');
}

dropZone.addEventListener('drop', handleDrop, false);

function handleDrop(e) {
    const dt = e.dataTransfer;
    const file = dt.files[0];
    
    const fileInput = document.getElementById('file-upload');
    fileInput.files = dt.files;
    fileInput.dispatchEvent(new Event('change'));
} 