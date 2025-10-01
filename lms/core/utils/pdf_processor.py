"""
Optimized PDF processing utilities to prevent memory leaks and browser crashes.

This module provides cached, memory-efficient PDF processing functionality
that addresses the "Aw, Snap!" Chrome errors caused by excessive memory usage.
"""

import logging
import gc
import psutil
from typing import Optional, Dict, List, Any
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

# Global PDF module cache
_PDFPLUMBER_MODULE = None
_REPORTLAB_MODULES = {}

def get_pdfplumber():
    """
    Get cached pdfplumber module to prevent repeated imports and memory spikes.
    
    Returns:
        pdfplumber module or None if not available
    """
    global _PDFPLUMBER_MODULE
    
    if _PDFPLUMBER_MODULE is not None:
        return _PDFPLUMBER_MODULE
    
    try:
        import pdfplumber
        _PDFPLUMBER_MODULE = pdfplumber
        logger.info(f"pdfplumber loaded successfully, version: {pdfplumber.__version__}")
        return _PDFPLUMBER_MODULE
    except ImportError:
        logger.warning("pdfplumber not available - PDF text extraction disabled")
        return None
    except Exception as e:
        logger.error(f"Error loading pdfplumber: {str(e)}")
        return None

def get_reportlab_module(module_name: str):
    """
    Get cached reportlab module to prevent repeated imports.
    
    Args:
        module_name: Name of the reportlab module (e.g., 'canvas', 'pagesizes')
        
    Returns:
        Requested module or None if not available
    """
    global _REPORTLAB_MODULES
    
    if module_name in _REPORTLAB_MODULES:
        return _REPORTLAB_MODULES[module_name]
    
    try:
        if module_name == 'canvas':
            from reportlab.pdfgen import canvas
            _REPORTLAB_MODULES[module_name] = canvas
            return canvas
        elif module_name == 'pagesizes':
            from reportlab.lib import pagesizes
            _REPORTLAB_MODULES[module_name] = pagesizes
            return pagesizes
        elif module_name == 'colors':
            from reportlab.lib import colors
            _REPORTLAB_MODULES[module_name] = colors
            return colors
        else:
            logger.warning(f"Unknown reportlab module requested: {module_name}")
            return None
    except ImportError:
        logger.warning(f"reportlab.{module_name} not available")
        return None
    except Exception as e:
        logger.error(f"Error loading reportlab.{module_name}: {str(e)}")
        return None

def get_weasyprint():
    """
    Get weasyprint modules for PDF generation.
    
    Returns:
        Tuple of (HTML, CSS) classes or (None, None) if not available
    """
    try:
        from weasyprint import HTML, CSS
        return HTML, CSS
    except ImportError:
        logger.warning("weasyprint not available - PDF generation disabled")
        return None, None
    except Exception as e:
        logger.error(f"Error loading weasyprint: {str(e)}")
        return None, None

def monitor_memory_usage(operation_name: str):
    """
    Monitor memory usage for PDF operations.
    
    Args:
        operation_name: Name of the operation for logging
        
    Returns:
        Current memory usage in MB
    """
    try:
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        logger.debug(f"Memory usage during {operation_name}: {memory_mb:.1f}MB")
        return memory_mb
    except Exception:
        return 0

def cleanup_pdf_memory():
    """
    Clean up memory after PDF operations to prevent accumulation.
    """
    try:
        # Force garbage collection
        gc.collect()
        logger.debug("PDF memory cleanup completed")
    except Exception as e:
        logger.error(f"Error during PDF memory cleanup: {str(e)}")

