// Common utility functions
class CommonUtils {
    static getCookie(name) {
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

    static initializeRichTextEditors() {
        const textEditors = document.querySelectorAll('.rich-text-editor');
        textEditors.forEach(editor => {
            ClassicEditor
                .create(editor)
                .catch(error => {
                    console.error(error);
                });
        });
    }

    static formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    static validateFileType(file, allowedTypes) {
        return allowedTypes.includes(file.type);
    }

    static validateFileSize(file, maxSize) {
        return file.size <= maxSize;
    }
}

// Export for use in other modules
window.CommonUtils = CommonUtils; 