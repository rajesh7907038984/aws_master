"""
File Processing Error Handler
Handles file upload and processing errors to prevent 500 errors
"""

import logging
import os
import mimetypes
from typing import Dict, Any, Optional, List
from django.core.files.uploadedfile import UploadedFile
from django.core.exceptions import ValidationError
from django.conf import settings

logger = logging.getLogger(__name__)

class FileProcessingHandler:
    """Comprehensive file processing error handler"""
    
    def __init__(self):
        self.max_file_size = getattr(settings, 'MAX_FILE_SIZE', 10 * 1024 * 1024)  # 10MB default
        self.allowed_extensions = getattr(settings, 'ALLOWED_FILE_EXTENSIONS', [
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg',
            '.mp4', '.avi', '.mov', '.wmv', '.flv',
            '.mp3', '.wav', '.ogg', '.m4a',
            '.zip', '.rar', '.7z'
        ])
        self.allowed_mime_types = getattr(settings, 'ALLOWED_MIME_TYPES', [
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/svg+xml',
            'video/mp4', 'video/avi', 'video/quicktime', 'video/x-msvideo',
            'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp4',
            'application/zip', 'application/x-rar-compressed', 'application/x-7z-compressed'
        ])
    
    def validate_file(self, file: UploadedFile) -> Dict[str, Any]:
        """Validate uploaded file with comprehensive checks"""
        try:
            # Check file size
            if file.size > self.max_file_size:
                return {
                    'valid': False,
                    'error': 'File size exceeds maximum allowed size',
                    'error_type': 'FILE_SIZE_ERROR',
                    'max_size': self.max_file_size,
                    'file_size': file.size
                }
            
            # Check file extension
            file_name = file.name.lower()
            file_extension = os.path.splitext(file_name)[1]
            
            if file_extension not in self.allowed_extensions:
                return {
                    'valid': False,
                    'error': f'File type {file_extension} is not allowed',
                    'error_type': 'FILE_TYPE_ERROR',
                    'allowed_extensions': self.allowed_extensions,
                    'file_extension': file_extension
                }
            
            # Check MIME type
            file_mime_type = file.content_type
            if file_mime_type not in self.allowed_mime_types:
                return {
                    'valid': False,
                    'error': f'MIME type {file_mime_type} is not allowed',
                    'error_type': 'MIME_TYPE_ERROR',
                    'allowed_mime_types': self.allowed_mime_types,
                    'file_mime_type': file_mime_type
                }
            
            # Check for malicious file names
            if self._is_malicious_filename(file_name):
                return {
                    'valid': False,
                    'error': 'File name contains potentially malicious characters',
                    'error_type': 'MALICIOUS_FILENAME_ERROR'
                }
            
            return {
                'valid': True,
                'file_name': file.name,
                'file_size': file.size,
                'file_type': file_mime_type,
                'file_extension': file_extension
            }
            
        except Exception as e:
            logger.error(f"Error validating file {file.name}: {str(e)}")
            return {
                'valid': False,
                'error': 'File validation failed',
                'error_type': 'VALIDATION_ERROR',
                'details': str(e)
            }
    
    def _is_malicious_filename(self, filename: str) -> bool:
        """Check for potentially malicious file names"""
        malicious_patterns = [
            '..',  # Directory traversal
            '/',   # Path separator
            '\\',  # Windows path separator
            '<',   # HTML/XML injection
            '>',   # HTML/XML injection
            '|',   # Command injection
            '&',   # Command injection
            ';',   # Command injection
            '`',   # Command injection
            '$',   # Variable substitution
            '(',   # Command injection
            ')',   # Command injection
        ]
        
        return any(pattern in filename for pattern in malicious_patterns)
    
    def safe_file_operation(self, operation_func, file: UploadedFile, *args, **kwargs):
        """Safely execute file operations with error handling"""
        try:
            # Validate file first
            validation_result = self.validate_file(file)
            if not validation_result['valid']:
                raise ValidationError(validation_result['error'])
            
            # Execute the operation
            return operation_func(file, *args, **kwargs)
            
        except ValidationError as e:
            logger.warning(f"File validation error: {str(e)}")
            raise e
        except FileNotFoundError as e:
            logger.error(f"File not found: {str(e)}")
            raise e
        except PermissionError as e:
            logger.error(f"File permission error: {str(e)}")
            raise e
        except OSError as e:
            logger.error(f"File system error: {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected file operation error: {str(e)}")
            raise e
    
    def handle_excel_processing(self, file: UploadedFile) -> Dict[str, Any]:
        """Handle Excel file processing with specific error handling"""
        try:
            import pandas as pd
        except ImportError:
            return {
                'success': False,
                'error': 'Excel processing library not available',
                'error_type': 'LIBRARY_UNAVAILABLE',
                'message': 'Please contact your administrator to install the required Excel processing library.'
            }
        
        try:
            # Read Excel file with error handling
            df = pd.read_excel(file)
            
            return {
                'success': True,
                'dataframe': df,
                'rows': len(df),
                'columns': list(df.columns)
            }
            
        except Exception as e:
            error_message = "Error processing Excel file"
            
            if "password" in str(e).lower():
                error_message = "Excel file is password protected. Please remove password protection and try again."
            elif "format" in str(e).lower() or "invalid" in str(e).lower():
                error_message = "Invalid Excel file format. Please ensure the file is a valid Excel file."
            elif "permission" in str(e).lower():
                error_message = "Permission denied reading Excel file. Please check file permissions."
            
            logger.error(f"Excel processing error: {str(e)}")
            return {
                'success': False,
                'error': error_message,
                'error_type': 'EXCEL_PROCESSING_ERROR',
                'details': str(e)
            }
    
    def handle_pdf_processing(self, file: UploadedFile) -> Dict[str, Any]:
        """Handle PDF file processing with specific error handling"""
        try:
            import pdfplumber
        except ImportError:
            return {
                'success': False,
                'error': 'PDF processing library not available',
                'error_type': 'LIBRARY_UNAVAILABLE',
                'message': 'Please contact your administrator to install the required PDF processing library.'
            }
        
        try:
            with pdfplumber.open(file) as pdf:
                text_content = ""
                for page in pdf.pages:
                    text_content += page.extract_text() or ""
                
                return {
                    'success': True,
                    'text_content': text_content,
                    'page_count': len(pdf.pages)
                }
                
        except Exception as e:
            logger.error(f"PDF processing error: {str(e)}")
            return {
                'success': False,
                'error': 'Failed to process PDF file',
                'error_type': 'PDF_PROCESSING_ERROR',
                'details': str(e)
            }
    
    def handle_image_processing(self, file: UploadedFile) -> Dict[str, Any]:
        """Handle image file processing with specific error handling"""
        try:
            from PIL import Image
        except ImportError:
            return {
                'success': False,
                'error': 'Image processing library not available',
                'error_type': 'LIBRARY_UNAVAILABLE',
                'message': 'Please contact your administrator to install the required image processing library.'
            }
        
        try:
            with Image.open(file) as img:
                return {
                    'success': True,
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode
                }
                
        except Exception as e:
            logger.error(f"Image processing error: {str(e)}")
            return {
                'success': False,
                'error': 'Failed to process image file',
                'error_type': 'IMAGE_PROCESSING_ERROR',
                'details': str(e)
            }

# Global file processing handler
file_handler = FileProcessingHandler()

def safe_file_operation(operation_func, file: UploadedFile, *args, **kwargs):
    """Convenience function for safe file operations"""
    return file_handler.safe_file_operation(operation_func, file, *args, **kwargs)

def validate_uploaded_file(file: UploadedFile) -> Dict[str, Any]:
    """Convenience function to validate uploaded files"""
    return file_handler.validate_file(file)
