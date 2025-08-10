#!/bin/bash
# Proper uninstall script for photo-organizer
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

# Check if uv is installed
check_uv() {
    if ! command -v uv &> /dev/null; then
        print_error "uv is not installed. Cannot uninstall photo-organizer."
        exit 1
    fi
    print_success "uv is available"
}

# Check if photo-organizer is installed
check_installed() {
    if ! uv tool list | grep -q "photo-organizer"; then
        print_warning "photo-organizer is not installed via uv tool install"
        
        # Check for legacy installations
        if [[ -f "$HOME/.local/bin/photo-organizer" ]]; then
            print_info "Found legacy installation at ~/.local/bin/photo-organizer"
            print_info "Removing legacy installation..."
            rm -f "$HOME/.local/bin/photo-organizer"
            print_success "Removed legacy installation"
        fi
        
        if [[ -f "/usr/local/bin/photo-organizer" ]]; then
            print_info "Found legacy global installation at /usr/local/bin/photo-organizer"
            print_info "Removing legacy global installation (requires sudo)..."
            sudo rm -f "/usr/local/bin/photo-organizer" 2>/dev/null || print_warning "Could not remove global installation (permission denied)"
        fi
        
        print_info "No uv tool installation found to remove."
        return 1
    fi
    return 0
}

# Uninstall the package
uninstall_package() {
    print_info "Uninstalling photo-organizer..."
    
    if uv tool uninstall photo-organizer; then
        print_success "Successfully uninstalled photo-organizer"
    else
        print_error "Failed to uninstall photo-organizer"
        exit 1
    fi
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Properly uninstall photo-organizer

Options:
  --force         Also remove legacy installations (old wrapper scripts)
  --help          Show this help message

Examples:
  $0              # Uninstall photo-organizer
  $0 --force      # Uninstall and clean up legacy installations

This script:
- Uses 'uv tool uninstall photo-organizer' for proper removal
- Cleans up the complete uv tool environment
- Optionally removes legacy wrapper script installations
- Does not require specifying user/global (uv handles this automatically)
EOF
}

# Main uninstall function
main() {
    local remove_legacy=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --force)
                remove_legacy=true
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
    
    print_info "=== Photo Organizer Proper Uninstaller ==="
    print_info ""
    
    # Check prerequisites
    check_uv
    
    # Check if installed and uninstall
    if check_installed; then
        uninstall_package
    fi
    
    # Remove legacy installations if requested
    if [[ "$remove_legacy" == true ]]; then
        print_info ""
        print_info "Checking for legacy installations..."
        
        if [[ -f "$HOME/.local/bin/photo-organizer" ]]; then
            print_info "Removing legacy user installation..."
            rm -f "$HOME/.local/bin/photo-organizer"
            print_success "Removed ~/.local/bin/photo-organizer"
        fi
        
        if [[ -f "/usr/local/bin/photo-organizer" ]]; then
            print_info "Removing legacy global installation (requires sudo)..."
            sudo rm -f "/usr/local/bin/photo-organizer" 2>/dev/null && print_success "Removed /usr/local/bin/photo-organizer" || print_warning "Could not remove global installation"
        fi
    fi
    
    print_info ""
    print_success "Uninstallation complete!"
    print_info ""
    print_info "photo-organizer has been completely removed from your system."
    
    if [[ "$remove_legacy" == false ]] && ([[ -f "$HOME/.local/bin/photo-organizer" ]] || [[ -f "/usr/local/bin/photo-organizer" ]]); then
        print_warning "Legacy wrapper scripts may still exist."
        print_info "Run: $0 --force  to remove them as well."
    fi
}

# Run main function
main "$@"