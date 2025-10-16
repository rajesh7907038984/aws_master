#!/bin/bash

# Build script for LMS with Tailwind CSS
echo "Building Tailwind CSS for LMS..."

# Load NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Build Tailwind CSS for production
echo "Building CSS for production..."
npm run build-css-prod

# Activate virtual environment and collect static files
echo "Collecting static files..."
source venv/bin/activate
python manage.py collectstatic --noinput

echo "Build completed successfully!"
