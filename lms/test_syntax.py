#!/usr/bin/env python3
"""Test syntax of fixed files"""

import ast
import sys

def test_file_syntax(file_path):
    """Test if a Python file has valid syntax"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        ast.parse(content)
        print("OK: {}".format(file_path))
        return True
    except SyntaxError as e:
        print("ERROR: {} - Line {}: {}".format(file_path, e.lineno, e.msg))
        return False
    except Exception as e:
        print("ERROR: {} - {}".format(file_path, str(e)))
        return False

def main():
    """Test all fixed files"""
    files_to_test = [
        'account_settings/views.py',
        'courses/views.py', 
        'users/views.py'
    ]
    
    print("Testing syntax of fixed files...")
    all_ok = True
    
    for file_path in files_to_test:
        if not test_file_syntax(file_path):
            all_ok = False
    
    if all_ok:
        print("\nAll files have valid syntax!")
    else:
        print("\nSome files have syntax errors!")
        sys.exit(1)

if __name__ == "__main__":
    main()

