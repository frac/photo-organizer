"""Drive comparison functionality using existing SQLite database"""

import hashlib
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import signal
import shutil
import os


class DriveScanner:
    """Scanner for backup drives using the existing database structure"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._lock = threading.Lock()  # For thread-safe logging and DB operations
        self._cancelled = threading.Event()  # For graceful shutdown

    def _get_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of file"""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.error(f"Error reading {file_path}: {e}")
            return ""

    def _get_file_checksum_fast(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum with larger buffer for speed"""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                # Use 64KB buffer instead of 4KB for better performance
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.error(f"Error reading {file_path}: {e}")
            return ""

    def cancel(self) -> None:
        """Cancel ongoing operations"""
        self._cancelled.set()

    def _process_file_batch(
        self, files_batch: List[Path], drive_path: Path
    ) -> List[Tuple]:
        """Process a batch of files and return their data for DB insertion"""
        batch_data = []

        for file_path in files_batch:
            # Check for cancellation
            if self._cancelled.is_set():
                with self._lock:
                    self.logger.info("Batch processing cancelled by user")
                break

            try:
                relative_path = file_path.relative_to(drive_path)
                file_size = file_path.stat().st_size
                checksum = self._get_file_checksum_fast(file_path)

                if checksum:
                    batch_data.append(
                        (
                            str(relative_path),
                            str(file_path),
                            file_size,
                            checksum,
                            str(drive_path),
                        )
                    )

            except Exception as e:
                if not self._cancelled.is_set():  # Only log if not cancelled
                    with self._lock:
                        self.logger.error(f"Error processing {file_path}: {e}")
                continue

        return batch_data

    def scan_drive_to_db(self, drive_path: Path, db_path: Optional[Path] = None) -> int:
        """Scan a drive and store file info in database

        Returns number of files scanned
        """
        if not drive_path.exists():
            self.logger.error(f"Drive path does not exist: {drive_path}")
            return 0

        if db_path is None:
            db_path = drive_path / ".photo_organizer_drive_scan.sqlite"

        # Initialize database
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drive_files (
                relative_path TEXT PRIMARY KEY,
                full_path TEXT,
                file_size INTEGER,
                checksum TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                drive_path TEXT
            )
        """
        )
        conn.commit()

        self.logger.info(f"Scanning drive: {drive_path}")

        files_scanned = 0
        files_to_process = []

        # Collect all files first
        for file_path in drive_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                files_to_process.append(file_path)

        self.logger.info(f"Found {len(files_to_process)} files to scan")

        # Check for existing files to skip unchanged ones
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_full_path ON drive_files(full_path)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_relative_path ON drive_files(relative_path)"
        )

        # Get existing files with their modification times
        existing_files = {}
        cursor = conn.execute(
            "SELECT full_path, file_size, scanned_at FROM drive_files WHERE drive_path = ?",
            (str(drive_path),),
        )
        for row in cursor:
            existing_files[row[0]] = {"size": row[1], "scanned_at": row[2]}

        # Filter files that haven't changed
        files_to_scan = []
        files_skipped = 0

        for file_path in files_to_process:
            try:
                file_stat = file_path.stat()
                file_size = file_stat.st_size

                existing = existing_files.get(str(file_path))
                if existing and existing["size"] == file_size:
                    # File exists in DB with same size, assume unchanged
                    files_skipped += 1
                    continue

                files_to_scan.append(file_path)

            except Exception as e:
                self.logger.error(f"Error checking {file_path}: {e}")
                continue

        self.logger.info(
            f"Skipping {files_skipped} unchanged files, scanning {len(files_to_scan)} files"
        )

        if not files_to_scan:
            self.logger.info("No files to scan")
            conn.close()
            return files_scanned

        # Process files in parallel
        batch_size = 20  # Files per batch
        max_workers = min(
            4, (len(files_to_scan) + batch_size - 1) // batch_size
        )  # Don't over-parallelize

        self.logger.info(f"Processing with {max_workers} threads...")

        # Split files into batches
        file_batches = []
        for i in range(0, len(files_to_scan), batch_size):
            file_batches.append(files_to_scan[i : i + batch_size])

        all_results = []
        processed_files = 0
        start_time = time.time()

        # Process batches in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all batches
            future_to_batch = {
                executor.submit(self._process_file_batch, batch, drive_path): i
                for i, batch in enumerate(file_batches)
            }

            # Collect results as they complete
            for future in as_completed(future_to_batch):
                # Check for cancellation
                if self._cancelled.is_set():
                    self.logger.info("Cancelling remaining batches...")
                    # Cancel remaining futures
                    for f in future_to_batch:
                        f.cancel()
                    break

                batch_idx = future_to_batch[future]
                try:
                    batch_results = future.result()
                    all_results.extend(batch_results)
                    processed_files += len(batch_results)

                    # Progress update (thread-safe)
                    with self._lock:
                        elapsed = time.time() - start_time
                        rate = processed_files / elapsed if elapsed > 0 else 0
                        self.logger.info(
                            f"Processed batch {batch_idx + 1}/{len(file_batches)} "
                            f"({processed_files}/{len(files_to_scan)} files, {rate:.1f} files/sec)"
                        )

                except Exception as e:
                    if not self._cancelled.is_set():  # Only log if not cancelled
                        with self._lock:
                            self.logger.error(
                                f"Error processing batch {batch_idx}: {e}"
                            )

        # Bulk insert all results
        if all_results:
            self.logger.info(
                f"Inserting {len(all_results)} file records into database..."
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO drive_files
                (relative_path, full_path, file_size, checksum, drive_path)
                VALUES (?, ?, ?, ?, ?)
            """,
                all_results,
            )
            conn.commit()
            files_scanned = len(all_results)

        elapsed_total = time.time() - start_time
        self.logger.info(
            f"Completed scanning: {files_scanned} files in {elapsed_total:.1f}s "
            f"({files_scanned/elapsed_total:.1f} files/sec)"
        )

        conn.close()
        self.logger.info(f"Completed scanning {drive_path}: {files_scanned} files")
        return files_scanned

    def get_drive_files(self, db_path: Path) -> Dict[str, Tuple[int, str]]:
        """Get all files from drive database

        Returns dict of {relative_path: (file_size, checksum)}
        """
        if not db_path.exists():
            return {}

        files = {}
        conn = sqlite3.connect(db_path)

        try:
            cursor = conn.execute(
                "SELECT relative_path, file_size, checksum FROM drive_files"
            )
            for row in cursor:
                relative_path, file_size, checksum = row
                files[relative_path] = (file_size, checksum)
        finally:
            conn.close()

        return files

    def _add_file_to_db(
        self,
        db_path: Path,
        relative_path: str,
        full_path: str,
        file_size: int,
        checksum: str,
    ) -> None:
        """Add a single file to the drive database"""
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                INSERT OR REPLACE INTO drive_files
                (relative_path, full_path, file_size, checksum, drive_path, scanned_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
                (relative_path, full_path, file_size, checksum, str(db_path.parent)),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Error adding file to database: {e}")


class DriveSynchronizer:
    """Synchronizes files between backup drives"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._lock = threading.Lock()
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        """Cancel ongoing operations"""
        self._cancelled.set()

    def _check_drive_space(self, drive_path: Path, required_bytes: int) -> bool:
        """Check if drive has enough free space"""
        try:
            statvfs = os.statvfs(drive_path)
            free_bytes = statvfs.f_frsize * statvfs.f_bavail
            return free_bytes >= required_bytes
        except Exception as e:
            self.logger.warning(f"Could not check space on {drive_path}: {e}")
            return True  # Assume OK if we can't check

    def _safe_copy_file(
        self, source_path: Path, target_path: Path, verify: bool = True
    ) -> bool:
        """Safely copy a file with verification"""
        try:
            # Ensure target directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Get source checksum for verification
            source_checksum = None
            if verify:
                source_checksum = self._calculate_checksum(source_path)

            # Copy file with metadata preservation
            shutil.copy2(source_path, target_path)

            # Verify copy if requested
            if verify and source_checksum:
                target_checksum = self._calculate_checksum(target_path)
                if source_checksum != target_checksum:
                    # Remove corrupted copy
                    target_path.unlink(missing_ok=True)
                    raise ValueError("Copy verification failed: checksums don't match")

            return True

        except Exception as e:
            self.logger.error(f"Failed to copy {source_path} -> {target_path}: {e}")
            return False

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of file"""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculating checksum for {file_path}: {e}")
            return ""

    def sync_drives(
        self,
        drive1_path: Path,
        drive2_path: Path,
        drive1_files: Dict[str, Tuple[int, str]],
        drive2_files: Dict[str, Tuple[int, str]],
        dry_run: bool = False,
    ) -> Dict[str, int]:
        """Synchronize files between two drives

        Returns dict with sync statistics
        """
        if self._cancelled.is_set():
            return {}

        # Find files that need syncing
        only_in_drive1 = [f for f in drive1_files.keys() if f not in drive2_files]
        only_in_drive2 = [f for f in drive2_files.keys() if f not in drive1_files]

        # Find files with different content
        different_files = []
        for file_path in set(drive1_files.keys()) & set(drive2_files.keys()):
            size1, checksum1 = drive1_files[file_path]
            size2, checksum2 = drive2_files[file_path]
            if checksum1 != checksum2:
                different_files.append(
                    {
                        "path": file_path,
                        "drive1": {"size": size1, "checksum": checksum1},
                        "drive2": {"size": size2, "checksum": checksum2},
                    }
                )

        # Calculate space requirements
        space_needed_drive1 = sum(drive2_files[f][0] for f in only_in_drive2)
        space_needed_drive2 = sum(drive1_files[f][0] for f in only_in_drive1)

        # Check available space
        if not self._check_drive_space(drive1_path, space_needed_drive1):
            self.logger.error(
                f"Drive 1 ({drive1_path}) doesn't have enough space for {space_needed_drive1:,} bytes"
            )
            return {}

        if not self._check_drive_space(drive2_path, space_needed_drive2):
            self.logger.error(
                f"Drive 2 ({drive2_path}) doesn't have enough space for {space_needed_drive2:,} bytes"
            )
            return {}

        sync_stats = {
            "files_copied_to_drive1": 0,
            "files_copied_to_drive2": 0,
            "files_skipped": 0,
            "errors": 0,
            "bytes_copied": 0,
        }

        if dry_run:
            self.logger.info("DRY RUN MODE - No files will be copied")

        # Copy files missing from Drive 1
        if only_in_drive2:
            self.logger.info(
                f"\n=== Copying {len(only_in_drive2)} files to Drive 1 ==="
            )
            for i, file_path in enumerate(only_in_drive2, 1):
                if self._cancelled.is_set():
                    break

                source_path = drive2_path / file_path
                target_path = drive1_path / file_path

                self.logger.info(
                    f"[{i}/{len(only_in_drive2)}] Copying to Drive 1: {file_path}"
                )

                if not dry_run:
                    if self._safe_copy_file(source_path, target_path):
                        sync_stats["files_copied_to_drive1"] += 1
                        sync_stats["bytes_copied"] += drive2_files[file_path][0]
                    else:
                        sync_stats["errors"] += 1
                else:
                    sync_stats["files_copied_to_drive1"] += 1
                    sync_stats["bytes_copied"] += drive2_files[file_path][0]

        # Copy files missing from Drive 2
        if only_in_drive1:
            self.logger.info(
                f"\n=== Copying {len(only_in_drive1)} files to Drive 2 ==="
            )
            for i, file_path in enumerate(only_in_drive1, 1):
                if self._cancelled.is_set():
                    break

                source_path = drive1_path / file_path
                target_path = drive2_path / file_path

                self.logger.info(
                    f"[{i}/{len(only_in_drive1)}] Copying to Drive 2: {file_path}"
                )

                if not dry_run:
                    if self._safe_copy_file(source_path, target_path):
                        sync_stats["files_copied_to_drive2"] += 1
                        sync_stats["bytes_copied"] += drive1_files[file_path][0]
                    else:
                        sync_stats["errors"] += 1
                else:
                    sync_stats["files_copied_to_drive2"] += 1
                    sync_stats["bytes_copied"] += drive1_files[file_path][0]

        # Handle files with different content
        if different_files:
            self.logger.info(
                f"\n=== Handling {len(different_files)} files with different content ==="
            )
            self.logger.info(
                "Files with different content will be skipped (manual intervention required)"
            )
            sync_stats["files_skipped"] = len(different_files)

            for diff in different_files[:10]:  # Show first 10
                self.logger.info(f"  {diff['path']} - Different content, skipping")
            if len(different_files) > 10:
                self.logger.info(f"  ... and {len(different_files) - 10} more files")

        return sync_stats


def compare_backup_drives(
    drive1_path: Path,
    drive2_path: Path,
    logger: logging.Logger,
    force_rescan: bool = False,
) -> None:
    """Compare two backup drives and show differences"""

    logger.info("=== Backup Drive Comparison ===")
    logger.info(f"Drive 1: {drive1_path}")
    logger.info(f"Drive 2: {drive2_path}")

    if not drive1_path.exists():
        logger.error(f"Drive 1 does not exist: {drive1_path}")
        return

    if not drive2_path.exists():
        logger.error(f"Drive 2 does not exist: {drive2_path}")
        return

    scanner = DriveScanner(logger)

    # Set up signal handler for graceful cancellation
    def signal_handler(signum: int, frame) -> None:
        logger.info("\nReceived interrupt signal (Ctrl+C). Cancelling operations...")
        scanner.cancel()

    # Register signal handlers
    original_sigint = signal.signal(signal.SIGINT, signal_handler)
    original_sigterm = signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Database paths
        db1_path = drive1_path / ".photo_organizer_drive_scan.sqlite"
        db2_path = drive2_path / ".photo_organizer_drive_scan.sqlite"

        # Scan both drives (or use existing scans)
        drive1_needs_scan = force_rescan or not db1_path.exists()
        drive2_needs_scan = force_rescan or not db2_path.exists()

        if scanner._cancelled.is_set():
            logger.info("Operation cancelled before scanning")
            return

        if drive1_needs_scan and drive2_needs_scan:
            logger.info("\n--- Scanning Both Drives in Parallel ---")

            # Scan both drives simultaneously
            with ThreadPoolExecutor(max_workers=2) as executor:
                future1 = executor.submit(
                    scanner.scan_drive_to_db, drive1_path, db1_path
                )
                future2 = executor.submit(
                    scanner.scan_drive_to_db, drive2_path, db2_path
                )

                # Wait for both to complete
                try:
                    files1 = future1.result(timeout=3600)  # 1 hour timeout
                    files2 = future2.result(timeout=3600)

                    if not scanner._cancelled.is_set():
                        logger.info(
                            f"Parallel scan completed: Drive 1: {files1} files, Drive 2: {files2} files"
                        )
                except Exception as e:
                    if not scanner._cancelled.is_set():
                        logger.error(f"Error during parallel scanning: {e}")
                        return

        elif drive1_needs_scan:
            logger.info("\n--- Scanning Drive 1 ---")
            scanner.scan_drive_to_db(drive1_path, db1_path)
        elif drive2_needs_scan:
            logger.info("\n--- Scanning Drive 2 ---")
            scanner.scan_drive_to_db(drive2_path, db2_path)
        else:
            logger.info(
                "Using existing scans for both drives (use --rescan to force rescan)"
            )

        if scanner._cancelled.is_set():
            logger.info("Operation cancelled during scanning")
            return

        # Load file data
        drive1_files = scanner.get_drive_files(db1_path)
        drive2_files = scanner.get_drive_files(db2_path)

        logger.info("\n=== Comparison Results ===")
        logger.info(f"Drive 1: {len(drive1_files)} files")
        logger.info(f"Drive 2: {len(drive2_files)} files")

        if scanner._cancelled.is_set():
            logger.info("Operation cancelled before comparison")
            return

        # Find differences
        only_in_drive1 = []
        only_in_drive2 = []
        different_files = []
        identical_files = []

        all_files = set(drive1_files.keys()) | set(drive2_files.keys())

        for file_path in all_files:
            if scanner._cancelled.is_set():
                logger.info("Comparison cancelled by user")
                return

            if file_path in drive1_files and file_path in drive2_files:
                # File exists in both drives
                size1, checksum1 = drive1_files[file_path]
                size2, checksum2 = drive2_files[file_path]

                if checksum1 == checksum2:
                    identical_files.append(file_path)
                else:
                    different_files.append(
                        {
                            "path": file_path,
                            "drive1": {"size": size1, "checksum": checksum1},
                            "drive2": {"size": size2, "checksum": checksum2},
                        }
                    )
            elif file_path in drive1_files:
                only_in_drive1.append(file_path)
            else:
                only_in_drive2.append(file_path)

        # Report results
        logger.info(
            f"\n=== Files Missing from Drive 2 ({len(only_in_drive1)} files) ==="
        )
        if only_in_drive1:
            for file_path in sorted(only_in_drive1)[:20]:  # Show first 20
                size, _ = drive1_files[file_path]
                logger.info(f"  {file_path} ({size:,} bytes)")
            if len(only_in_drive1) > 20:
                logger.info(f"  ... and {len(only_in_drive1) - 20} more files")
        else:
            logger.info("  ✓ No files missing from Drive 2")

        logger.info(
            f"\n=== Files Missing from Drive 1 ({len(only_in_drive2)} files) ==="
        )
        if only_in_drive2:
            for file_path in sorted(only_in_drive2)[:20]:  # Show first 20
                size, _ = drive2_files[file_path]
                logger.info(f"  {file_path} ({size:,} bytes)")
            if len(only_in_drive2) > 20:
                logger.info(f"  ... and {len(only_in_drive2) - 20} more files")
        else:
            logger.info("  ✓ No files missing from Drive 1")

        logger.info(
            f"\n=== Files with Different Content ({len(different_files)} files) ==="
        )
        if different_files:
            for diff in different_files[:10]:  # Show first 10
                logger.info(f"  {diff['path']}")
                checksum1 = str(diff['drive1']['checksum'])
                checksum2 = str(diff['drive2']['checksum'])
                logger.info(
                    f"    Drive 1: {diff['drive1']['size']:,} bytes, checksum: {checksum1[:16]}..."
                )
                logger.info(
                    f"    Drive 2: {diff['drive2']['size']:,} bytes, checksum: {checksum2[:16]}..."
                )
            if len(different_files) > 10:
                logger.info(f"  ... and {len(different_files) - 10} more files")
        else:
            logger.info("  ✓ All common files have identical content")

        # Summary
        total_files = len(all_files)
        files_needing_sync = (
            len(only_in_drive1) + len(only_in_drive2) + len(different_files)
        )

        logger.info("\n=== Summary ===")
        logger.info(f"Total unique files: {total_files}")
        logger.info(f"Identical files: {len(identical_files)}")
        logger.info(f"Files needing sync: {files_needing_sync}")

        if files_needing_sync == 0:
            logger.info("🎉 Drives are perfectly synchronized!")
        else:
            logger.info("⚠️  Drives need synchronization")

            # Suggest sync commands
            if only_in_drive1:
                logger.info("\nTo copy missing files from Drive 1 to Drive 2:")
                logger.info(f"  # Copy {len(only_in_drive1)} files")

            if only_in_drive2:
                logger.info("\nTo copy missing files from Drive 2 to Drive 1:")
                logger.info(f"  # Copy {len(only_in_drive2)} files")

    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        scanner.cancel()
    except Exception as e:
        logger.error(f"Unexpected error during comparison: {e}")
    finally:
        # Restore original signal handlers
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)

        if scanner._cancelled.is_set():
            logger.info("Drive comparison cancelled by user")


def sync_backup_drives(
    drive1_path: Path,
    drive2_path: Path,
    logger: logging.Logger,
    force_rescan: bool = False,
    dry_run: bool = False,
) -> bool:
    """Compare and synchronize two backup drives

    Returns True if sync was successful, False otherwise
    """
    # Set up signal handling for graceful shutdown
    original_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
    original_sigterm = signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def signal_handler(signum: int, frame) -> None:
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        scanner.cancel()
        synchronizer.cancel()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    scanner = DriveScanner(logger)
    synchronizer = DriveSynchronizer(logger)

    try:
        # Database paths
        db1_path = drive1_path / ".photo_organizer_drive_scan.sqlite"
        db2_path = drive2_path / ".photo_organizer_drive_scan.sqlite"

        # Scan both drives (or use existing scans)
        drive1_needs_scan = force_rescan or not db1_path.exists()
        drive2_needs_scan = force_rescan or not db2_path.exists()

        if scanner._cancelled.is_set():
            logger.info("Operation cancelled before scanning")
            return False

        if drive1_needs_scan and drive2_needs_scan:
            logger.info("\n--- Scanning Both Drives in Parallel ---")

            # Scan both drives simultaneously
            with ThreadPoolExecutor(max_workers=2) as executor:
                future1 = executor.submit(
                    scanner.scan_drive_to_db, drive1_path, db1_path
                )
                future2 = executor.submit(
                    scanner.scan_drive_to_db, drive2_path, db2_path
                )

                # Wait for both to complete
                try:
                    files1 = future1.result(timeout=3600)  # 1 hour timeout
                    files2 = future2.result(timeout=3600)

                    if not scanner._cancelled.is_set():
                        logger.info(
                            f"Parallel scan completed: Drive 1: {files1} files, Drive 2: {files2} files"
                        )
                except Exception as e:
                    if not scanner._cancelled.is_set():
                        logger.error(f"Error during parallel scanning: {e}")
                        return False

        elif drive1_needs_scan:
            logger.info("\n--- Scanning Drive 1 ---")
            scanner.scan_drive_to_db(drive1_path, db1_path)
        elif drive2_needs_scan:
            logger.info("\n--- Scanning Drive 2 ---")
            scanner.scan_drive_to_db(drive2_path, db2_path)
        else:
            logger.info(
                "Using existing scans for both drives (use --rescan to force rescan)"
            )

        if scanner._cancelled.is_set():
            logger.info("Operation cancelled after scanning")
            return False

        # Get file information from both drives
        drive1_files = scanner.get_drive_files(db1_path)
        drive2_files = scanner.get_drive_files(db2_path)

        if not drive1_files and not drive2_files:
            logger.error("No files found on either drive")
            return False

        logger.info(f"\nDrive 1 ({drive1_path}): {len(drive1_files)} files")
        logger.info(f"Drive 2 ({drive2_path}): {len(drive2_files)} files")

        # Find differences
        only_in_drive1 = [f for f in drive1_files.keys() if f not in drive2_files]
        only_in_drive2 = [f for f in drive2_files.keys() if f not in drive1_files]
        different_files = []

        for file_path in set(drive1_files.keys()) & set(drive2_files.keys()):
            size1, checksum1 = drive1_files[file_path]
            size2, checksum2 = drive2_files[file_path]
            if checksum1 != checksum2:
                different_files.append(
                    {
                        "path": file_path,
                        "drive1": {"size": size1, "checksum": checksum1},
                        "drive2": {"size": size2, "checksum": checksum2},
                    }
                )

        # Report differences
        logger.info(
            f"\n=== Files Missing from Drive 2 ({len(only_in_drive1)} files) ==="
        )
        if only_in_drive1:
            for file_path in sorted(only_in_drive1)[:20]:  # Show first 20
                size, _ = drive1_files[file_path]
                logger.info(f"  {file_path} ({size:,} bytes)")
            if len(only_in_drive1) > 20:
                logger.info(f"  ... and {len(only_in_drive1) - 20} more files")
        else:
            logger.info("  ✓ No files missing from Drive 2")

        logger.info(
            f"\n=== Files Missing from Drive 1 ({len(only_in_drive2)} files) ==="
        )
        if only_in_drive2:
            for file_path in sorted(only_in_drive2)[:20]:  # Show first 20
                size, _ = drive2_files[file_path]
                logger.info(f"  {file_path} ({size:,} bytes)")
            if len(only_in_drive2) > 20:
                logger.info(f"  ... and {len(only_in_drive2) - 20} more files")
        else:
            logger.info("  ✓ No files missing from Drive 1")

        logger.info(
            f"\n=== Files with Different Content ({len(different_files)} files) ==="
        )
        if different_files:
            for diff in different_files[:10]:  # Show first 10
                logger.info(f"  {diff['path']}")
                checksum1 = str(diff['drive1']['checksum'])
                checksum2 = str(diff['drive2']['checksum'])
                logger.info(
                    f"    Drive 1: {diff['drive1']['size']:,} bytes, checksum: {checksum1[:16]}..."
                )
                logger.info(
                    f"    Drive 2: {diff['drive2']['size']:,} bytes, checksum: {checksum2[:16]}..."
                )
            if len(different_files) > 10:
                logger.info(f"  ... and {len(different_files) - 10} more files")
        else:
            logger.info("  ✓ All common files have identical content")

        # Summary
        total_files = len(set(drive1_files.keys()) | set(drive2_files.keys()))
        files_needing_sync = (
            len(only_in_drive1) + len(only_in_drive2) + len(different_files)
        )

        logger.info("\n=== Summary ===")
        logger.info(f"Total unique files: {total_files}")
        logger.info(f"Files needing sync: {files_needing_sync}")

        if files_needing_sync == 0:
            logger.info("🎉 Drives are perfectly synchronized!")
            return True

        # Perform synchronization
        logger.info("\n⚠️  Drives need synchronization")

        if not dry_run:
            logger.info("Starting automatic synchronization...")
            sync_stats = synchronizer.sync_drives(
                drive1_path, drive2_path, drive1_files, drive2_files, dry_run=False
            )

            if sync_stats:
                logger.info("\n=== Synchronization Complete ===")
                logger.info(
                    f"Files copied to Drive 1: {sync_stats['files_copied_to_drive1']}"
                )
                logger.info(
                    f"Files copied to Drive 2: {sync_stats['files_copied_to_drive2']}"
                )
                logger.info(f"Files skipped: {sync_stats['files_skipped']}")
                logger.info(f"Errors: {sync_stats['errors']}")
                logger.info(f"Total bytes copied: {sync_stats['bytes_copied']:,}")

                if sync_stats["errors"] == 0:
                    logger.info("✅ Synchronization completed successfully!")
                    return True
                else:
                    logger.warning("⚠️  Synchronization completed with errors")
                    return False
            else:
                logger.error("❌ Synchronization failed")
                return False
        else:
            logger.info("DRY RUN MODE - No files will be copied")
            logger.info("Run without --dry-run to perform actual synchronization")
            return True

    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        scanner.cancel()
        synchronizer.cancel()
        return False
    except Exception as e:
        logger.error(f"Unexpected error during sync: {e}")
        return False
    finally:
        # Restore original signal handlers
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)

        if scanner._cancelled.is_set() or synchronizer._cancelled.is_set():
            logger.info("Drive synchronization cancelled by user")


def backup_archive_to_drives(
    archive_path: Path,
    drive_paths: List[Path],
    logger: logging.Logger,
    dry_run: bool = False,
    rescan: bool = False,
) -> bool:
    """Backup local archive to one or more backup drives

    Args:
        archive_path: Path to the local archive directory
        drive_paths: List of paths to backup drives
        logger: Logger instance
        dry_run: If True, show what would be done without actually doing it

    Returns:
        True if backup was successful, False otherwise
    """
    logger.info("=== Backup Archive to Drives ===")
    original_archive_path = archive_path
    logger.info(f"Original archive path: {original_archive_path}")
    logger.info(f"Target drives: {[str(d) for d in drive_paths]}")

    # Resolve relative archive path to absolute
    if archive_path == Path(".") or archive_path.is_relative_to(Path.cwd()):
        # If it's a relative path like "." or "archive", resolve it
        resolved_archive = archive_path.resolve()

        # Check if the resolved path is an archive (has year subdirectories)
        has_year_dirs = any(
            (resolved_archive / item).is_dir()
            and item.name.isdigit()
            and len(item.name) == 4
            and 1900 <= int(item.name) <= 2100
            for item in resolved_archive.iterdir()
        )

        if has_year_dirs:
            # The resolved path itself is an archive
            archive_path = resolved_archive
        else:
            # Try to find an archive subdirectory
            potential_archive = resolved_archive / "archive"
            if potential_archive.exists():
                archive_path = potential_archive
            else:
                # If still no archive subdirectory, check if we're in a directory that should have an archive
                # This handles the case where user is in ~/pics and uses -a .
                if archive_path == Path("."):
                    potential_archive = Path.cwd() / "archive"
                    if potential_archive.exists():
                        archive_path = potential_archive
                    else:
                        # Check if current directory itself is an archive (has year subdirectories)
                        current_dir = Path.cwd()
                        has_year_dirs = any(
                            (current_dir / item).is_dir()
                            and item.name.isdigit()
                            and len(item.name) == 4
                            and 1900 <= int(item.name) <= 2100
                            for item in current_dir.iterdir()
                        )
                        if has_year_dirs:
                            archive_path = current_dir
                        else:
                            # Check if there's an archive subdirectory in current directory
                            # Look for common archive directory names
                            potential_archive_names = [
                                "archive",
                                "Archive",
                                "photos",
                                "Photos",
                                "local_archive",
                            ]
                            archive_subdir = None

                            for name in potential_archive_names:
                                potential_dir = current_dir / name
                                if potential_dir.exists() and potential_dir.is_dir():
                                    archive_subdir = potential_dir
                                    break

                            if archive_subdir:
                                archive_path = archive_subdir
                            else:
                                logger.error(
                                    f"No archive directory found. Expected one of: {[current_dir / name for name in potential_archive_names]}"
                                )
                                return False
                else:
                    logger.error(f"Archive path does not exist: {resolved_archive}")
                    return False
    else:
        # Absolute path, check if it exists
        if not archive_path.exists():
            logger.error(f"Archive path does not exist: {archive_path}")
            return False

    if not archive_path.is_dir():
        logger.error(f"Archive path is not a directory: {archive_path}")
        return False

    # Set up signal handling for graceful shutdown
    original_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
    original_sigterm = signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def signal_handler(signum: int, frame) -> None:
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        scanner.cancel()
        synchronizer.cancel()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    scanner = DriveScanner(logger)
    synchronizer = DriveSynchronizer(logger)

    try:
        # Scan each target drive
        drive_files = {}
        drive_archive_paths = {}

        for drive_path in drive_paths:
            if not drive_path.exists():
                logger.error(f"Drive path does not exist: {drive_path}")
                return False

            logger.info(f"\n--- Scanning Drive: {drive_path} ---")
            db_path = drive_path / ".photo_organizer_drive_scan.sqlite"

            # Check if we already have a scan of this drive
            if db_path.exists() and not rescan:
                logger.info(f"Using existing scan data for {drive_path}")
                drive_files[drive_path] = scanner.get_drive_files(db_path)
            else:
                # Scan drive to get current file list
                logger.info(f"Scanning drive {drive_path}...")
                scanner.scan_drive_to_db(drive_path, db_path)
                drive_files[drive_path] = scanner.get_drive_files(db_path)

            if scanner._cancelled.is_set():
                logger.info("Operation cancelled during scanning")
                return False

            # Determine where to place archive files on this drive
            # Check if there's already an archive subdirectory
            potential_archive_dirs = [
                drive_path / "archive",
                drive_path / "Archive",
                drive_path / "photos",
                drive_path / "Photos",
            ]

            archive_target = None
            for potential_dir in potential_archive_dirs:
                if potential_dir.exists() and potential_dir.is_dir():
                    archive_target = potential_dir
                    logger.info(f"Found existing archive directory: {archive_target}")
                    break

            if not archive_target:
                # Create archive directory at drive root
                archive_target = drive_path / "archive"
                logger.info(f"Will create archive directory: {archive_target}")

            drive_archive_paths[drive_path] = archive_target

        # Recursively scan the local archive
        logger.info(f"Final resolved archive path: {archive_path}")
        logger.info(f"\n--- Scanning Local Archive: {archive_path} ---")
        archive_files = {}

        for file_path in archive_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                try:
                    relative_path = file_path.relative_to(archive_path)
                    file_size = file_path.stat().st_size
                    checksum = scanner._get_file_checksum_fast(file_path)

                    if checksum:
                        archive_files[str(relative_path)] = (file_size, checksum)

                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    continue

        logger.info(f"Found {len(archive_files)} files in local archive")

        # Compare files with each target drive and copy missing ones
        total_files_copied = 0
        total_bytes_copied = 0

        for drive_path in drive_paths:
            logger.info(f"\n--- Backing up to Drive: {drive_path} ---")

            drive_file_dict = drive_files[drive_path]
            archive_target = drive_archive_paths[drive_path]
            files_to_copy = []
            bytes_to_copy = 0

            # Find files that need to be copied
            for file_path, (file_size, checksum) in archive_files.items():
                # Check if file exists in the archive subdirectory of the drive
                drive_archive_file_path = str(Path("archive") / file_path)

                if drive_archive_file_path not in drive_file_dict:
                    files_to_copy.append((file_path, file_size, checksum))
                    bytes_to_copy += file_size
                else:
                    # File exists, check if content is different
                    drive_size, drive_checksum = drive_file_dict[
                        drive_archive_file_path
                    ]
                    if drive_checksum != checksum:
                        files_to_copy.append((file_path, file_size, checksum))
                        bytes_to_copy += file_size

            if not files_to_copy:
                logger.info("✓ Drive is already up to date")
                continue

            logger.info(
                f"Need to copy {len(files_to_copy)} files ({bytes_to_copy:,} bytes)"
            )

            if dry_run:
                logger.info("DRY RUN MODE - No files will be copied")
                for file_path, file_size, _ in files_to_copy[:10]:  # Show first 10
                    logger.info(f"  Would copy: {file_path} ({file_size:,} bytes)")
                if len(files_to_copy) > 10:
                    logger.info(f"  ... and {len(files_to_copy) - 10} more files")
                total_files_copied += len(files_to_copy)
                total_bytes_copied += bytes_to_copy
                continue

            # Check available space
            if not synchronizer._check_drive_space(drive_path, bytes_to_copy):
                logger.error(
                    f"Drive {drive_path} doesn't have enough space for {bytes_to_copy:,} bytes"
                )
                return False

            # Copy files
            files_copied = 0
            bytes_copied = 0
            errors = 0

            for i, (file_path, file_size, checksum) in enumerate(files_to_copy, 1):
                if scanner._cancelled.is_set():
                    break

                source_path = archive_path / file_path
                target_path = archive_target / file_path

                # Ensure target directory exists
                target_path.parent.mkdir(parents=True, exist_ok=True)

                logger.info(f"[{i}/{len(files_to_copy)}] Copying: {file_path}")

                if synchronizer._safe_copy_file(source_path, target_path):
                    files_copied += 1
                    bytes_copied += file_size

                    # Update the drive's database with the archive-relative path
                    drive_archive_file_path = str(Path("archive") / file_path)
                    scanner._add_file_to_db(
                        drive_path / ".photo_organizer_drive_scan.sqlite",
                        drive_archive_file_path,
                        str(target_path),
                        file_size,
                        checksum,
                    )
                else:
                    errors += 1

            logger.info(
                f"Drive {drive_path}: {files_copied} files copied, {errors} errors"
            )
            total_files_copied += files_copied
            total_bytes_copied += bytes_copied

            if errors > 0:
                logger.warning(f"Some files failed to copy to {drive_path}")

        # Summary
        logger.info("\n=== Backup Summary ===")
        logger.info(f"Total files copied: {total_files_copied}")
        logger.info(f"Total bytes copied: {total_bytes_copied:,}")

        if total_files_copied > 0:
            logger.info("✅ Backup completed successfully!")
            return True
        else:
            logger.info("ℹ️  No files needed to be copied (drives are up to date)")
            return True

    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        scanner.cancel()
        synchronizer.cancel()
        return False
    except Exception as e:
        logger.error(f"Unexpected error during backup: {e}")
        return False
    finally:
        # Restore original signal handlers
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)

        if scanner._cancelled.is_set() or synchronizer._cancelled.is_set():
            logger.info("Backup operation cancelled by user")
