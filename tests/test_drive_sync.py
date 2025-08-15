"""Tests for drive synchronization functionality"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
import sqlite3
import hashlib

from photo_organizer.drive_comparison import (
    DriveScanner,
    DriveSynchronizer,
    sync_backup_drives,
)


class TestDriveScanner:
    """Test DriveScanner functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.drive_path = Path(self.temp_dir) / "test_drive"
        self.drive_path.mkdir()
        self.logger = Mock()

        # Create some test files
        self.test_files = {
            "photo1.jpg": b"fake photo data 1",
            "photo2.jpg": b"fake photo data 2",
            "subfolder/photo3.jpg": b"fake photo data 3",
        }

        for file_path, content in self.test_files.items():
            full_path = self.drive_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)

    def teardown_method(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_scan_drive_to_db(self):
        """Test scanning drive and storing in database"""
        scanner = DriveScanner(self.logger)
        db_path = (
            Path(self.temp_dir) / "test_scan.sqlite"
        )  # Use temp_dir, not drive_path

        # Scan drive
        files_scanned = scanner.scan_drive_to_db(self.drive_path, db_path)

        # Verify database was created and contains expected data
        assert db_path.exists()
        assert files_scanned == len(self.test_files)

        # Check database contents
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT relative_path, file_size FROM drive_files")
        db_files = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        # Verify all test files are in database
        for file_path in self.test_files.keys():
            assert file_path in db_files
            expected_size = len(self.test_files[file_path])
            assert db_files[file_path] == expected_size

    def test_get_drive_files(self):
        """Test retrieving files from drive database"""
        scanner = DriveScanner(self.logger)
        db_path = (
            Path(self.temp_dir) / "test_get.sqlite"
        )  # Use temp_dir, not drive_path

        # First scan the drive
        scanner.scan_drive_to_db(self.drive_path, db_path)

        # Then retrieve files
        files = scanner.get_drive_files(db_path)

        # Verify returned data structure
        assert len(files) == len(self.test_files)
        for file_path, (size, checksum) in files.items():
            assert file_path in self.test_files
            assert size == len(self.test_files[file_path])
            assert len(checksum) == 64  # SHA-256 hex length
            assert checksum.isalnum()  # Should be alphanumeric


class TestDriveSynchronizer:
    """Test DriveSynchronizer functionality"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.drive1_path = Path(self.temp_dir) / "drive1"
        self.drive2_path = Path(self.temp_dir) / "drive2"
        self.drive1_path.mkdir()
        self.drive2_path.mkdir()
        self.logger = Mock()

        # Create test files on drive 1
        self.drive1_files = {
            "photo1.jpg": b"drive1 photo 1",
            "photo2.jpg": b"drive1 photo 2",
            "common.jpg": b"drive1 common",
        }

        for file_path, content in self.drive1_files.items():
            full_path = self.drive1_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)

        # Create test files on drive 2
        self.drive2_files = {
            "photo3.jpg": b"drive2 photo 3",
            "photo4.jpg": b"drive2 photo 4",
            "common.jpg": b"drive2 common different",  # Different content
        }

        for file_path, content in self.drive2_files.items():
            full_path = self.drive2_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)

    def teardown_method(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def test_safe_copy_file(self):
        """Test safe file copying with verification"""
        synchronizer = DriveSynchronizer(self.logger)

        source_file = self.drive1_path / "photo1.jpg"
        target_file = self.drive2_path / "photo1_copy.jpg"

        # Copy file
        result = synchronizer._safe_copy_file(source_file, target_file)

        # Verify copy was successful
        assert result is True
        assert target_file.exists()
        assert target_file.read_bytes() == source_file.read_bytes()

    def test_safe_copy_file_verification_failure(self):
        """Test copy verification failure handling"""
        synchronizer = DriveSynchronizer(self.logger)

        source_file = self.drive1_path / "photo1.jpg"
        target_file = self.drive2_path / "photo1_copy.jpg"

        # Mock checksum calculation to simulate verification failure
        with patch.object(synchronizer, "_calculate_checksum") as mock_checksum:
            mock_checksum.side_effect = ["abc123", "def456"]  # Different checksums

            result = synchronizer._safe_copy_file(source_file, target_file)

            # Should fail due to checksum mismatch
            assert result is False
            # Target file should be removed
            assert not target_file.exists()

    def test_sync_drives_dry_run(self):
        """Test drive synchronization in dry-run mode"""
        synchronizer = DriveSynchronizer(self.logger)

        # Create file dictionaries for testing
        drive1_files = {
            "photo1.jpg": (len(self.drive1_files["photo1.jpg"]), "checksum1"),
            "photo2.jpg": (len(self.drive1_files["photo2.jpg"]), "checksum2"),
            "common.jpg": (len(self.drive1_files["common.jpg"]), "checksum3"),
        }

        drive2_files = {
            "photo3.jpg": (len(self.drive2_files["photo3.jpg"]), "checksum4"),
            "photo4.jpg": (len(self.drive2_files["photo4.jpg"]), "checksum5"),
            "common.jpg": (len(self.drive2_files["common.jpg"]), "checksum6"),
        }

        # Sync in dry-run mode
        stats = synchronizer.sync_drives(
            self.drive1_path, self.drive2_path, drive1_files, drive2_files, dry_run=True
        )

        # Verify statistics
        assert stats["files_copied_to_drive1"] == 2  # photo3.jpg, photo4.jpg
        assert stats["files_copied_to_drive2"] == 2  # photo1.jpg, photo2.jpg
        assert stats["files_skipped"] == 1  # common.jpg (different content)
        assert stats["errors"] == 0

        # Verify no actual files were copied
        assert not (self.drive1_path / "photo3.jpg").exists()
        assert not (self.drive2_path / "photo1.jpg").exists()

    def test_sync_drives_actual_copy(self):
        """Test actual drive synchronization"""
        synchronizer = DriveSynchronizer(self.logger)

        # Create file dictionaries for testing
        drive1_files = {
            "photo1.jpg": (len(self.drive1_files["photo1.jpg"]), "checksum1"),
            "photo2.jpg": (len(self.drive1_files["photo2.jpg"]), "checksum2"),
        }

        drive2_files = {
            "photo3.jpg": (len(self.drive2_files["photo3.jpg"]), "checksum3"),
            "photo4.jpg": (len(self.drive2_files["photo4.jpg"]), "checksum4"),
        }

        # Sync drives
        stats = synchronizer.sync_drives(
            self.drive1_path,
            self.drive2_path,
            drive1_files,
            drive2_files,
            dry_run=False,
        )

        # Verify statistics
        assert stats["files_copied_to_drive1"] == 2
        assert stats["files_copied_to_drive2"] == 2
        assert stats["errors"] == 0

        # Verify files were actually copied
        assert (self.drive1_path / "photo3.jpg").exists()
        assert (self.drive1_path / "photo4.jpg").exists()
        assert (self.drive2_path / "photo1.jpg").exists()
        assert (self.drive2_path / "photo2.jpg").exists()


class TestDriveSyncIntegration:
    """Integration tests for drive synchronization"""

    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.drive1_path = Path(self.temp_dir) / "drive1"
        self.drive2_path = Path(self.temp_dir) / "drive2"
        self.drive1_path.mkdir()
        self.drive2_path.mkdir()
        self.logger = Mock()

        # Create test files
        self.create_test_files()

    def teardown_method(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir)

    def create_test_files(self):
        """Create test files on both drives"""
        # Drive 1 files
        files1 = {
            "photos/2024/photo1.jpg": b"drive1 photo 1 content",
            "photos/2024/photo2.jpg": b"drive1 photo 2 content",
            "photos/2024/common.jpg": b"drive1 common content",
        }

        for file_path, content in files1.items():
            full_path = self.drive1_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)

        # Drive 2 files
        files2 = {
            "photos/2024/photo3.jpg": b"drive2 photo 3 content",
            "photos/2024/photo4.jpg": b"drive2 photo 4 content",
            "photos/2024/common.jpg": b"drive2 common content different",
        }

        for file_path, content in files2.items():
            full_path = self.drive2_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(content)

    @patch("photo_organizer.drive_comparison.DriveScanner")
    @patch("photo_organizer.drive_comparison.DriveSynchronizer")
    def test_sync_backup_drives_integration(self, mock_sync_class, mock_scanner_class):
        """Test full drive synchronization integration"""
        # Mock scanner behavior
        mock_scanner = Mock()
        mock_scanner_class.return_value = mock_scanner
        mock_scanner.scan_drive_to_db.return_value = 3
        mock_scanner._cancelled.is_set.return_value = False

        # Return different files on each drive to trigger sync
        drive1_files = {
            "photos/2024/photo1.jpg": (len(b"drive1 photo 1 content"), "checksum1"),
            "photos/2024/photo2.jpg": (len(b"drive1 photo 2 content"), "checksum2"),
            "photos/2024/common.jpg": (len(b"drive1 common content"), "checksum3"),
        }

        drive2_files = {
            "photos/2024/photo3.jpg": (len(b"drive2 photo 3 content"), "checksum4"),
            "photos/2024/photo4.jpg": (len(b"drive2 photo 4 content"), "checksum5"),
            "photos/2024/common.jpg": (
                len(b"drive2 common content different"),
                "checksum6",
            ),
        }

        mock_scanner.get_drive_files.side_effect = [drive1_files, drive2_files]

        # Mock synchronizer behavior
        mock_synchronizer = Mock()
        mock_sync_class.return_value = mock_synchronizer
        mock_synchronizer._cancelled.is_set.return_value = False
        mock_synchronizer.sync_drives.return_value = {
            "files_copied_to_drive1": 2,
            "files_copied_to_drive2": 2,
            "files_skipped": 1,
            "errors": 0,
            "bytes_copied": 400,
        }

        # Run synchronization
        result = sync_backup_drives(
            self.drive1_path,
            self.drive2_path,
            self.logger,
            force_rescan=False,
            dry_run=False,
        )

        # Verify result
        assert result is True

        # Verify logging calls were made
        assert self.logger.info.called
        # Verify synchronizer was called
        mock_synchronizer.sync_drives.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
