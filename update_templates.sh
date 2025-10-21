#!/bin/bash

# Script to update all templates from CDN Tailwind to local Tailwind CSS

echo "Updating templates to use local Tailwind CSS..."

# Find and replace CDN links with local CSS (handle both v2 and v3)
find /home/ec2-user/lms -name "*.html" -type f -exec sed -i 's|https://cdn.jsdelivr.net/npm/tailwindcss@[0-9.]*/dist/tailwind.min.css|{% static '\''css/tailwind.css'\'' %}|g' {} \;

echo "Template updates completed!"
echo "Updated templates now use local Tailwind CSS instead of CDN."