class PDFProcessor:
    """
    Memory-optimized PDF processor with caching and cleanup.
    """
    
    def __init__(self, cache_timeout: int = 300):
        self.cache_timeout = cache_timeout
        self.memory_threshold = getattr(settings, 'MEMORY_THRESHOLD_MB', 400)
    
    def extract_text_from_pdf(self, file_path: str, cache_key: Optional[str] = None) -> Optional[str]:
        """
        Extract text from PDF with memory monitoring and caching.
        
        Args:
            file_path: Path to the PDF file
            cache_key: Optional cache key for the extracted text
            
        Returns:
            Extracted text or None if extraction failed
        """
        # Check cache first
        if cache_key:
            cached_text = cache.get(f"pdf_text_{cache_key}")
            if cached_text:
                logger.debug(f"Using cached PDF text for key: {cache_key}")
                return cached_text
        
        # Monitor memory before processing
        initial_memory = monitor_memory_usage("pdf_text_extraction_start")
        
        pdfplumber = get_pdfplumber()
        if not pdfplumber:
            logger.error("pdfplumber not available for text extraction")
            return None
        
        try:
            # Check if we have enough memory
            if initial_memory > self.memory_threshold * 0.8:  # 80% of threshold
                logger.warning(f"Memory usage too high for PDF processing: {initial_memory:.1f}MB")
                return None
            
            with pdfplumber.open(file_path) as pdf:
                text_parts = []
                
                for page_num, page in enumerate(pdf.pages):
                    # Monitor memory per page
                    page_memory = monitor_memory_usage(f"pdf_page_{page_num}")
                    
                    if page_memory > self.memory_threshold:
                        logger.warning(f"Memory threshold exceeded during page {page_num}: {page_memory:.1f}MB")
                        break
                    
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                    
                    # Cleanup every 10 pages
                    if (page_num + 1) % 10 == 0:
                        cleanup_pdf_memory()
                
                extracted_text = "\n\n".join(text_parts)
                
                # Cache the result
                if cache_key and extracted_text:
                    cache.set(f"pdf_text_{cache_key}", extracted_text, self.cache_timeout)
                    logger.debug(f"Cached PDF text with key: {cache_key}")
                
                return extracted_text
        
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {str(e)}")
            return None
        
        finally:
            # Always cleanup after PDF processing
            cleanup_pdf_memory()
            final_memory = monitor_memory_usage("pdf_text_extraction_complete")
            logger.debug(f"Memory change: {final_memory - initial_memory:+.1f}MB")
    
    def extract_cv_data(self, file_path: str, cache_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract structured CV data from PDF with enhanced memory management.
        
        Args:
            file_path: Path to the CV PDF file
            cache_key: Optional cache key for the extracted data
            
        Returns:
            Dictionary containing extracted CV data
        """
        # Check cache first
        if cache_key:
            cached_data = cache.get(f"cv_data_{cache_key}")
            if cached_data:
                logger.debug(f"Using cached CV data for key: {cache_key}")
                return cached_data
        
        initial_memory = monitor_memory_usage("cv_extraction_start")
        
        try:
            # Extract raw text first
            text = self.extract_text_from_pdf(file_path, f"{cache_key}_text" if cache_key else None)
            if not text:
                return {'error': 'Failed to extract text from PDF'}
            
            # Process the text to extract structured data
            cv_data = self._process_cv_text(text)
            
            # Cache the result
            if cache_key and cv_data:
                cache.set(f"cv_data_{cache_key}", cv_data, self.cache_timeout)
                logger.debug(f"Cached CV data with key: {cache_key}")
            
            return cv_data
        
        except Exception as e:
            logger.error(f"Error extracting CV data from {file_path}: {str(e)}")
            return {'error': f'CV processing failed: {str(e)}'}
        
        finally:
            cleanup_pdf_memory()
            final_memory = monitor_memory_usage("cv_extraction_complete")
            logger.debug(f"CV extraction memory change: {final_memory - initial_memory:+.1f}MB")
    
    def _process_cv_text(self, text: str) -> Dict[str, Any]:
        """
        Process extracted text to identify CV components.
        
        Args:
            text: Raw text extracted from CV
            
        Returns:
            Dictionary with structured CV data
        """
        import re
        from datetime import datetime
        
        cv_data = {
            'text': text,
            'email': None,
            'phone': None,
            'name': None,
            'skills': [],
            'education': [],
            'experience': [],
            'processed_at': datetime.now().isoformat()
        }
        
        try:
            # Extract email
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            email_matches = re.findall(email_pattern, text)
            if email_matches:
                cv_data['email'] = email_matches[0]
            
            # Extract phone numbers
            phone_pattern = r'(\+?[\d\s\-\(\)\.]{10,})'
            phone_matches = re.findall(phone_pattern, text)
            if phone_matches:
                cv_data['phone'] = phone_matches[0].strip()
            
            # Extract potential names (first few lines, common patterns)
            lines = text.split('\n')[:10]  # Check first 10 lines
            for line in lines:
                line = line.strip()
                if len(line) > 3 and len(line) < 50 and not any(char.isdigit() for char in line):
                    if '@' not in line and 'http' not in line:
                        cv_data['name'] = line
                        break
            
            # Extract skills (basic keyword matching)
            skill_keywords = [
                'python', 'django', 'javascript', 'html', 'css', 'sql', 'mysql', 'postgresql',
                'react', 'vue', 'angular', 'node.js', 'php', 'java', 'c++', 'c#', 'ruby',
                'git', 'docker', 'aws', 'azure', 'linux', 'windows', 'mac', 'excel',
                'word', 'powerpoint', 'photoshop', 'illustrator'
            ]
            
            text_lower = text.lower()
            found_skills = [skill for skill in skill_keywords if skill in text_lower]
            cv_data['skills'] = list(set(found_skills))  # Remove duplicates
            
            logger.debug(f"Processed CV: found {len(found_skills)} skills, email: {bool(cv_data['email'])}")
            
        except Exception as e:
            logger.error(f"Error processing CV text: {str(e)}")
            cv_data['processing_error'] = str(e)
        
        return cv_data

# Global instance for easy import
pdf_processor = PDFProcessor()
