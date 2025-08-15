"""Core photo organizer with safety-first approach"""

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple, Any, List
import logging

from .config import Config
from .metadata import MetadataExtractor
from .file_utils import FileOperations


class PhotoOrganizer:
    """Main photo organizer class with safety features"""

    def __init__(self, config: Config, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.metadata_extractor = MetadataExtractor()
        self.file_ops = FileOperations(config, logger)

        # Track processed files to avoid reprocessing
        self.processed_files_db = self._init_processed_db()

    def _init_processed_db(self) -> Path:
        """Initialize SQLite database to track processed files"""
        db_path = self.config.output_dir / ".photo_organizer_db.sqlite"

        # Create output directory if it doesn't exist
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_files (
                original_path TEXT PRIMARY KEY,
                original_checksum TEXT,
                new_path TEXT,
                processed_at TIMESTAMP,
                file_size INTEGER
            )
        """)
        conn.commit()
        conn.close()

        return db_path

    def _get_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _is_already_processed(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """Check if file was already processed by comparing checksum"""
        if not file_path.exists():
            return False, None

        current_checksum = self._get_file_checksum(file_path)

        conn = sqlite3.connect(self.processed_files_db)
        cursor = conn.execute(
            "SELECT new_path, original_checksum FROM processed_files WHERE original_path = ?",
            (str(file_path),)
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            stored_new_path, stored_checksum = result
            if stored_checksum == current_checksum:
                self.logger.debug(f"File already processed: {file_path} -> {stored_new_path}")
                return True, stored_new_path
            else:
                self.logger.info(f"File content changed since last processing: {file_path}")

        return False, None

    def _mark_as_processed(self, original_path: Path, checksum: str, new_path: Path, file_size: int):
        """Mark file as processed in database"""
        conn = sqlite3.connect(self.processed_files_db)
        conn.execute("""
            INSERT OR REPLACE INTO processed_files
            (original_path, original_checksum, new_path, processed_at, file_size)
            VALUES (?, ?, ?, ?, ?)
        """, (
            str(original_path),
            checksum,
            str(new_path),
            datetime.now().isoformat(),
            file_size
        ))
        conn.commit()
        conn.close()

    def _generate_target_path(self, original_path: Path, creation_date: datetime) -> Path:
        """Generate target path based on creation date"""
        # Create filename: YYYY-MM-DD_HH-MM-SS.ext
        filename = creation_date.strftime("%Y-%m-%d_%H-%M-%S") + original_path.suffix.lower()

        if self.config.rename_only:
            # Rename in place - same directory as original
            return original_path.parent / filename
        else:
            # Move to archive structure
            year = creation_date.strftime("%Y")
            month = creation_date.strftime("%m")
            target_dir = self.config.output_dir / f"{year}" / f"{year}_{month}"
            return target_dir / filename

    def _find_safe_target_path(self, target_path: Path) -> Path:
        """Find a safe target path that doesn't overwrite existing files"""
        if not target_path.exists():
            return target_path

        # File exists, generate incremental names
        stem = target_path.stem
        suffix = target_path.suffix
        parent = target_path.parent

        for i in range(1, self.config.max_duplicate_suffix + 1):
            candidate = parent / f"{stem}_{i:03d}{suffix}"
            if not candidate.exists():
                return candidate

        # If we reach here, we've exceeded max duplicates
        raise ValueError(f"Too many duplicates for {target_path}")

    def _handle_existing_file(self, source_path: Path, target_path: Path) -> Tuple[bool, str]:
        """Handle case where target file already exists"""
        if not target_path.exists():
            return True, "no_conflict"

        # Compare checksums to detect true duplicates
        source_checksum = self._get_file_checksum(source_path)
        target_checksum = self._get_file_checksum(target_path)

        if source_checksum == target_checksum:
            self.logger.info(f"Duplicate file detected: {source_path.name} == {target_path.name}")
            return False, "duplicate"

        # Files are different, find safe name
        self.logger.info(f"File name conflict but different content: {target_path.name}")
        return True, "name_conflict"

    def process_file(self, file_path: Path) -> Dict[str, Any]:
        """Process a single file safely"""
        result = {
            'success': False,
            'action': 'skipped',
            'reason': '',
            'original_path': str(file_path),
            'target_path': None,
            'checksum': None
        }

        try:
            # Skip if not supported extension
            if not self.config.is_supported_extension(file_path):
                result['reason'] = 'unsupported_extension'
                return result

            # Check if already processed
            already_processed, previous_target = self._is_already_processed(file_path)
            if already_processed:
                result['reason'] = 'already_processed'
                result['target_path'] = previous_target
                return result

            # Skip if file is already in archive structure
            if self._is_in_archive_structure(file_path):
                result['reason'] = 'already_in_archive'
                return result

            # Extract metadata to get creation date
            creation_date = self.metadata_extractor.get_creation_date(file_path)
            if not creation_date:
                result['reason'] = 'no_creation_date'
                return result

            # Generate target path
            target_path = self._generate_target_path(file_path, creation_date)

            # Handle existing files
            can_proceed, conflict_type = self._handle_existing_file(file_path, target_path)

            if not can_proceed:
                result['reason'] = conflict_type
                result['target_path'] = str(target_path)
                return result

            if conflict_type == "name_conflict":
                target_path = self._find_safe_target_path(target_path)

            result['target_path'] = str(target_path)

            # Calculate checksum and get file size before operation
            checksum = self._get_file_checksum(file_path)
            file_size = file_path.stat().st_size  # Get size before moving the file
            result['checksum'] = checksum

            # Perform the operation (rename/move/copy) SAFELY
            if not self.config.dry_run:
                if self.config.rename_only:
                    success = self.file_ops.safe_rename(file_path, target_path, verify=self.config.verify_checksums)
                    if not success:
                        raise ValueError(f"Safe rename failed: {file_path} -> {target_path}")
                    result['action'] = 'renamed'
                elif self.config.copy_mode:
                    success = self.file_ops.safe_copy(file_path, target_path, verify=self.config.verify_checksums)
                    if not success:
                        raise ValueError(f"Safe copy failed: {file_path} -> {target_path}")
                    result['action'] = 'copied'
                else:
                    success = self.file_ops.safe_move(file_path, target_path, verify=self.config.verify_checksums)
                    if not success:
                        raise ValueError(f"Safe move failed: {file_path} -> {target_path}")
                    result['action'] = 'moved'

                # Mark as processed only after successful operation
                self._mark_as_processed(file_path, checksum, target_path, file_size)
            else:
                result['action'] = 'dry_run'

            result['success'] = True

        except Exception as e:
            self.logger.error(f"Error processing {file_path}: {e}")
            result['reason'] = str(e)

        return result

    def _is_inside_archive_dir(self, file_path: Path, archive_path: Path) -> bool:
        """Check if file is inside the archive directory"""
        try:
            # Check if file_path is inside archive_path
            return archive_path in file_path.parents or file_path == archive_path
        except Exception:
            return False

    def _is_in_archive_structure(self, file_path: Path) -> bool:
        """Check if file is already in the archive structure"""
        try:
            # Check if path contains year/year-month pattern
            parts = file_path.parts
            for i, part in enumerate(parts[:-1]):  # Exclude filename
                if part.isdigit() and len(part) == 4:  # Year
                    if i + 1 < len(parts) - 1:  # Has next part
                        next_part = parts[i + 1]
                        if next_part.startswith(f"{part}-") and len(next_part) == 7:
                            return True
            return False
        except Exception:
            return False

    def process_directory(self, input_dir: Path) -> Dict[str, int]:
        """Process all supported files in directory"""
        results = {
            'processed': 0,
            'skipped': 0,
            'duplicates': 0,
            'errors': 0
        }

        # Find all supported files
        files_to_process: List[Path] = []
        for ext in self.config.extensions:
            # Case-insensitive search
            files_to_process.extend(input_dir.rglob(f"*.{ext}"))
            files_to_process.extend(input_dir.rglob(f"*.{ext.upper()}"))

        # Remove duplicates and sort
        files_to_process = sorted(set(files_to_process))

        # Filter out files that are inside the archive/output directory
        archive_path = self.config.output_dir.resolve()
        filtered_files = []
        for file_path in files_to_process:
            try:
                file_path_resolved = file_path.resolve()
                # Check if file is inside the archive directory
                if not self._is_inside_archive_dir(file_path_resolved, archive_path):
                    filtered_files.append(file_path)
                else:
                    self.logger.debug(f"Skipping file inside archive directory: {file_path}")
            except Exception as e:
                self.logger.warning(f"Could not resolve path for {file_path}: {e}")
                # If we can't resolve the path, include it to be safe
                filtered_files.append(file_path)

        files_to_process = filtered_files

        self.logger.info(f"Found {len(files_to_process)} files to process")

        for i, file_path in enumerate(files_to_process, 1):
            self.logger.debug(f"Processing ({i}/{len(files_to_process)}): {file_path.name}")

            result = self.process_file(file_path)

            if result['success']:
                if result['action'] in ['moved', 'copied', 'renamed', 'dry_run']:
                    results['processed'] += 1
                    action_msg = result['action'].replace('_', ' ').upper()
                    target_path = Path(result['target_path'])
                    if self.config.rename_only or result['action'] == 'renamed':
                        # For rename only, show just the filename change
                        self.logger.info(f"{action_msg}: {file_path.name} -> {target_path.name}")
                    else:
                        # Show relative path from archive root for clarity
                        relative_target = target_path.relative_to(self.config.output_dir)
                        self.logger.info(f"{action_msg}: {file_path.name} -> {relative_target}")
            else:
                if result['reason'] in ['duplicate', 'already_processed']:
                    results['duplicates'] += 1
                    self.logger.debug(f"SKIP ({result['reason']}): {file_path.name}")
                elif result['reason'] in ['unsupported_extension', 'already_in_archive', 'no_creation_date']:
                    results['skipped'] += 1
                    self.logger.debug(f"SKIP ({result['reason']}): {file_path.name}")
                else:
                    results['errors'] += 1
                    self.logger.error(f"ERROR: {file_path.name} - {result['reason']}")

        return results
