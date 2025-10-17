#!/usr/bin/env python3
"""Fix indentation issues in account_settings/views.py"""

def fix_indentation():
    print("🔧 Fixing indentation in account_settings/views.py...")
    
    with open('account_settings/views.py', 'r') as f:
        content = f.read()
    
    # Replace all tabs with 4 spaces
    content = content.replace('\t', '    ')
    
    # Write the fixed content back
    with open('account_settings/views.py', 'w') as f:
        f.write(content)
    
    print("✅ Indentation fixed!")
    
    # Test the file
    try:
        import ast
        with open('account_settings/views.py', 'r') as f:
            content = f.read()
        ast.parse(content)
        print("✅ File compiles successfully!")
        return True
    except SyntaxError as e:
        print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
        print(f"Text: {e.text}")
        return False

if __name__ == "__main__":
    fix_indentation()