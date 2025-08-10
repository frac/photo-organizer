#!/bin/bash
# Installation script for photo-organizer
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default installation directories
USER_BIN="$HOME/.local/bin"
GLOBAL_BIN="/usr/local/bin"

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

# Install dependencies
install_deps() {
    print_info "Installing dependencies..."
    uv sync
    print_success "Dependencies installed"
}

# Create wrapper script
create_wrapper() {
    local install_dir=$1
    local script_path="$install_dir/photo-organizer"
    local project_path="$(pwd)"
    
    # Create directory if it doesn't exist
    mkdir -p "$install_dir"
    
    # Create wrapper script
    cat > "$script_path" << EOF
#!/bin/bash
# Photo Organizer wrapper script
# Save current working directory
ORIGINAL_PWD="\$PWD"

# Change to project directory to run uv
cd "$project_path"

# Convert relative paths to absolute paths
args=()
next_is_output=false

for arg in "\$@"; do
    if [[ "\$next_is_output" == true ]]; then
        # This is an output path after -o or --output
        if [[ "\$arg" != /* ]]; then
            # Relative path, make absolute
            args+=("\$ORIGINAL_PWD/\$arg")
        else
            args+=("\$arg")
        fi
        next_is_output=false
    elif [[ "\$arg" == "-o" || "\$arg" == "--output" ]]; then
        # Next argument will be output path
        args+=("\$arg")
        next_is_output=true
    elif [[ "\$arg" == --output=* ]]; then
        # Handle --output=path format
        path_part="\${arg#--output=}"
        if [[ "\$path_part" != /* ]]; then
            args+=("--output=\$ORIGINAL_PWD/\$path_part")
        else
            args+=("\$arg")
        fi
    elif [[ "\$arg" != -* ]]; then
        # This is a positional argument (input directory)
        if [[ "\$arg" != /* ]]; then
            # Relative path, make absolute
            args+=("\$ORIGINAL_PWD/\$arg")
        else
            args+=("\$arg")
        fi
    else
        # Flag argument, pass through
        args+=("\$arg")
    fi
done

# If no arguments provided, use current directory
if [[ \$# -eq 0 ]]; then
    args+=("\$ORIGINAL_PWD")
fi

# Run with converted arguments
exec uv run photo-organizer "\${args[@]}"
EOF
    
    # Make executable
    chmod +x "$script_path"
    print_success "Created executable at $script_path"
}

# Add to PATH if needed
add_to_path() {
    local bin_dir=$1
    
    # Check if directory is in PATH
    if [[ ":$PATH:" != *":$bin_dir:"* ]]; then
        print_warning "$bin_dir is not in your PATH"
        
        # Try to add to shell rc files
        local shell_rc=""
        if [[ -n "$BASH_VERSION" ]]; then
            shell_rc="$HOME/.bashrc"
        elif [[ -n "$ZSH_VERSION" ]]; then
            shell_rc="$HOME/.zshrc"
        else
            shell_rc="$HOME/.profile"
        fi
        
        if [[ -f "$shell_rc" ]]; then
            echo "" >> "$shell_rc"
            echo "# Added by photo-organizer installer" >> "$shell_rc"
            echo "export PATH=\"$bin_dir:\$PATH\"" >> "$shell_rc"
            print_success "Added $bin_dir to PATH in $shell_rc"
            print_warning "Please restart your shell or run: source $shell_rc"
        else
            print_warning "Please add $bin_dir to your PATH manually"
        fi
    else
        print_success "$bin_dir is already in PATH"
    fi
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Install photo-organizer globally or locally

Options:
  --user          Install to ~/.local/bin (default)
  --global        Install to /usr/local/bin (requires sudo)
  --help          Show this help message

Examples:
  $0              # Install to ~/.local/bin
  $0 --user       # Install to ~/.local/bin
  $0 --global     # Install to /usr/local/bin (requires sudo)
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
    
    print_info "=== Photo Organizer Installer ==="
    print_info ""
    
    # Check prerequisites
    check_uv
    
    # Install dependencies
    install_deps
    
    # Determine installation directory
    local install_dir
    if [[ "$install_type" == "global" ]]; then
        install_dir="$GLOBAL_BIN"
        print_info "Installing globally to $install_dir (requires sudo)"
        
        # Check if we need sudo
        if [[ ! -w "$install_dir" ]]; then
            print_warning "This requires sudo access"
            sudo mkdir -p "$install_dir"
            create_wrapper "$install_dir"
            sudo chown root:root "$install_dir/photo-organizer"
        else
            create_wrapper "$install_dir"
        fi
    else
        install_dir="$USER_BIN"
        print_info "Installing locally to $install_dir"
        create_wrapper "$install_dir"
    fi
    
    # Add to PATH if needed (only for user installs)
    if [[ "$install_type" == "user" ]]; then
        add_to_path "$install_dir"
    fi
    
    print_info ""
    print_success "Installation complete!"
    print_info ""
    print_info "You can now run: photo-organizer --help"
    print_info "Example: photo-organizer /path/to/photos --dry-run"
}

# Run main function
main "$@"