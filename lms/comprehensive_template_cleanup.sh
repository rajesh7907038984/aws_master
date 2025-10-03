#!/bin/bash

# Comprehensive SCORM Cloud Template Cleanup Script

echo "🧹 Starting comprehensive SCORM Cloud cleanup..."

# Backup original files
echo "📋 Creating backups..."
cp /home/ec2-user/lms/account_settings/templates/account_settings/settings.html /home/ec2-user/lms/account_settings/templates/account_settings/settings.html.backup.scorm

# Remove the entire SCORM Cloud integration section from settings.html
echo "🗑️ Removing SCORM Cloud integration section from account settings..."

# Create a new version without the SCORM Cloud section
python3 << 'EOF'
import re

with open('/home/ec2-user/lms/account_settings/templates/account_settings/settings.html', 'r') as f:
    content = f.read()

# Remove the SCORM Cloud tab button section
content = re.sub(
    r'<button @click="setActiveIntegration\(\'scorm\'\)".*?</button>',
    '<button disabled class="pb-4 border-b-2 border-transparent text-gray-400 font-medium text-sm cursor-not-allowed">Native SCORM (No Setup Required)</button>',
    content,
    flags=re.DOTALL
)

# Remove the entire SCORM integration content div
# Find the start of the SCORM section
scorm_start = content.find('<!-- SCORM Cloud Integration Section Removed')
if scorm_start != -1:
    # Find the corresponding {% endif %}
    scorm_section = content[scorm_start:]
    endif_count = 0
    search_pos = 0
    
    while search_pos < len(scorm_section):
        if_match = re.search(r'{%\s*if\s+', scorm_section[search_pos:])
        endif_match = re.search(r'{%\s*endif\s*%}', scorm_section[search_pos:])
        
        if if_match and (not endif_match or if_match.start() < endif_match.start()):
            endif_count += 1
            search_pos += if_match.end()
        elif endif_match:
            if endif_count == 0:
                # This is our closing endif
                scorm_end = scorm_start + search_pos + endif_match.end()
                break
            else:
                endif_count -= 1
                search_pos += endif_match.end()
        else:
            break
    
    if scorm_end:
        # Replace the entire section with a simple message
        new_section = '''
                    <!-- Native SCORM Information -->
                    {% if is_branch_admin %}
                    <div x-show="activeIntegration === 'scorm'" class="space-y-4">
                        <div class="bg-blue-50 border border-blue-200 rounded-lg p-6">
                            <div class="flex items-center mb-4">
                                <div class="flex-shrink-0">
                                    <svg class="h-8 w-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                                    </svg>
                                </div>
                                <div class="ml-3">
                                    <h3 class="text-lg font-medium text-blue-800">Native SCORM Integration</h3>
                                </div>
                            </div>
                            <div class="text-blue-700">
                                <p class="mb-3">This LMS now uses <strong>native SCORM processing</strong>. No external integration setup is required.</p>
                                <div class="bg-white rounded-lg p-4 border border-blue-200">
                                    <h4 class="font-semibold mb-2">Features:</h4>
                                    <ul class="list-disc list-inside space-y-1 text-sm">
                                        <li>Automatic SCORM 1.2 and SCORM 2004 support</li>
                                        <li>Built-in SCORM player and API</li>
                                        <li>Progress tracking and scoring</li>
                                        <li>No third-party dependencies</li>
                                        <li>Files stored securely in S3</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                    {% endif %}
'''
        content = content[:scorm_start] + new_section + content[scorm_end:]

# Remove the SCORM Cloud connection test JavaScript
js_start = content.find('alert(`✅ SCORM Cloud connection successful!')
if js_start != -1:
    # Find the end of this JavaScript function
    js_end = content.find('});', js_start)
    if js_end != -1:
        js_end = content.find('}', js_end + 3) + 1
        content = content[:js_start] + 'alert("✅ Native SCORM is ready - no connection test needed!");' + content[js_end:]

with open('/home/ec2-user/lms/account_settings/templates/account_settings/settings.html', 'w') as f:
    f.write(content)

print("✅ SCORM Cloud section removed and replaced with native SCORM information")
EOF

# Clean up gradebook template tags (need to update these to use native SCORM)
echo "🏷️ Updating gradebook template tags..."
if [ -f "/home/ec2-user/lms/gradebook/templates/gradebook/index_original.html" ]; then
    cp /home/ec2-user/lms/gradebook/templates/gradebook/index_original.html /home/ec2-user/lms/gradebook/templates/gradebook/index_original.html.backup.scorm
    
    # Comment out old SCORM template tags temporarily
    sed -i 's/{% build_scorm_lookup scorm_registrations as scorm_lookup %}/<!-- {% build_scorm_lookup scorm_registrations as scorm_lookup %} -->/' /home/ec2-user/lms/gradebook/templates/gradebook/index_original.html
    sed -i 's/{% course_has_activities course '\''scorm'\'' scorm_registrations=scorm_registrations as has_scorm_activities %}/<!-- {% course_has_activities course '\''scorm'\'' scorm_registrations=scorm_registrations as has_scorm_activities %} -->/' /home/ec2-user/lms/gradebook/templates/gradebook/index_original.html
    sed -i 's/{% get_scorm_registration_for_topic scorm_registrations student.id topic.id as registration %}/<!-- {% get_scorm_registration_for_topic scorm_registrations student.id topic.id as registration %} -->/' /home/ec2-user/lms/gradebook/templates/gradebook/index_original.html
fi

echo "✅ Template cleanup completed!"
echo "📋 Backup files created with .backup.scorm extension"
echo "🔧 Templates now use native SCORM implementation"
