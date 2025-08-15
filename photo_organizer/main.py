#!/usr/bin/env python3
"""
Main entry point for photo organizer
"""

import click
import logging
import json
from pathlib import Path
from typing import List

from .organizer import PhotoOrganizer
from .config import Config
from .logger import setup_logger
from .directory_config import (
    DirectoryConfigManager,
    DirectoryConfig,
    BackupDriveConfig,
    GooglePhotosConfig,
)


@click.command()
@click.argument(
    "input_dir",
    type=click.Path(exists=True, path_type=Path),
    required=False,
)
@click.option(
    "-o",
    "--output",
    "--archive",
    "-a",
    type=click.Path(path_type=Path),
    default="archive",
    help="Output/archive directory or path to local archive for backup (default: archive). For backup operations, can be relative (e.g., '.' from ~/pics will use ~/pics/archive)",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without actually doing it"
)
@click.option(
    "-e",
    "--extensions",
    multiple=True,
    default=["JPG", "JPEG", "PNG", "TIFF", "jpg", "jpeg", "png", "tiff"],
    help="File extensions to process (can be specified multiple times)",
)
@click.option(
    "--copy",
    is_flag=True,
    default=False,
    help="Copy files instead of moving them (safer)",
)
@click.option(
    "--rename-only",
    is_flag=True,
    default=False,
    help="Only rename files in place without moving to date folders",
)
@click.option(
    "--compare-drives",
    nargs=2,
    metavar="DRIVE1 DRIVE2",
    help="Compare files between two backup drives",
)
@click.option(
    "--sync-drives",
    nargs=2,
    metavar="DRIVE1 DRIVE2",
    help="Compare and automatically synchronize two backup drives",
)
@click.option(
    "--rescan",
    is_flag=True,
    default=False,
    help="Force rescan of drives (ignore existing scan data)",
)
@click.option(
    "--backup-to-drives",
    multiple=True,
    metavar="DRIVE_PATH",
    help="Backup local archive to one or more backup drives. Specify drive root paths (e.g., /media/drive1, /mnt/backup), not subdirectories. The tool will automatically detect existing archive directories or create them. Can be specified multiple times.",
)
def main(
    input_dir: Path,
    output: Path,
    verbose: bool,
    dry_run: bool,
    extensions: List[str],
    copy: bool,
    rename_only: bool,
    compare_drives: tuple,
    sync_drives: tuple,
    rescan: bool,
    backup_to_drives: List[str],
):
    """Organize photos by renaming based on EXIF data and optionally moving to date-based folders.

    This tool safely processes photos by:
    - Reading EXIF creation date from photos
    - Renaming to YYYY-MM-DD_HH-MM-SS format
    - Either renaming in place (--rename-only) or moving to archive/YEAR/YEAR-MM/ folder structure
    - Never overwriting existing files
    - Supporting dry-run mode for preview

    Drive Management:
    - Use --compare-drives to analyze differences between backup drives
    - Use --sync-drives to automatically copy missing files between drives
    - Use --backup-to-drives to backup local archive to one or more backup drives
    - Use --rescan to force fresh scanning of drives

    Use 'photo-organizer config --help' to manage per-directory configurations.
    """
    # Setup logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logger = setup_logger(level=log_level)

    # Handle drive comparison
    if compare_drives:
        from .drive_comparison import compare_backup_drives

        drive1, drive2 = compare_drives
        compare_backup_drives(Path(drive1), Path(drive2), logger, force_rescan=rescan)
        return 0

    # Handle drive synchronization
    if sync_drives:
        from .drive_comparison import sync_backup_drives

        drive1, drive2 = sync_drives
        success = sync_backup_drives(
            Path(drive1), Path(drive2), logger, force_rescan=rescan, dry_run=dry_run
        )
        return 0 if success else 1

    # Handle backup to drives
    if backup_to_drives:
        from .drive_comparison import backup_archive_to_drives

        drive_paths = [Path(drive) for drive in backup_to_drives]
        success = backup_archive_to_drives(
            archive_path=output,
            drive_paths=drive_paths,
            logger=logger,
            dry_run=dry_run,
            rescan=rescan,
        )
        return 0 if success else 1

    # Check if input directory is required for photo organization
    if input_dir is None:
        logger.error("Input directory is required for photo organization operations.")
        logger.error(
            "Use --compare-drives, --sync-drives, or --backup-to-drives for drive management operations."
        )
        return 1

    # Create configuration
    config = Config(
        output_dir=output,
        extensions=(
            list(extensions)
            if extensions
            else ["JPG", "JPEG", "PNG", "TIFF", "jpg", "jpeg", "png", "tiff"]
        ),
        dry_run=dry_run,
        copy_mode=copy,
        rename_only=rename_only,
    )

    # Initialize organizer
    organizer = PhotoOrganizer(config, logger)

    try:
        # Process photos
        logger.info(f"Processing photos in: {input_dir}")
        logger.info(f"Output directory: {output}")
        mode = (
            "DRY RUN"
            if dry_run
            else "RENAME ONLY" if rename_only else "COPY" if copy else "MOVE"
        )
        logger.info(f"Mode: {mode}")

        result = organizer.process_directory(input_dir)

        logger.info("=== Processing Complete ===")
        logger.info(f"Files processed: {result['processed']}")
        logger.info(f"Files skipped: {result['skipped']}")
        logger.info(f"Duplicates handled: {result['duplicates']}")
        logger.info(f"Errors: {result['errors']}")

        if result["errors"] > 0:
            logger.warning("Some files had errors. Check the log above for details.")
            return 1

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if verbose:
            import traceback

            logger.error(traceback.format_exc())
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
