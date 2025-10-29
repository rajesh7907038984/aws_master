/**
 * Comprehensive Secure Filename Validator for LMS (JavaScript)
 * =============================================================
 * 
 * Frontend companion to the Python SecureFilenameValidator.
 * Provides real-time validation feedback to users.
 */

class SecureFilenameValidator {
    constructor(options = {}) {
        this.allowedCategories = options.allowedCategories || ['general'];
        this.maxSizeMB = options.maxSizeMB || null;
        this.customExtensions = options.customExtensions || null;
        
        // Security patterns (matches Python version)
        this.dangerousPatterns = [
            /\.\.+/,              // Path traversal attempts
            /^\.+/,               // Hidden files
            /[<>:"|?*]/,         // Windows reserved characters
            /[\x00-\x1f\x7f]/,   // Control characters
            /[\\/]/,             // Path separators
        ];
        
        // Dangerous extensions
        this.dangerousExtensions = new Set([
            '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.vbe',
            '.js', '.jse', '.wsf', '.wsh', '.msc', '.jar', '.php', '.asp', 
            '.aspx', '.jsp', '.py', '.rb', '.pl', '.sh', '.ps1', '.psm1'
        ]);
        
        // Allowed extensions by category
        this.allowedExtensions = {
            'image': new Set(['.jpg', '.jpeg', '.png']),
            'document': new Set(['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.csv', '.ppt', '.pptx']),
            'video': new Set(['.mp4', '.webm']),
            'audio': new Set(['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac']),
            'archive': new Set(['.zip', '.rar', '.7z', '.tar', '.gz']),
            'general': null
        };
        
        // Validation messages
        this.validationMessages = {
            'tooLong': 'Filename is too long. Please use a filename shorter than {maxLength} characters.',
            'empty': 'Filename cannot be empty.',
            'dangerousExtension': 'File type "{ext}" is not allowed for security reasons. Please use a different file format.',
            'extensionNotAllowed': 'File type "{ext}" is not allowed. Allowed formats: {allowedFormats}',
            'dangerousCharacters': 'Filename contains invalid characters. Please use only letters, numbers, spaces, hyphens (-), underscores (_), and dots (.).',
            'hiddenFile': 'Hidden files (starting with dots) are not allowed.',
            'pathTraversal': 'Filename contains path traversal patterns which are not allowed for security reasons.',
            'controlCharacters': 'Filename contains invalid control characters. Please use a simpler filename.',
            'doubleExtension': 'Files with double extensions are not allowed for security reasons.',
            'reservedName': 'This filename is reserved by the system. Please choose a different name.',
            'fileTooLarge': 'File size ({actualSize}MB) exceeds the maximum allowed size of {maxSize}MB.'
        };
        
        // Reserved names
        this.reservedNames = new Set([
            'con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4', 'com5', 
            'com6', 'com7', 'com8', 'com9', 'lpt1', 'lpt2', 'lpt3', 'lpt4', 
            'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
        ]);
        
        this.maxFilenameLength = 200;
    }
    
    /**
     * Validate a filename
     */
    validateFilename(filename) {
        if (!filename) {
            return {
                valid: false,
                errors: [this.validationMessages.empty]
            };
        }
        
        const errors = [];
        
        // Normalize filename (basic normalization)
        const normalizedFilename = filename.trim();
        
        // Extract parts
        const lastDotIndex = normalizedFilename.lastIndexOf('.');
        const baseName = lastDotIndex > 0 ? normalizedFilename.substring(0, lastDotIndex) : normalizedFilename;
        const extension = lastDotIndex > 0 ? normalizedFilename.substring(lastDotIndex).toLowerCase() : '';
        
        // Check filename length
        if (normalizedFilename.length > this.maxFilenameLength) {
            errors.push(this.validationMessages.tooLong.replace('{maxLength}', this.maxFilenameLength));
        }
        
        // Check for dangerous patterns
        for (const pattern of this.dangerousPatterns) {
            if (pattern.test(normalizedFilename)) {
                if (pattern.toString().includes('\\.\\.')) {
                    errors.push(this.validationMessages.pathTraversal);
                } else if (pattern.toString().includes('^\\.')) {
                    errors.push(this.validationMessages.hiddenFile);
                } else if (pattern.toString().includes('x00-x1f')) {
                    errors.push(this.validationMessages.controlCharacters);
                } else {
                    errors.push(this.validationMessages.dangerousCharacters);
                }
                break;
            }
        }
        
        // Check for dangerous extensions
        if (this.dangerousExtensions.has(extension)) {
            errors.push(this.validationMessages.dangerousExtension.replace('{ext}', extension));
        }
        
        // Check for double extensions
        const baseParts = baseName.split('.');
        if (baseParts.length > 1) {
            for (let i = 0; i < baseParts.length - 1; i++) {
                if (this.dangerousExtensions.has('.' + baseParts[i].toLowerCase())) {
                    errors.push(this.validationMessages.doubleExtension);
                    break;
                }
            }
        }
        
        // Check reserved names
        if (this.reservedNames.has(baseName.toLowerCase())) {
            errors.push(this.validationMessages.reservedName);
        }
        
        // Check allowed extensions
        let allowedExts = new Set();
        if (this.customExtensions) {
            allowedExts = new Set(this.customExtensions.map(ext => ext.toLowerCase()));
        } else {
            for (const category of this.allowedCategories) {
                if (this.allowedExtensions[category]) {
                    for (const ext of this.allowedExtensions[category]) {
                        allowedExts.add(ext);
                    }
                }
            }
        }
        
        if (allowedExts.size > 0 && extension && !allowedExts.has(extension)) {
            const formattedExts = Array.from(allowedExts).sort().join(', ').toUpperCase();
            errors.push(this.validationMessages.extensionNotAllowed
                .replace('{ext}', extension.toUpperCase())
                .replace('{allowedFormats}', formattedExts));
        }
        
        // Check base filename characters
        if (!/^[a-zA-Z0-9\s._\-()[\]{}]+$/.test(baseName)) {
            errors.push(this.validationMessages.dangerousCharacters);
        }
        
        return {
            valid: errors.length === 0,
            errors: errors,
            normalizedFilename: normalizedFilename
        };
    }
    
    /**
     * Validate a file object
     */
    validateFile(file) {
        const filenameResult = this.validateFilename(file.name);
        
        // Check file size if specified
        if (this.maxSizeMB && file.size) {
            const maxSizeBytes = this.maxSizeMB * 1024 * 1024;
            if (file.size > maxSizeBytes) {
                const actualSizeMB = (file.size / (1024 * 1024)).toFixed(1);
                filenameResult.errors.push(
                    this.validationMessages.fileTooLarge
                        .replace('{actualSize}', actualSizeMB)
                        .replace('{maxSize}', this.maxSizeMB)
                );
                filenameResult.valid = false;
            }
        }
        
        return filenameResult;
    }
    
    /**
     * Get help text for users
     */
    getHelpText() {
        const categories = this.allowedCategories;
        
        // Get allowed extensions
        let allowedExts = new Set();
        for (const category of categories) {
            if (this.allowedExtensions[category]) {
                for (const ext of this.allowedExtensions[category]) {
                    allowedExts.add(ext);
                }
            }
        }
        
        const helpParts = [];
        
        if (allowedExts.size > 0) {
            const extText = Array.from(allowedExts).sort().join(', ').toUpperCase();
            helpParts.push(`Allowed formats: ${extText}`);
        } else {
            helpParts.push('All file types allowed');
        }
        
        if (this.maxSizeMB) {
            helpParts.push(`Maximum size: ${this.maxSizeMB}MB`);
        }
        
        helpParts.push('Use simple filenames with letters, numbers, spaces, hyphens, and underscores');
        
        return helpParts.join(' • ');
    }
    
    /**
     * Create validator for specific category
     */
    static createCategoryValidator(category, maxSizeMB = null) {
        return new SecureFilenameValidator({
            allowedCategories: [category],
            maxSizeMB: maxSizeMB
        });
    }
    
    /**
     * Add real-time validation to a file input
     */
    attachToFileInput(fileInput, options = {}) {
        const showErrors = options.showErrors !== false;
        const errorContainer = options.errorContainer || null;
        const helpContainer = options.helpContainer || null;
        
        // Show help text
        if (helpContainer) {
            helpContainer.textContent = this.getHelpText();
            helpContainer.className = 'text-sm text-gray-600 mt-1';
        }
        
        fileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            
            // Clear previous errors
            if (errorContainer) {
                errorContainer.innerHTML = '';
                errorContainer.className = 'hidden';
            }
            
            if (!file) return;
            
            const result = this.validateFile(file);
            
            if (!result.valid && showErrors) {
                this.showErrors(result.errors, errorContainer);
                
                // Optionally clear the input
                if (options.clearOnError) {
                    event.target.value = '';
                }
                
                // Call error callback
                if (options.onError) {
                    options.onError(result.errors, file);
                }
            } else if (result.valid && options.onSuccess) {
                options.onSuccess(file);
            }
        });
    }
    
    /**
     * Show errors in UI
     */
    showErrors(errors, container) {
        if (!container) {
            console.error('Filename validation errors:', errors);
            return;
        }
        
        container.className = 'text-sm text-red-600 mt-1';
        container.innerHTML = errors.map(error => 
            `<div class="flex items-center"><svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg>${error}</div>`
        ).join('');
    }
}

// Global convenience functions
window.SecureFilenameValidator = SecureFilenameValidator;

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SecureFilenameValidator;
}
