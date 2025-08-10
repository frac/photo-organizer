# TODO

[x] add option to just rename files

## Configuration System
[ ] **Per-Directory Configuration Storage**
    - Store config per source directory (e.g., `~/Dropbox/Camera_Downloads`, `~/Pictures/Son_camera`)
    - JSON/YAML config files in `~/.config/photo-organizer/`
    - Each directory can have different:
      - Google Photos settings (account, album naming)
      - Backup drive targets (multiple HDDs with different paths)
      - Processing preferences (rename patterns, folder organization)

[ ] **Configuration Interface Options**
    - CLI commands: `photo-organizer config set/show/list/remove`
    - Web UI: Simple browser-based config editor (Flask/FastAPI)
    - Config file wizard: Interactive setup for new directories
    - Import/export configs for backup/sharing

## Google Photos Integration  
[ ] **Album Management**
    - Create albums automatically based on date/pattern
    - Examples: `Phone_2025_08`, `Son_2025_08`
    - Handle existing albums (append vs new)
    - Album descriptions with metadata

[ ] **Upload System**
    - OAuth2 authentication per Google account
    - Batch upload with progress tracking
    - Retry failed uploads
    - Track uploaded files to avoid duplicates
    - Quality options (original vs compressed)

## Backup Drive Management
[ ] **Drive Detection & Verification**
    - Detect connected drives by UUID/label
    - Verify drive is correct target (avoid wrong drive mistakes)
    - Check available space before operations
    - Handle drive connection/disconnection gracefully

[ ] **Multi-Drive Sync**
    - Copy files to multiple backup drives
    - Different target paths per drive: `/Pictures/archive` vs `/Pictures/Son/archive`
    - Verify all drives have same content
    - Report missing files per drive
    - Resume interrupted sync operations

[ ] **Drive Initialization**
    - Set up directory structure on new drives
    - Create drive identification files
    - Copy existing archive to new drive
    - Verification after initial sync

## Enhanced Features
[ ] **Progress & Status**
    - Progress bars for long operations
    - Status dashboard showing:
      - Last sync times per drive
      - Upload status to Google Photos
      - Missing files summary
      - Drive health/availability

[ ] **Automation & Monitoring**
    - Watch folders for new files
    - Automatic processing on file arrival
    - Email/notification on errors
    - Scheduled sync operations

[ ] **Safety & Recovery**
    - Backup configs before changes
    - Rollback mechanisms for failed operations  
    - Integrity verification across all targets
    - Recovery from partial failures

## Interface Design Considerations

**CLI**: Good for automation, scripts, power users
**Web UI**: Better for:
- Visual config management
- Progress monitoring
- Drive status dashboard
- Bulk operations with previews

**Hybrid Approach**: CLI for operations, Web UI for configuration and monitoring?
