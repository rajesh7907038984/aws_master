#!/bin/bash

echo "================================================"
echo "        SCORM Score Diagnostic Tool"
echo "================================================"
echo ""

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --diagnose      Run diagnosis only (default)"
    echo "  --fix           Run diagnosis and fix issues"
    echo "  --package ID    Check specific SCORM package ID"
    echo "  --user ID       Check specific user ID"
    echo "  --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                     # Run diagnosis for all SCORM data"
    echo "  $0 --fix               # Fix all found issues"
    echo "  $0 --package 64        # Check only package ID 64"
    echo "  $0 --fix --user 123    # Fix issues for user ID 123"
}

# Parse command line arguments
FIX_MODE=""
PACKAGE_ID=""
USER_ID=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX_MODE="--fix"
            shift
            ;;
        --package)
            PACKAGE_ID="--package-id $2"
            shift 2
            ;;
        --user)
            USER_ID="--user-id $2"
            shift 2
            ;;
        --help)
            show_usage
            exit 0
            ;;
        --diagnose)
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Build the command
CMD="python manage.py fix_scorm_scores_comprehensive $FIX_MODE $PACKAGE_ID $USER_ID"
CMD=$(echo $CMD | xargs)  # Clean up extra spaces

# Show what we're doing
if [ -n "$FIX_MODE" ]; then
    echo "🔧 Running in FIX mode - issues will be automatically corrected"
else
    echo "🔍 Running in DIAGNOSE mode - issues will be reported only"
fi

if [ -n "$PACKAGE_ID" ]; then
    echo "📦 Checking specific package: $PACKAGE_ID"
fi

if [ -n "$USER_ID" ]; then
    echo "👤 Checking specific user: $USER_ID"
fi

echo ""
echo "Running: $CMD"
echo "================================================"
echo ""

# Run the command
$CMD

echo ""
echo "================================================"
echo "Diagnostic complete!"
echo ""
echo "Additional tools available:"
echo "  - python manage.py sync_scorm_scores      # Sync all SCORM scores"
echo "  - python manage.py debug_scorm_scores     # Debug specific issues"
echo "  - python manage.py auto_fix_scorm_scores  # Auto-fix score sync issues"
echo ""
