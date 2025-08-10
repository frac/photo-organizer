#!/usr/bin/env python3
"""
Main entry point for photo organizer
"""

import click
import logging
from pathlib import Path
from typing import List

from .organizer import PhotoOrganizer
from .config import Config
from .logger import setup_logger


@click.command()
@click.argument("input_dir", type=click.Path(exists=True, path_type=Path), default=".")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default="archive",
    help="Output directory (default: archive)",
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
def main(
    input_dir: Path,
    output: Path,
    verbose: bool,
    dry_run: bool,
    extensions: List[str],
    copy: bool,
    rename_only: bool,
):
    """Organize photos by renaming based on EXIF data and optionally moving to date-based folders.

    This tool safely processes photos by:
    - Reading EXIF creation date from photos
    - Renaming to YYYY-MM-DD_HH-MM-SS format
    - Either renaming in place (--rename-only) or moving to archive/YEAR/YEAR-MM/ folder structure
    - Never overwriting existing files
    - Supporting dry-run mode for preview
    """
    # Setup logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logger = setup_logger(level=log_level)

    # Create configuration
    config = Config(
        output_dir=output,
        extensions=(
            list(extensions)
            if extensions
            else ["JPG", "JPEG", "PNG","TIFF", "jpg", "jpeg", "png", "tiff"]
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
        mode = 'DRY RUN' if dry_run else 'RENAME ONLY' if rename_only else 'COPY' if copy else 'MOVE'
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
