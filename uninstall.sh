#!/bin/bash
# Uninstall script for photo-organizer
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "$1"
}

# Default installation directories
USER_BIN="$HOME/.local/bin"
GLOBAL_BIN="/usr/local/bin"

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Uninstall photo-organizer

Options:
  --user          Remove from ~/.local/bin (default)
  --global        Remove from /usr/local/bin (requires sudo)
  --all           Remove from both locations
  --help          Show this help message

Examples:
  $0              # Remove from ~/.local/bin
  $0 --user       # Remove from ~/.local/bin
  $0 --global     # Remove from /usr/local/bin (requires sudo)
  $0 --all        # Remove from both locations
EOF
}

# Remove script from directory
remove_from_dir() {
    local dir=$1
    local script_path="$dir/photo-organizer"
    
    if [[ -f "$script_path" ]]; then
        if [[ "$dir" == "$GLOBAL_BIN" && ! -w "$dir" ]]; then
            print_info "Removing from $dir (requires sudo)"
            sudo rm -f "$script_path"
        else
            rm -f "$script_path"
        fi
        print_success "Removed $script_path"
    else
        print_warning "Not found: $script_path"
    fi
}

# Main uninstall function
main() {
    local remove_user=false
    local remove_global=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --user)
                remove_user=true
                shift
                ;;
            --global)
                remove_global=true
                shift
                ;;
            --all)
                remove_user=true
                remove_global=true
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Default to user if no options specified
    if [[ "$remove_user" == false && "$remove_global" == false ]]; then
        remove_user=true
    fi
    
    print_info "=== Photo Organizer Uninstaller ==="
    print_info ""
    
    # Remove from specified locations
    if [[ "$remove_user" == true ]]; then
        remove_from_dir "$USER_BIN"
    fi
    
    if [[ "$remove_global" == true ]]; then
        remove_from_dir "$GLOBAL_BIN"
    fi
    
    print_info ""
    print_success "Uninstallation complete!"
    print_info ""
    print_warning "Note: This doesn't remove PATH entries from shell rc files."
    print_info "You may want to manually remove them if no longer needed."
}

# Run main function
main "$@"