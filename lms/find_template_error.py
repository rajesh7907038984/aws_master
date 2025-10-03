#!/usr/bin/env python3
import os
import re

def find_problematic_templates():
    """Find templates with actual syntax errors that would cause Django errors"""
    
    template_files = []
    for root, dirs, files in os.walk('.'):
        if 'venv' in root or '.git' in root or '__pycache__' in root:
            continue
        for file in files:
            if file.endswith('.html'):
                template_files.append(os.path.join(root, file))
    
    print(f"Scanning {len(template_files)} templates for actual syntax errors...")
    
    for template_file in template_files:
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
        except:
            continue
            
        # Look for the specific error pattern: endwith where endfor is expected
        for i, line in enumerate(lines, 1):
            # Check for endwith
            if 'endwith' in line and '{%' in line and '%}' in line:
                # Look backwards to find the most recent unclosed tag
                context_lines = lines[max(0, i-20):i]
                
                # Count open/close tags in the context
                for_count = 0
                endfor_count = 0
                with_count = 0
                endwith_count = 0
                
                for ctx_line in context_lines:
                    for_count += ctx_line.count('{% for ')
                    endfor_count += ctx_line.count('{% endfor %}')
                    with_count += ctx_line.count('{% with ')
                    endwith_count += ctx_line.count('{% endwith %}')
                
                # If there are more for tags than endfor tags in context, this endwith might be wrong
                if for_count > endfor_count:
                    print(f"\n❌ POTENTIAL ERROR in {template_file}:")
                    print(f"   Line {i}: endwith found but unclosed for in context")
                    print(f"   Context: for={for_count}, endfor={endfor_count}, with={with_count}, endwith={endwith_count}")
                    print(f"   Line content: {line.strip()}")
                    
                    # Show context
                    start_line = max(1, i-5)
                    end_line = min(len(lines), i+5)
                    print(f"   Context (lines {start_line}-{end_line}):")
                    for j in range(start_line-1, end_line):
                        marker = " >>> " if j == i-1 else "     "
                        print(f"   {marker}{j+1:3d}: {lines[j].strip()}")

if __name__ == "__main__":
    find_problematic_templates()
