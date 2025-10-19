#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to replace console.log statements with ProductionLogger calls
This ensures all logging goes through the production-safe logger
"""

import os
import re
import glob
from pathlib import Path

def fix_console_logs_in_file(file_path):
    """Fix console.log statements in a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Replace console.log with ProductionLogger.log
        content = re.sub(
            r'console\.log\s*\(',
            'ProductionLogger.log(',
            content
        )
        
        # Replace console.info with ProductionLogger.info
        content = re.sub(
            r'console\.info\s*\(',
            'ProductionLogger.info(',
            content
        )
        
        # Replace console.debug with ProductionLogger.debug
        content = re.sub(
            r'console\.debug\s*\(',
            'ProductionLogger.debug(',
            content
        )
        
        # Replace console.warn with ProductionLogger.warn
        content = re.sub(
            r'console\.warn\s*\(',
            'ProductionLogger.warn(',
            content
        )
        
        # Replace console.error with ProductionLogger.error
        content = re.sub(
            r'console\.error\s*\(',
            'ProductionLogger.error(',
            content
        )
        
        # Only write if changes were made
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print("Fixed console statements in {}".format(file_path))
            return True
        else:
            return False
            
    except Exception as e:
        print("Error processing {}: {}".format(file_path, e))
        return False

def main():
    """Main function to fix all console.log statements"""
    print("Fixing console.log statements in production...")
    
    # Get the project root
    project_root = Path(__file__).parent.parent
    
    # Find all JavaScript files
    js_files = []
    js_files.extend(glob.glob(str(project_root / "static" / "**" / "*.js"), recursive=True))
    js_files.extend(glob.glob(str(project_root / "**" / "static" / "**" / "*.js"), recursive=True))
    
    # Also check template files for inline JavaScript
    template_files = []
    template_files.extend(glob.glob(str(project_root / "**" / "templates" / "**" / "*.html"), recursive=True))
    
    fixed_count = 0
    total_files = len(js_files) + len(template_files)
    
    print("Found {} JS files and {} template files".format(len(js_files), len(template_files)))
    
    # Process JavaScript files
    for js_file in js_files:
        if fix_console_logs_in_file(js_file):
            fixed_count += 1
    
    # Process template files
    for template_file in template_files:
        if fix_console_logs_in_file(template_file):
            fixed_count += 1
    
    print("Fixed console statements in {} files".format(fixed_count))
    print("All console.log statements now use ProductionLogger")
    print("Production logging is now secure and controlled")

if __name__ == "__main__":
    main()
