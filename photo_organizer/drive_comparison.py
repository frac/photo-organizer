"""Drive comparison functionality using existing SQLite database"""

import hashlib
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import signal
import sys


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
    
    def cancel(self):
        """Cancel ongoing operations"""
        self._cancelled.set()
    
    def _process_file_batch(self, files_batch: List[Path], drive_path: Path) -> List[Tuple]:
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
                    batch_data.append((
                        str(relative_path),
                        str(file_path),
                        file_size,
                        checksum,
                        str(drive_path)
                    ))
                    
            except Exception as e:
                if not self._cancelled.is_set():  # Only log if not cancelled
                    with self._lock:
                        self.logger.error(f"Error processing {file_path}: {e}")
                continue
        
        return batch_data
    
    def scan_drive_to_db(self, drive_path: Path, db_path: Path = None) -> int:
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS drive_files (
                relative_path TEXT PRIMARY KEY,
                full_path TEXT,
                file_size INTEGER,
                checksum TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                drive_path TEXT
            )
        """)
        conn.commit()
        
        self.logger.info(f"Scanning drive: {drive_path}")
        
        files_scanned = 0
        files_to_process = []
        
        # Collect all files first
        for file_path in drive_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith('.'):
                files_to_process.append(file_path)
        
        self.logger.info(f"Found {len(files_to_process)} files to scan")
        
        # Check for existing files to skip unchanged ones
        conn.execute("CREATE INDEX IF NOT EXISTS idx_full_path ON drive_files(full_path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_relative_path ON drive_files(relative_path)")
        
        # Get existing files with their modification times
        existing_files = {}
        cursor = conn.execute("SELECT full_path, file_size, scanned_at FROM drive_files WHERE drive_path = ?", (str(drive_path),))
        for row in cursor:
            existing_files[row[0]] = {'size': row[1], 'scanned_at': row[2]}
        
        # Filter files that haven't changed
        files_to_scan = []
        files_skipped = 0
        
        for file_path in files_to_process:
            try:
                file_stat = file_path.stat()
                file_size = file_stat.st_size
                file_mtime = file_stat.st_mtime
                
                existing = existing_files.get(str(file_path))
                if existing and existing['size'] == file_size:
                    # File exists in DB with same size, assume unchanged
                    files_skipped += 1
                    continue
                    
                files_to_scan.append(file_path)
                
            except Exception as e:
                self.logger.error(f"Error checking {file_path}: {e}")
                continue
        
        self.logger.info(f"Skipping {files_skipped} unchanged files, scanning {len(files_to_scan)} files")
        
        if not files_to_scan:
            self.logger.info("No files to scan")
            conn.close()
            return files_scanned
        
        # Process files in parallel
        batch_size = 20  # Files per batch
        max_workers = min(4, (len(files_to_scan) + batch_size - 1) // batch_size)  # Don't over-parallelize
        
        self.logger.info(f"Processing with {max_workers} threads...")
        
        # Split files into batches
        file_batches = []
        for i in range(0, len(files_to_scan), batch_size):
            file_batches.append(files_to_scan[i:i + batch_size])
        
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
                        self.logger.info(f"Processed batch {batch_idx + 1}/{len(file_batches)} "
                                       f"({processed_files}/{len(files_to_scan)} files, {rate:.1f} files/sec)")
                        
                except Exception as e:
                    if not self._cancelled.is_set():  # Only log if not cancelled
                        with self._lock:
                            self.logger.error(f"Error processing batch {batch_idx}: {e}")
        
        # Bulk insert all results
        if all_results:
            self.logger.info(f"Inserting {len(all_results)} file records into database...")
            conn.executemany("""
                INSERT OR REPLACE INTO drive_files 
                (relative_path, full_path, file_size, checksum, drive_path)
                VALUES (?, ?, ?, ?, ?)
            """, all_results)
            conn.commit()
            files_scanned = len(all_results)
        
        elapsed_total = time.time() - start_time
        self.logger.info(f"Completed scanning: {files_scanned} files in {elapsed_total:.1f}s "
                        f"({files_scanned/elapsed_total:.1f} files/sec)")
        
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
            cursor = conn.execute("SELECT relative_path, file_size, checksum FROM drive_files")
            for row in cursor:
                relative_path, file_size, checksum = row
                files[relative_path] = (file_size, checksum)
        finally:
            conn.close()
        
        return files


def compare_backup_drives(drive1_path: Path, drive2_path: Path, logger: logging.Logger, force_rescan: bool = False):
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
    def signal_handler(signum, frame):
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
                future1 = executor.submit(scanner.scan_drive_to_db, drive1_path, db1_path)
                future2 = executor.submit(scanner.scan_drive_to_db, drive2_path, db2_path)
                
                # Wait for both to complete
                try:
                    files1 = future1.result(timeout=3600)  # 1 hour timeout
                    files2 = future2.result(timeout=3600)
                    
                    if not scanner._cancelled.is_set():
                        logger.info(f"Parallel scan completed: Drive 1: {files1} files, Drive 2: {files2} files")
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
            logger.info("Using existing scans for both drives (use --rescan to force rescan)")
        
        if scanner._cancelled.is_set():
            logger.info("Operation cancelled during scanning")
            return
        
        # Load file data
        drive1_files = scanner.get_drive_files(db1_path)
        drive2_files = scanner.get_drive_files(db2_path)
        
        logger.info(f"\n=== Comparison Results ===")
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
                    different_files.append({
                        'path': file_path,
                        'drive1': {'size': size1, 'checksum': checksum1},
                        'drive2': {'size': size2, 'checksum': checksum2}
                    })
            elif file_path in drive1_files:
                only_in_drive1.append(file_path)
            else:
                only_in_drive2.append(file_path)
        
        # Report results
        logger.info(f"\n=== Files Missing from Drive 2 ({len(only_in_drive1)} files) ===")
        if only_in_drive1:
            for file_path in sorted(only_in_drive1)[:20]:  # Show first 20
                size, _ = drive1_files[file_path]
                logger.info(f"  {file_path} ({size:,} bytes)")
            if len(only_in_drive1) > 20:
                logger.info(f"  ... and {len(only_in_drive1) - 20} more files")
        else:
            logger.info("  ✓ No files missing from Drive 2")
        
        logger.info(f"\n=== Files Missing from Drive 1 ({len(only_in_drive2)} files) ===")
        if only_in_drive2:
            for file_path in sorted(only_in_drive2)[:20]:  # Show first 20
                size, _ = drive2_files[file_path]
                logger.info(f"  {file_path} ({size:,} bytes)")
            if len(only_in_drive2) > 20:
                logger.info(f"  ... and {len(only_in_drive2) - 20} more files")
        else:
            logger.info("  ✓ No files missing from Drive 1")
        
        logger.info(f"\n=== Files with Different Content ({len(different_files)} files) ===")
        if different_files:
            for diff in different_files[:10]:  # Show first 10
                logger.info(f"  {diff['path']}")
                logger.info(f"    Drive 1: {diff['drive1']['size']:,} bytes, checksum: {diff['drive1']['checksum'][:16]}...")
                logger.info(f"    Drive 2: {diff['drive2']['size']:,} bytes, checksum: {diff['drive2']['checksum'][:16]}...")
            if len(different_files) > 10:
                logger.info(f"  ... and {len(different_files) - 10} more files")
        else:
            logger.info("  ✓ All common files have identical content")
        
        # Summary
        total_files = len(all_files)
        files_needing_sync = len(only_in_drive1) + len(only_in_drive2) + len(different_files)
        
        logger.info(f"\n=== Summary ===")
        logger.info(f"Total unique files: {total_files}")
        logger.info(f"Identical files: {len(identical_files)}")
        logger.info(f"Files needing sync: {files_needing_sync}")
        
        if files_needing_sync == 0:
            logger.info("🎉 Drives are perfectly synchronized!")
        else:
            logger.info("⚠️  Drives need synchronization")
            
            # Suggest sync commands
            if only_in_drive1:
                logger.info(f"\nTo copy missing files from Drive 1 to Drive 2:")
                logger.info(f"  # Copy {len(only_in_drive1)} files")
            
            if only_in_drive2:
                logger.info(f"\nTo copy missing files from Drive 2 to Drive 1:")
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