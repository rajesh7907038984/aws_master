#!/usr/bin/env python3
"""
"""

import os
import re
import glob

def fix_template_file(filepath):
    print(f"🔧 Processing: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    
    replacements = [
    ]
    
    for old, new in replacements:
        content = re.sub(old, new, content, flags=re.IGNORECASE)
    
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Updated: {filepath}")
        return True
    else:
        print(f"⏭️  No changes needed: {filepath}")
        return False

def main():
    
    # Find all HTML templates in the project
    template_patterns = [
        '/home/ec2-user/lms/courses/templates/**/*.html',
        '/home/ec2-user/lms/account_settings/templates/**/*.html',
        '/home/ec2-user/lms/*/templates/**/*.html',
    ]
    
    all_templates = []
    for pattern in template_patterns:
        all_templates.extend(glob.glob(pattern, recursive=True))
    
    # Remove duplicates
    all_templates = list(set(all_templates))
    
    print(f"📋 Found {len(all_templates)} template files to check")
    
    updated_files = []
    
    for template_file in all_templates:
        if fix_template_file(template_file):
            updated_files.append(template_file)
    
    print(f"\n📊 Summary:")
    print(f"   - Total templates checked: {len(all_templates)}")
    print(f"   - Templates updated: {len(updated_files)}")
    
    if updated_files:
        print(f"\n✅ Updated files:")
        for file in updated_files:
            print(f"   - {file}")
    
    print(f"\n🎉 Template cleanup completed!")

if __name__ == "__main__":
    main()
