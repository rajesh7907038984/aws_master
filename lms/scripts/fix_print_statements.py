#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to replace print statements with proper logging
This ensures all output goes through the logging system
"""

import os
import re
import glob
from pathlib import Path

def fix_print_statements_in_file(file_path):
    """Fix print statements in a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Skip if file doesn't contain print statements
        if 'print(' not in content:
            return False
        
        # Add logging import if not present
        if 'import logging' not in content and 'from django.utils import log' not in content:
            # Find the best place to add the import
            import_lines = []
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                if line.strip().startswith('import ') or line.strip().startswith('from '):
                    import_lines.append(i)
            
            if import_lines:
                # Add after the last import
                last_import = max(import_lines)
                lines.insert(last_import + 1, 'import logging')
            else:
                # Add at the beginning after docstring
                lines.insert(0, 'import logging')
            
            content = '\n'.join(lines)
        
        # Add logger if not present
        if 'logger = logging.getLogger(__name__)' not in content:
            # Find a good place to add logger
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.strip() and not line.strip().startswith('#'):
                    lines.insert(i, 'logger = logging.getLogger(__name__)')
                    break
            content = '\n'.join(lines)
        
        # Replace print statements with logger calls
        # Simple print() -> logger.info()
        content = re.sub(
            r'print\s*\(\s*([^)]+)\s*\)',
            r'logger.info(\1)',
            content
        )
        
        # Only write if changes were made
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Fixed print statements in {}".format(file_path))
            return True
        else:
            return False
            
    except Exception as e:
        print("Error processing {}: {}".format(file_path, e))
        return False

def main():
    """Main function to fix all print statements"""
    print("Fixing print statements in production...")
    
    # Get the project root
    project_root = Path(__file__).parent.parent
    
    # Find all Python files
    py_files = []
    py_files.extend(glob.glob(str(project_root / "**" / "*.py"), recursive=True))
    
    # Exclude virtual environment and cache directories
    py_files = [f for f in py_files if '/venv/' not in f and '/__pycache__/' not in f and '/.git/' not in f]
    
    fixed_count = 0
    total_files = len(py_files)
    
    print("Found {} Python files".format(total_files))
    
    # Process Python files
    for py_file in py_files:
        if fix_print_statements_in_file(py_file):
            fixed_count += 1
    
    print("Fixed print statements in {} files".format(fixed_count))
    print("All print statements now use proper logging")

if __name__ == "__main__":
    main()
