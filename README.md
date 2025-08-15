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
# Process photos in a directory (dry run first!)
photo-organizer /path/to/photos --dry-run

# Actually process files
photo-organizer /path/to/photos

# Specify input and output directories
photo-organizer /path/to/photos -o /path/to/archive

# Just rename files in place without moving to folders
photo-organizer --rename-only /path/to/photos

# Use archive alias instead of output (more intuitive for sync operations)
photo-organizer /path/to/photos --archive /path/to/archive
```

**Note:** Input directory is only required for photo organization operations. For drive management operations (`--compare-drives`, `--sync-drives`, `--backup-to-drives`), no input directory is needed.

### Drive Management
```bash
# Compare two backup drives to see differences
photo-organizer --compare-drives /media/drive1 /mnt/drive2

# Automatically synchronize two backup drives
photo-organizer --sync-drives /media/drive1 /mnt/drive2

# Force rescan of drives (ignore existing scan data)
photo-organizer --sync-drives /media/drive1 /mnt/drive2 --rescan

# Preview sync operations without actually copying files
photo-organizer --sync-drives /media/drive1 /mnt/drive2 --dry-run

# Backup local archive to one or more backup drives
photo-organizer --archive /path/to/archive --backup-to-drives /media/drive1

# Backup to multiple drives
photo-organizer --archive /path/to/archive --backup-to-drives /media/drive1 --backup-to-drives /mnt/backup2

# Preview backup operations without actually copying files
photo-organizer --archive /path/to/archive --backup-to-drives /media/drive1 --dry-run
```

### Options

- `--dry-run`: Show what would be done without actually doing it
- `-o, -a, --output, --archive DIR`: Output/archive directory (default: `archive`)
- `--copy`: Copy files instead of moving them (safer)
- `--rename-only`: Only rename files in place without moving to date folders
- `--extensions JPG PNG`: File extensions to process
- `--compare-drives DRIVE1 DRIVE2`: Compare files between two backup drives
- `--sync-drives DRIVE1 DRIVE2`: Compare and automatically synchronize two backup drives
- `--backup-to-drives DRIVE_PATH`: Backup local archive to one or more backup drives. Specify drive root paths (e.g., /media/drive1, /mnt/backup), not subdirectories. Can be specified multiple times.
- `--rescan`: Force rescan of drives (ignore existing scan data)
- `-v, --verbose`: Enable verbose logging

### How It Works

1. **Scans** for supported image files (JPG, PNG, TIFF, RAW, etc.)
2. **Reads EXIF metadata** to extract creation date
3. **Renames** files to `YYYY-MM-DD_HH-MM-SS.ext` format
4. **Organizes** into `archive/YEAR/YEAR_MM/` folder structure
5. **Handles duplicates** safely with incremental naming (`photo_001.jpg`)
6. **Tracks processed files** to avoid reprocessing

### Drive Synchronization

The drive synchronization system ensures your backup drives have identical content:

1. **Drive Scanning**: Creates SQLite databases on each drive containing file metadata (path, size, checksum)
2. **Comparison**: Identifies files missing from each drive and files with different content
3. **Synchronization**: Automatically copies missing files between drives with verification
4. **Safety**: Never overwrites existing files, verifies copies with checksums

**What Gets Synced:**
- Files missing from either drive
- Files with different content are skipped (manual intervention required)

**Safety Features:**
- Checksum verification after each copy
- Space verification before starting sync
- Dry-run mode to preview operations
- Graceful cancellation with Ctrl+C

**Example Output:**
```bash
$ photo-organizer --sync-drives /media/backup1 /mnt/backup2

=== Files Missing from Drive 2 (15 files) ===
  photos/2024/IMG_001.jpg (2,048,000 bytes)
  photos/2024/IMG_002.jpg (1,024,000 bytes)
  ... and 13 more files

=== Files Missing from Drive 1 (8 files) ===
  photos/2024/IMG_015.jpg (3,072,000 bytes)
  ... and 7 more files

=== Files with Different Content (2 files) ===
  photos/2024/common.jpg - Different content, skipping

Starting automatic synchronization...
=== Copying 8 files to Drive 1 ===
[1/8] Copying to Drive 1: photos/2024/IMG_015.jpg
[2/8] Copying to Drive 1: photos/2024/IMG_016.jpg
...

=== Synchronization Complete ===
Files copied to Drive 1: 8
Files copied to Drive 2: 15
Files skipped: 2
Errors: 0
Total bytes copied: 45,056,000
✅ Synchronization completed successfully!
```

### Archive Backup to Drives

The backup system allows you to backup your local photo archive to one or more external backup drives:

**Important**: Specify drive root paths (e.g., `/media/drive1`, `/mnt/backup`, `/Volumes/Backup`), not subdirectories. The tool will create the organized folder structure automatically.

1. **Archive Scanning**: Recursively scans your local archive directory for all photos
2. **Drive Comparison**: Compares archive contents with each target drive's database
3. **Smart Copying**: Only copies files that are missing or have different content
4. **Database Updates**: Updates each drive's scan database after successful copies

**What Gets Backed Up:**
- Files missing from target drives
- Files with different content (overwrites with archive version)
- Maintains the organized folder structure from your archive

**Safety Features:**
- Checksum verification after each copy
- Space verification before starting backup
- Dry-run mode to preview operations
- Graceful cancellation with Ctrl+C
- Never overwrites files without verification

**Example Output:**
```bash
$ photo-organizer --archive /home/user/photo_archive --backup-to-drives /media/backup1 /mnt/backup2

=== Backup Archive to Drives ===
Archive path: /home/user/photo_archive
Target drives: ['/media/backup1', '/media/backup2']

--- Scanning Drive: /media/backup1 ---
Scanning drive: /media/backup1
Found 1,250 files to scan
Skipping 1,200 unchanged files, scanning 50 files

--- Scanning Local Archive: /home/user/photo_archive ---
Found 1,300 files in local archive

--- Backing up to Drive: /media/backup1 ---
Need to copy 50 files (125,000,000 bytes)
[1/50] Copying: photos/2025/IMG_001.jpg
[2/50] Copying: photos/2025/IMG_002.jpg
...

--- Backing up to Drive: /media/backup2 ---
Need to copy 100 files (250,000,000 bytes)
[1/100] Copying: photos/2025/IMG_001.jpg
...

=== Backup Summary ===
Total files copied: 150
Total bytes copied: 375,000,000
✅ Backup completed successfully!
```

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