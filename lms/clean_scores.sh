#!/bin/bash
#
# Clean Learner Scores - Helper Script
# 
# This script makes it easier to clean user learner score-related data from the database.
#
# Usage:
#   ./clean_scores.sh                                    # Show help
#   ./clean_scores.sh --dry-run                          # Preview what would be deleted
#   ./clean_scores.sh --dry-run --keep-enrollments       # Preview with enrollments preserved
#   ./clean_scores.sh --user john_doe --dry-run          # Preview for specific user
#   ./clean_scores.sh --course 5 --dry-run               # Preview for specific course
#   ./clean_scores.sh                                    # Actually clean all data (prompts for confirmation)
#

cd /home/ec2-user/lms

# Activate virtual environment
source venv/bin/activate

# Run the Django management command with all passed arguments
if [ $# -eq 0 ]; then
    echo "=========================================="
    echo "Clean Learner Scores Helper Script"
    echo "=========================================="
    echo ""
    echo "This script cleans user learner score-related data including:"
    echo "  - SCORM attempts and scores"
    echo "  - SCORM interactions, objectives, and comments"
    echo "  - Gradebook grades"
    echo "  - Topic progress records"
    echo "  - Course enrollment completion data"
    echo ""
    echo "Usage examples:"
    echo "  ./clean_scores.sh --dry-run                          # Preview what would be deleted"
    echo "  ./clean_scores.sh --dry-run --keep-enrollments       # Preview with enrollments preserved"
    echo "  ./clean_scores.sh --user john_doe --dry-run          # Preview for specific user"
    echo "  ./clean_scores.sh --course 5 --dry-run               # Preview for specific course"
    echo "  ./clean_scores.sh --help                             # Show detailed help"
    echo ""
    echo "To actually clean data (will prompt for confirmation):"
    echo "  ./clean_scores.sh                                    # Clean all data"
    echo "  ./clean_scores.sh --keep-enrollments                 # Clean but keep enrollments"
    echo "  ./clean_scores.sh --user john_doe                    # Clean specific user data"
    echo ""
    python manage.py clean_learner_scores --help
else
    python manage.py clean_learner_scores "$@"
fi

