"""
Critical safety tests - these must NEVER fail!
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import os

from photo_organizer.organizer import PhotoOrganizer
from photo_organizer.config import Config
from photo_organizer.logger import setup_logger


class TestCriticalSafety:
    """Critical safety tests that must never fail"""
    
    def test_shutil_move_dangerous_behavior(self, temp_dir, logger):
        """
        CRITICAL: Files must NEVER be deleted if the move/copy operation fails.
        
        This test simulates a scenario where the target directory creation or
        file operation fails AFTER the source file would be deleted by shutil.move().
        The original file MUST still exist.
        """
        # Create test setup
        config = Config(
            output_dir=temp_dir / "archive",
            extensions=['jpg'],
            dry_run=False,
            copy_mode=False,  # Use move mode to test the dangerous operation
            verify_checksums=True
        )
        
        organizer = PhotoOrganizer(config, logger)
        
        # Create a test file with known content
        test_file = temp_dir / "test_photo.jpg"
        original_content = "fake photo content for safety test"
        test_file.write_text(original_content)
        
        # Verify file exists and get its checksum
        assert test_file.exists()
        original_checksum = organizer._get_file_checksum(test_file)
        
        # Create a scenario where the target directory cannot be created
        # by creating a file with the same name as the target directory
        target_year_dir = config.output_dir / "2023"
        target_month_dir = target_year_dir / "2023_12"
        
        # Create the year directory as a file (not a directory) to cause failure
        config.output_dir.mkdir(parents=True, exist_ok=True)
        target_year_dir.write_text("this is a file, not a directory")
        
        # Mock the creation date to ensure predictable target path
        creation_date = datetime(2023, 12, 25, 14, 30, 45)
        
        # Monkey patch the metadata extractor to return our test date
        def mock_get_creation_date(file_path):
            return creation_date
        
        organizer.metadata_extractor.get_creation_date = mock_get_creation_date
        
        # Now attempt to process the file - this should fail
        # because target_year_dir is a file, not a directory
        result = organizer.process_file(test_file)
        
        # CRITICAL ASSERTION: The original file must still exist!
        assert test_file.exists(), f"CRITICAL SAFETY FAILURE: Original file {test_file} was deleted!"
        
        # CRITICAL ASSERTION: The original file content must be intact!
        assert test_file.read_text() == original_content, "CRITICAL SAFETY FAILURE: Original file content was corrupted!"
        
        # CRITICAL ASSERTION: The checksum must match original
        current_checksum = organizer._get_file_checksum(test_file)
        assert current_checksum == original_checksum, "CRITICAL SAFETY FAILURE: File checksum changed!"
        
        # The operation should have failed
        assert not result['success'], "Operation should have failed due to directory creation issue"
        
        # Clean up the blocking file for next test
        target_year_dir.unlink()
    
    def test_never_delete_files_on_permission_error(self, temp_dir, logger):
        """
        CRITICAL: Files must never be deleted if target location is not writable
        """
        config = Config(
            output_dir=temp_dir / "archive",
            extensions=['jpg'],
            dry_run=False,
            copy_mode=False,  # Move mode
            verify_checksums=True
        )
        
        organizer = PhotoOrganizer(config, logger)
        
        # Create test file
        test_file = temp_dir / "permission_test.jpg"
        original_content = "content for permission test"
        test_file.write_text(original_content)
        original_checksum = organizer._get_file_checksum(test_file)
        
        # Create target structure but make it read-only
        target_dir = config.output_dir / "2023" / "2023_12"
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Remove write permissions on target directory
        os.chmod(target_dir, 0o444)  # Read-only
        
        # Mock creation date
        creation_date = datetime(2023, 12, 25, 14, 30, 45)
        organizer.metadata_extractor.get_creation_date = lambda x: creation_date
        
        try:
            # Attempt to process - should fail due to permissions
            result = organizer.process_file(test_file)
            
            # CRITICAL: Original file must still exist
            assert test_file.exists(), "CRITICAL: Original file was deleted despite permission error!"
            assert test_file.read_text() == original_content, "CRITICAL: Original file content changed!"
            assert organizer._get_file_checksum(test_file) == original_checksum, "CRITICAL: File checksum changed!"
            
            # Operation should have failed
            assert not result['success'], "Operation should have failed due to permission error"
            
        finally:
            # Restore permissions for cleanup
            os.chmod(target_dir, 0o755)
    
    def test_never_delete_on_checksum_verification_failure(self, temp_dir, logger):
        """
        CRITICAL: If checksum verification fails, original file must not be deleted
        """
        config = Config(
            output_dir=temp_dir / "archive",
            extensions=['jpg'],
            dry_run=False,
            copy_mode=False,  # Move mode - most dangerous
            verify_checksums=True
        )
        
        organizer = PhotoOrganizer(config, logger)
        
        # Create test file
        test_file = temp_dir / "checksum_test.jpg"
        original_content = "content for checksum test"
        test_file.write_text(original_content)
        original_checksum = organizer._get_file_checksum(test_file)
        
        # Mock creation date
        creation_date = datetime(2023, 12, 25, 14, 30, 45)
        organizer.metadata_extractor.get_creation_date = lambda x: creation_date
        
        # Mock the checksum verification to simulate corruption
        original_get_checksum = organizer._get_file_checksum
        call_count = 0
        
        def mock_checksum(file_path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call (before operation) - return correct checksum
                return original_get_checksum(file_path)
            else:
                # Second call (verification) - return wrong checksum to simulate corruption
                return "corrupted_checksum"
        
        organizer._get_file_checksum = mock_checksum
        
        # Process file - should fail verification
        result = organizer.process_file(test_file)
        
        # CRITICAL: Original file must still exist even though verification failed
        assert test_file.exists(), "CRITICAL: Original file deleted despite checksum verification failure!"
        assert test_file.read_text() == original_content, "CRITICAL: Original file content changed!"
        
        # Operation should have failed
        assert not result['success'], "Operation should have failed due to checksum mismatch"
    
    def test_atomic_operations_no_partial_state(self, temp_dir, logger):
        """
        CRITICAL: Operations must be atomic - no partial state where file is moved but not verified
        """
        config = Config(
            output_dir=temp_dir / "archive",
            extensions=['jpg'],
            dry_run=False,
            copy_mode=False,
            verify_checksums=True
        )
        
        organizer = PhotoOrganizer(config, logger)
        
        # Create test file
        test_file = temp_dir / "atomic_test.jpg"
        test_file.write_text("atomic test content")
        
        # Mock creation date
        creation_date = datetime(2023, 12, 25, 14, 30, 45)
        organizer.metadata_extractor.get_creation_date = lambda x: creation_date
        
        # Expected target path
        expected_target = config.output_dir / "2023" / "2023_12" / "2023-12-25_14-30-45.jpg"
        
        # Process successfully first to verify normal operation
        result = organizer.process_file(test_file)
        
        if result['success']:
            # File should be moved to target
            assert not test_file.exists(), "Source file should be gone after successful move"
            assert expected_target.exists(), "Target file should exist after successful move"
            assert expected_target.read_text() == "atomic test content"
        else:
            # If it failed, original should still be there
            assert test_file.exists(), "CRITICAL: Source file missing after failed operation!"
            assert not expected_target.exists(), "Target file should not exist after failed operation"