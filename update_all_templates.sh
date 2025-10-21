#!/bin/bash

# Comprehensive script to update ALL templates to use local Tailwind CSS
echo "🔍 Scanning and updating ALL templates to use local Tailwind CSS..."

# Find all HTML files
echo "📁 Finding all HTML template files..."
find /home/ec2-user/lms -name "*.html" -type f | wc -l
echo " templates found"

echo ""
echo "🔄 Updating templates..."

# Update cdn.tailwindcss.com references
echo "  - Updating cdn.tailwindcss.com references..."
find /home/ec2-user/lms -name "*.html" -type f -exec sed -i 's|<script src="https://cdn.tailwindcss.com"></script>|<link href="{% static '\''css/tailwind.css'\'' %}" rel="stylesheet">|g' {} \;

# Update jsdelivr CDN references (v2 and v3)
echo "  - Updating jsdelivr CDN references..."
find /home/ec2-user/lms -name "*.html" -type f -exec sed -i 's|https://cdn.jsdelivr.net/npm/tailwindcss@[0-9.]*/dist/tailwind.min.css|{% static '\''css/tailwind.css'\'' %}|g' {} \;

# Update any remaining unpkg references
echo "  - Updating unpkg references..."
find /home/ec2-user/lms -name "*.html" -type f -exec sed -i 's|https://unpkg.com/tailwindcss@[0-9.]*/dist/tailwind.min.css|{% static '\''css/tailwind.css'\'' %}|g' {} \;

# Update any remaining CDN references
echo "  - Updating any remaining CDN references..."
find /home/ec2-user/lms -name "*.html" -type f -exec sed -i 's|https://cdn.jsdelivr.net/npm/tailwindcss@[0-9.]*/dist/tailwind.min.css|{% static '\''css/tailwind.css'\'' %}|g' {} \;

echo ""
echo "✅ Template updates completed!"

# Verify the changes
echo ""
echo "🔍 Verifying changes..."

# Count remaining CDN references
CDN_COUNT=$(find /home/ec2-user/lms -name "*.html" -type f -exec grep -l "cdn.tailwindcss.com\|cdn.jsdelivr.net.*tailwind\|unpkg.*tailwind" {} \; 2>/dev/null | wc -l)

# Count local Tailwind references
LOCAL_COUNT=$(find /home/ec2-user/lms -name "*.html" -type f -exec grep -l "static.*tailwind\.css" {} \; 2>/dev/null | wc -l)

echo "📊 Results:"
echo "  - Templates with CDN references: $CDN_COUNT"
echo "  - Templates with local Tailwind: $LOCAL_COUNT"

if [ $CDN_COUNT -eq 0 ]; then
    echo "🎉 All templates successfully updated to use local Tailwind CSS!"
else
    echo "⚠️  Some templates still have CDN references:"
    find /home/ec2-user/lms -name "*.html" -type f -exec grep -l "cdn.tailwindcss.com\|cdn.jsdelivr.net.*tailwind\|unpkg.*tailwind" {} \; 2>/dev/null
fi

echo ""
echo "🚀 Ready to deploy changes!"
