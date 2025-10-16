#!/bin/bash

# Development script for LMS with Tailwind CSS
echo "Starting development mode for LMS..."

# Load NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Start Tailwind CSS in watch mode
echo "Starting Tailwind CSS in watch mode..."
echo "Press Ctrl+C to stop watching for changes"
npm run build-css
