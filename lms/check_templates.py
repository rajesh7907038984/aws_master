#!/usr/bin/env python3
import os
import re
import sys

def check_template_syntax(file_path):
    """Check a single template file for syntax issues"""
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
    except Exception as e:
        return [f"ERROR: Could not read file: {e}"]
    
    # Find all template tags
    for_tags = re.findall(r'{\s*%\s*for\s+.*?%\s*}', content)
    endfor_tags = re.findall(r'{\s*%\s*endfor\s*%\s*}', content)
    
    with_tags = re.findall(r'{\s*%\s*with\s+.*?%\s*}', content)
    endwith_tags = re.findall(r'{\s*%\s*endwith\s*%\s*}', content)
    
    if_tags = re.findall(r'{\s*%\s*if\s+.*?%\s*}', content)
    elif_tags = re.findall(r'{\s*%\s*elif\s+.*?%\s*}', content)
    else_tags = re.findall(r'{\s*%\s*else\s*%\s*}', content)
    endif_tags = re.findall(r'{\s*%\s*endif\s*%\s*}', content)
    
    block_tags = re.findall(r'{\s*%\s*block\s+.*?%\s*}', content)
    endblock_tags = re.findall(r'{\s*%\s*endblock\s*.*?%\s*}', content)
    
    # Check for mismatches
    if len(for_tags) != len(endfor_tags):
        issues.append(f"MISMATCH: {len(for_tags)} 'for' tags vs {len(endfor_tags)} 'endfor' tags")
    
    if len(with_tags) != len(endwith_tags):
        issues.append(f"MISMATCH: {len(with_tags)} 'with' tags vs {len(endwith_tags)} 'endwith' tags")
    
    # For if/endif, count total if+elif vs endif
    total_if_tags = len(if_tags) + len(elif_tags)
    if len(if_tags) != len(endif_tags):
        issues.append(f"MISMATCH: {len(if_tags)} 'if' tags vs {len(endif_tags)} 'endif' tags")
    
    if len(block_tags) != len(endblock_tags):
        issues.append(f"MISMATCH: {len(block_tags)} 'block' tags vs {len(endblock_tags)} 'endblock' tags")
    
    # Check for orphaned tags (common after SCORM removal)
    orphaned_patterns = [
        r'{\s*%\s*endif\s*%\s*}(?!\s*{\s*%\s*(?:else|elif))',  # endif without matching if
        r'{\s*%\s*endfor\s*%\s*}(?!\s*{\s*%\s*empty)',        # endfor without matching for
        r'{\s*%\s*endwith\s*%\s*}',                           # endwith without matching with
        r'{\s*%\s*endblock\s*%\s*}'                           # endblock without matching block
    ]
    
    # Look for specific problematic patterns
    for i, line in enumerate(lines, 1):
        # Check for common syntax errors
        if re.search(r'{\s*%\s*endwith\s*%\s*}.*{\s*%\s*endfor\s*%\s*}', line):
            issues.append(f"Line {i}: Potential endwith/endfor confusion")
        
        if re.search(r'{\s*%\s*endif\s*%\s*}.*{\s*%\s*endfor\s*%\s*}', line):
            issues.append(f"Line {i}: Potential endif/endfor confusion")
    
    return issues

def main():
    """Check all templates in the project"""
    template_files = []
    
    # Find all HTML templates
    for root, dirs, files in os.walk('.'):
        # Skip venv and other non-template directories
        if 'venv' in root or '.git' in root or '__pycache__' in root:
            continue
            
        for file in files:
            if file.endswith('.html'):
                template_files.append(os.path.join(root, file))
    
    print(f"Checking {len(template_files)} template files...")
    print("=" * 50)
    
    total_issues = 0
    problematic_files = []
    
    for template_file in sorted(template_files):
        issues = check_template_syntax(template_file)
        if issues:
            total_issues += len(issues)
            problematic_files.append(template_file)
            print(f"\n❌ {template_file}:")
            for issue in issues:
                print(f"   - {issue}")
    
    print(f"\n" + "=" * 50)
    print(f"SUMMARY:")
    print(f"Total templates checked: {len(template_files)}")
    print(f"Templates with issues: {len(problematic_files)}")
    print(f"Total issues found: {total_issues}")
    
    if problematic_files:
        print(f"\n🔧 FILES NEEDING ATTENTION:")
        for file in problematic_files:
            print(f"   - {file}")
        return 1
    else:
        print(f"\n✅ All templates appear to have correct syntax!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
