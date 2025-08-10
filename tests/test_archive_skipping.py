"""
Tests for archive directory skipping functionality
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


class TestArchiveSkipping:
    """Test that archive directory is properly skipped during processing"""
    
    def test_skips_files_in_archive_directory(self, temp_dir, logger):
        """Test that files inside the archive directory are skipped"""
        # Setup config
        archive_dir = temp_dir / "archive"
        config = Config(
            output_dir=archive_dir,
            extensions=['jpg'],
            dry_run=False,
            copy_mode=False,
            verify_checksums=True
        )
        
        organizer = PhotoOrganizer(config, logger)
        
        # Create some test files outside archive
        test_file1 = temp_dir / "photo1.jpg"
        test_file2 = temp_dir / "photo2.jpg"
        test_file1.write_text("fake photo 1")
        test_file2.write_text("fake photo 2")
        
        # Create the archive directory structure manually
        archive_subdir = archive_dir / "2023" / "2023_12"
        archive_subdir.mkdir(parents=True, exist_ok=True)
        
        # Put a file inside the archive directory
        archive_file = archive_subdir / "2023-12-25_14-30-45.jpg"
        archive_file.write_text("archived photo")
        
        # Mock creation dates
        creation_date1 = datetime(2023, 12, 25, 14, 30, 45)
        creation_date2 = datetime(2023, 12, 26, 15, 45, 30)
        
        def mock_get_creation_date(file_path):
            if file_path.name == "photo1.jpg":
                return creation_date1
            elif file_path.name == "photo2.jpg":
                return creation_date2
            else:
                return creation_date1  # Default for archive file
        
        organizer.metadata_extractor.get_creation_date = mock_get_creation_date
        
        # Process the directory
        results = organizer.process_directory(temp_dir)
        
        # Verify results
        assert results['processed'] == 2, "Should process both non-archive files"
        assert results['errors'] == 0, "Should have no errors"
        
        # Verify the archive file was not processed
        # The archive file should still exist in its original location
        assert archive_file.exists(), "Archive file should not be moved/deleted"
        assert archive_file.read_text() == "archived photo", "Archive file should be unchanged"
        
        # Verify the non-archive files were processed
        expected_file1 = archive_dir / "2023" / "2023_12" / "2023-12-25_14-30-45_001.jpg"  # Should get suffix due to duplicate name
        expected_file2 = archive_dir / "2023" / "2023_12" / "2023-12-26_15-45-30.jpg"
        
        # At least one of the files should have been processed
        processed_files = list(archive_dir.rglob("*.jpg"))
        assert len(processed_files) >= 2, f"Should have at least 2 files in archive, found: {processed_files}"
        
    def test_is_inside_archive_dir_method(self, temp_dir, logger):
        """Test the _is_inside_archive_dir helper method directly"""
        config = Config(output_dir=temp_dir / "archive")
        organizer = PhotoOrganizer(config, logger)
        
        # Create test paths
        archive_path = (temp_dir / "archive").resolve()
        archive_path.mkdir(exist_ok=True)
        
        # File inside archive
        inside_file = archive_path / "subdir" / "file.jpg"
        inside_file.parent.mkdir(parents=True, exist_ok=True)
        inside_file.touch()
        
        # File outside archive
        outside_file = temp_dir / "outside.jpg"
        outside_file.touch()
        
        # Test the method
        assert organizer._is_inside_archive_dir(inside_file.resolve(), archive_path) is True
        assert organizer._is_inside_archive_dir(outside_file.resolve(), archive_path) is False
        
    def test_skips_archive_in_subdirectory_scan(self, temp_dir, logger):
        """Test that recursive scanning properly skips archive directory"""
        # Create a complex directory structure
        subdir = temp_dir / "photos" / "2023"
        subdir.mkdir(parents=True)
        
        archive_dir = temp_dir / "archive"
        
        config = Config(
            output_dir=archive_dir,
            extensions=['jpg'],
            dry_run=True,  # Use dry run to avoid actual file operations
            copy_mode=False
        )
        
        organizer = PhotoOrganizer(config, logger)
        
        # Create files in various locations
        files = {
            temp_dir / "root.jpg": "root photo",
            subdir / "sub.jpg": "sub photo", 
            temp_dir / "archive" / "2023" / "2023_12" / "archived.jpg": "archived photo"
        }
        
        for file_path, content in files.items():
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        
        # Mock creation date
        organizer.metadata_extractor.get_creation_date = lambda x: datetime(2023, 12, 25, 14, 30, 45)
        
        # Process directory
        results = organizer.process_directory(temp_dir)
        
        # Should only process the non-archive files (2 files: root.jpg and sub.jpg)
        # In dry run mode, processed count reflects files that would be processed
        assert results['processed'] == 2, f"Expected 2 files to be processed, got {results['processed']}"
        assert results['errors'] == 0, "Should have no errors"
        
    def test_archive_skipping_with_relative_paths(self, temp_dir, logger):
        """Test archive skipping works with relative paths"""
        # Change to temp directory to test relative paths
        original_cwd = Path.cwd()
        os.chdir(temp_dir)
        
        try:
            config = Config(
                output_dir=Path("my_archive"),  # Relative path
                extensions=['jpg'],
                dry_run=True
            )
            
            organizer = PhotoOrganizer(config, logger)
            
            # Create files
            test_file = Path("test.jpg")
            test_file.write_text("test content")
            
            archive_file = Path("my_archive/2023/2023_12/existing.jpg")
            archive_file.parent.mkdir(parents=True, exist_ok=True)
            archive_file.write_text("archive content")
            
            # Mock creation date
            organizer.metadata_extractor.get_creation_date = lambda x: datetime(2023, 12, 25, 14, 30, 45)
            
            # Process current directory
            results = organizer.process_directory(Path("."))
            
            # Should process only the non-archive file
            assert results['processed'] == 1, "Should process only the test file"
            assert results['errors'] == 0, "Should have no errors"
            
        finally:
            os.chdir(original_cwd)
            
    def test_no_infinite_loops_with_archive_scanning(self, temp_dir, logger):
        """Test that processing the same directory multiple times doesn't cause issues"""
        archive_dir = temp_dir / "archive"
        config = Config(
            output_dir=archive_dir,
            extensions=['jpg'],
            dry_run=False,
            copy_mode=True  # Use copy mode to keep originals
        )
        
        organizer = PhotoOrganizer(config, logger)
        
        # Create a test file
        test_file = temp_dir / "test.jpg"
        test_file.write_text("test photo content")
        
        # Mock creation date
        organizer.metadata_extractor.get_creation_date = lambda x: datetime(2023, 12, 25, 14, 30, 45)
        
        # Process directory first time
        results1 = organizer.process_directory(temp_dir)
        assert results1['processed'] == 1, "First run should process 1 file"
        
        # Process directory second time
        results2 = organizer.process_directory(temp_dir)
        assert results2['processed'] == 0, "Second run should process 0 files (already processed)"
        assert results2['duplicates'] == 1, "Second run should detect 1 duplicate/already processed"
        
        # Process directory third time
        results3 = organizer.process_directory(temp_dir)
        assert results3['processed'] == 0, "Third run should process 0 files"
        assert results3['duplicates'] == 1, "Third run should detect 1 duplicate/already processed"
        
        # Verify only expected files exist
        archive_files = list(archive_dir.rglob("*.jpg"))
        assert len(archive_files) == 1, f"Should have exactly 1 file in archive, found: {archive_files}"
        
        # Original file should still exist (copy mode)
        assert test_file.exists(), "Original file should still exist in copy mode"
        
    def test_deeply_nested_archive_structure(self, temp_dir, logger):
        """Test archive skipping with deeply nested archive structures"""
        archive_dir = temp_dir / "photos" / "organized" / "archive"
        config = Config(
            output_dir=archive_dir,
            extensions=['jpg'],
            dry_run=True
        )
        
        organizer = PhotoOrganizer(config, logger)
        
        # Create files at various nesting levels
        files_to_create = [
            temp_dir / "root.jpg",
            temp_dir / "photos" / "level1.jpg",
            temp_dir / "photos" / "subfolder" / "level2.jpg",
            archive_dir / "2023" / "2023_01" / "archived1.jpg",
            archive_dir / "2023" / "2023_02" / "subfolder" / "archived2.jpg",
            archive_dir / "2024" / "2024_01" / "archived3.jpg"
        ]
        
        for file_path in files_to_create:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"content for {file_path.name}")
        
        # Mock creation date
        organizer.metadata_extractor.get_creation_date = lambda x: datetime(2023, 12, 25, 14, 30, 45)
        
        # Process the root directory
        results = organizer.process_directory(temp_dir)
        
        # Should process only the 3 non-archive files
        assert results['processed'] == 3, f"Should process 3 non-archive files, got {results['processed']}"
        assert results['errors'] == 0, "Should have no errors"
        
    def test_archive_skipping_case_insensitive_extensions(self, temp_dir, logger):
        """Test that archive skipping works with case-insensitive extensions"""
        archive_dir = temp_dir / "archive"
        config = Config(
            output_dir=archive_dir,
            extensions=['jpg', 'JPG', 'jpeg', 'JPEG'],
            dry_run=True
        )
        
        organizer = PhotoOrganizer(config, logger)
        
        # Create files with various extensions
        files = [
            temp_dir / "test1.jpg",
            temp_dir / "test2.JPG", 
            temp_dir / "test3.jpeg",
            temp_dir / "test4.JPEG",
            archive_dir / "2023" / "2023_12" / "archived1.jpg",
            archive_dir / "2023" / "2023_12" / "archived2.JPG",
            archive_dir / "2023" / "2023_12" / "archived3.jpeg",
            archive_dir / "2023" / "2023_12" / "archived4.JPEG"
        ]
        
        for file_path in files:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f"content for {file_path.name}")
        
        # Mock creation date
        organizer.metadata_extractor.get_creation_date = lambda x: datetime(2023, 12, 25, 14, 30, 45)
        
        # Process directory
        results = organizer.process_directory(temp_dir)
        
        # Should process only the 4 non-archive files
        assert results['processed'] == 4, f"Should process 4 non-archive files, got {results['processed']}"
        assert results['errors'] == 0, "Should have no errors"