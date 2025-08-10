#!/bin/bash
# Proper installation script for photo-organizer
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
        print_error "uv is not installed. Please install it first:"
        print_info "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    print_success "uv is installed"
}

# Build the package
build_package() {
    print_info "Building package..."
    uv build
    print_success "Package built successfully"
}

# Install the package
install_package() {
    local install_type=$1
    
    if [[ "$install_type" == "global" ]]; then
        print_info "Installing globally (requires sudo)..."
        # Install system-wide using pipx or uv tool install
        if command -v pipx &> /dev/null; then
            sudo pipx install --force ./dist/*.whl
        else
            # Use uv tool install for global installation
            uv tool install --force ./dist/*.whl
        fi
        print_success "Installed globally"
    else
        print_info "Installing for current user..."
        # Install for user using uv tool install
        uv tool install --force ./dist/*.whl
        print_success "Installed for current user"
        
        # Check if ~/.local/bin is in PATH
        if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
            print_warning "~/.local/bin is not in your PATH"
            print_info "Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
            print_info "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        fi
    fi
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Properly install photo-organizer as a standalone package

Options:
  --user          Install for current user only (default)
  --global        Install system-wide (requires sudo/admin rights)
  --help          Show this help message

Examples:
  $0              # Install for current user
  $0 --user       # Install for current user  
  $0 --global     # Install system-wide

This creates a proper installation that:
- Packages the code into a wheel
- Installs it properly using uv tool install
- Creates a standalone executable
- Can be uninstalled cleanly with: uv tool uninstall photo-organizer
EOF
}

# Main installation function
main() {
    local install_type="user"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --user)
                install_type="user"
                shift
                ;;
            --global)
                install_type="global"
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
    
    print_info "=== Photo Organizer Proper Installer ==="
    print_info ""
    
    # Check prerequisites
    check_uv
    
    # Build the package
    build_package
    
    # Install the package
    install_package "$install_type"
    
    print_info ""
    print_success "Installation complete!"
    print_info ""
    print_info "The photo-organizer command is now available:"
    print_info "  photo-organizer --help"
    print_info "  photo-organizer /path/to/photos --dry-run"
    print_info ""
    print_info "To uninstall: uv tool uninstall photo-organizer"
}

# Run main function
main "$@"