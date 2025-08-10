# Photo Organizer

A safe, reliable tool to rename and organize photos based on metadata.

## Features

 **Safety First**: Never loses photos, never overwrites existing files
 **Idempotent**: Safe to run multiple times without creating duplicates
 **Python EXIF Reading**: No external dependencies like `exiftool`
 **Checksums**: Verifies file integrity during operations
 **Dry Run**: Preview changes before applying them
 **Comprehensive Tests**: 26 tests including critical safety tests

## Installation

### Method 1: Easy Installation (Recommended)

```bash
# Clone or copy this directory
cd photo-organizer

# Install globally (available system-wide)
./install.sh --global

# Or install for current user only
./install.sh --user
```

After installation, you can run `photo-organizer` from anywhere!

To uninstall later:
```bash
./uninstall.sh --user    # Remove user installation
./uninstall.sh --global  # Remove global installation
```

### Method 2: Development Installation

```bash
# Clone or copy this directory
cd photo-organizer

# Install with uv (recommended)
uv sync

# Or install with pip
pip install -e .
```

### Method 3: Direct pip install

```bash
# Install directly from source
pip install .

# Or for development
pip install -e .
```

## Usage

### Basic Usage
```bash
# Process current directory (dry run first!)
photo-organizer --dry-run

# Actually process files
photo-organizer

# Specify input and output directories
photo-organizer /path/to/photos -o /path/to/archive

# Just rename files in place without moving to folders
photo-organizer --rename-only /path/to/photos
```

### Options

- `--dry-run`: Show what would be done without actually doing it
- `-o, --output DIR`: Output directory (default: `archive`)
- `--copy`: Copy files instead of moving them (safer)
- `--rename-only`: Only rename files in place without moving to date folders
- `--extensions JPG PNG`: File extensions to process
- `-v, --verbose`: Enable verbose logging

### How It Works

1. **Scans** for supported image files (JPG, PNG, TIFF, RAW, etc.)
2. **Reads EXIF metadata** to extract creation date
3. **Renames** files to `YYYY-MM-DD_HH-MM-SS.ext` format
4. **Organizes** into `archive/YEAR/YEAR_MM/` folder structure
5. **Handles duplicates** safely with incremental naming (`photo_001.jpg`)
6. **Tracks processed files** to avoid reprocessing

## Safety Features

### Never Lose Photos
- Files are copied first, then original deleted (for moves)
- Checksums verify integrity before and after operations
- Corrupted operations are rolled back automatically

### Never Overwrite
- Existing files are never overwritten
- Duplicate content is detected and skipped
- Name conflicts get incremental suffixes (`_001`, `_002`, etc.)

### Idempotent Operations
- Safe to run multiple times
- Already processed files are skipped
- Files in archive structure are ignored
- Database tracks what's been processed

## Examples

### Standard Mode (organize into folders)
```bash
# Before
photos/
    IMG_1234.JPG    (taken 2023-12-25 14:30:45)
    DSC_5678.JPG    (taken 2023-12-26 10:15:30)
    photo.png       (taken 2024-01-01 00:00:00)

# After running photo-organizer
photos/
archive/
    2023/
        2023_12/
            2023-12-25_14-30-45.jpg
            2023-12-26_10-15-30.jpg
    2024/
        2024_01/
            2024-01-01_00-00-00.png
```

### Rename-Only Mode (rename in place)
```bash
# Before
photos/
    IMG_1234.JPG    (taken 2023-12-25 14:30:45)
    DSC_5678.JPG    (taken 2023-12-26 10:15:30)
    photo.png       (taken 2024-01-01 00:00:00)

# After running photo-organizer --rename-only
photos/
    2023-12-25_14-30-45.jpg
    2023-12-26_10-15-30.jpg
    2024-01-01_00-00-00.png
```

## Development

### Quick Commands (using Makefile)

```bash
make install-user    # Install to ~/.local/bin
make dev            # Setup development environment
make test           # Run tests
make format         # Format code
make lint           # Run linting
make clean          # Clean build artifacts
```

### Manual Commands

```bash
# Install development dependencies
uv sync --dev

# Run tests
uv run pytest -v

# Run with coverage
uv run pytest --cov

# Format code
uv run black .
uv run ruff check .
```

## License

MIT License - feel free to modify and share!