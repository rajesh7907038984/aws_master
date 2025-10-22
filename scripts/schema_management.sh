#!/bin/bash
# Database Schema Management Script
# Provides convenient commands for schema management

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "Database Schema Management Script"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  dump-baseline     Create baseline schema"
    echo "  dump-current      Dump current schema"
    echo "  compare           Compare current schema with baseline"
    echo "  validate         Validate schema consistency"
    echo "  snapshot         Create schema snapshot"
    echo "  setup-git        Setup git hooks for schema management"
    echo "  help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 dump-baseline"
    echo "  $0 compare --strict"
    echo "  $0 validate"
}

# Function to create baseline schema
dump_baseline() {
    print_status "Creating baseline schema..."
    python manage.py dump_schema --baseline --output database_schema/baseline_schema.json
    print_success "Baseline schema created: database_schema/baseline_schema.json"
}

# Function to dump current schema
dump_current() {
    print_status "Dumping current schema..."
    timestamp=$(date +%Y%m%d_%H%M%S)
    python manage.py dump_schema --output database_schema/current_schema_${timestamp}.json
    print_success "Current schema dumped: database_schema/current_schema_${timestamp}.json"
}

# Function to compare schemas
compare_schemas() {
    print_status "Comparing schemas..."
    
    if [ ! -f "database_schema/baseline_schema.json" ]; then
        print_error "Baseline schema not found. Run 'dump-baseline' first."
        exit 1
    fi
    
    python manage.py compare_schema --baseline database_schema/baseline_schema.json "$@"
}

# Function to validate schema
validate_schema() {
    print_status "Validating schema consistency..."
    
    if [ ! -f "database_schema/baseline_schema.json" ]; then
        print_error "Baseline schema not found. Run 'dump-baseline' first."
        exit 1
    fi
    
    python manage.py compare_schema --baseline database_schema/baseline_schema.json --strict
    print_success "Schema validation passed"
}

# Function to create schema snapshot
create_snapshot() {
    print_status "Creating schema snapshot..."
    timestamp=$(date +%Y%m%d_%H%M%S)
    python manage.py dump_schema --output database_schema/schema_snapshot_${timestamp}.json
    print_success "Schema snapshot created: database_schema/schema_snapshot_${timestamp}.json"
}

# Function to setup git hooks
setup_git() {
    print_status "Setting up git hooks for schema management..."
    
    # Make pre-commit hook executable
    chmod +x .git/hooks/pre-commit
    
    # Create schema directory
    mkdir -p database_schema
    
    print_success "Git hooks configured"
    print_warning "Remember to create baseline schema: $0 dump-baseline"
}

# Function to check if we're in a Django project
check_django_project() {
    if [ ! -f "manage.py" ]; then
        print_error "Not in a Django project directory"
        exit 1
    fi
}

# Main script logic
main() {
    # Check if we're in a Django project
    check_django_project
    
    # Parse command
    case "${1:-help}" in
        "dump-baseline")
            dump_baseline
            ;;
        "dump-current")
            dump_current
            ;;
        "compare")
            shift
            compare_schemas "$@"
            ;;
        "validate")
            validate_schema
            ;;
        "snapshot")
            create_snapshot
            ;;
        "setup-git")
            setup_git
            ;;
        "help"|"-h"|"--help")
            show_usage
            ;;
        *)
            print_error "Unknown command: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
