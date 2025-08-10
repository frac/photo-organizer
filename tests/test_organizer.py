"""Tests for the main organizer functionality - safety first!"""

import hashlib
from datetime import datetime
from pathlib import Path
import pytest
import sqlite3

from photo_organizer.organizer import PhotoOrganizer
from photo_organizer.config import Config


@pytest.fixture
def organizer(sample_config, logger):
    """Create organizer instance for testing"""
    return PhotoOrganizer(sample_config, logger)


def test_organizer_initialization(organizer, sample_config):
    """Test that organizer initializes correctly"""
    assert organizer.config == sample_config
    assert organizer.processed_files_db.exists()
    
    # Check database was created correctly
    conn = sqlite3.connect(organizer.processed_files_db)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert 'processed_files' in tables
    conn.close()


def test_get_file_checksum(organizer, sample_jpg):
    """Test checksum calculation"""
    checksum = organizer._get_file_checksum(sample_jpg)
    
    # Verify it's a valid SHA-256 hash
    assert len(checksum) == 64
    assert all(c in '0123456789abcdef' for c in checksum)
    
    # Should be consistent
    checksum2 = organizer._get_file_checksum(sample_jpg)
    assert checksum == checksum2


def test_is_already_processed_new_file(organizer, sample_jpg):
    """Test detection of new (unprocessed) file"""
    is_processed, target_path = organizer._is_already_processed(sample_jpg)
    
    assert not is_processed
    assert target_path is None


def test_mark_and_check_processed_file(organizer, sample_jpg, temp_dir):
    """Test marking file as processed and detecting it"""
    checksum = organizer._get_file_checksum(sample_jpg)
    target_path = temp_dir / "archive" / "processed.jpg"
    
    # Mark as processed
    organizer._mark_as_processed(sample_jpg, checksum, target_path)
    
    # Should now be detected as processed
    is_processed, stored_target = organizer._is_already_processed(sample_jpg)
    assert is_processed
    assert stored_target == str(target_path)


def test_generate_target_path(organizer):
    """Test target path generation"""
    original_path = Path("test_photo.jpg")
    creation_date = datetime(2023, 12, 25, 14, 30, 45)
    
    target_path = organizer._generate_target_path(original_path, creation_date)
    
    expected = organizer.config.output_dir / "2023" / "2023_12" / "2023-12-25_14-30-45.jpg"
    assert target_path == expected


def test_find_safe_target_path_no_conflict(organizer, temp_dir):
    """Test safe target path when no conflict exists"""
    target_path = temp_dir / "new_file.jpg"
    
    safe_path = organizer._find_safe_target_path(target_path)
    assert safe_path == target_path


def test_find_safe_target_path_with_conflict(organizer, temp_dir):
    """Test safe target path generation when conflict exists"""
    target_path = temp_dir / "existing_file.jpg"
    
    # Create conflicting file
    target_path.write_text("existing content")
    
    safe_path = organizer._find_safe_target_path(target_path)
    
    expected = temp_dir / "existing_file_001.jpg"
    assert safe_path == expected
    assert not safe_path.exists()  # Should be available


def test_handle_existing_file_no_conflict(organizer, sample_jpg, temp_dir):
    """Test handling when no existing file conflict"""
    target_path = temp_dir / "no_conflict.jpg"
    
    can_proceed, conflict_type = organizer._handle_existing_file(sample_jpg, target_path)
    
    assert can_proceed
    assert conflict_type == "no_conflict"


def test_handle_existing_file_duplicate_content(organizer, temp_dir):
    """Test detection of true duplicates (same content)"""
    # Create two files with identical content
    content = "identical content"
    source_path = temp_dir / "source.jpg"
    target_path = temp_dir / "target.jpg"
    
    source_path.write_text(content)
    target_path.write_text(content)
    
    can_proceed, conflict_type = organizer._handle_existing_file(source_path, target_path)
    
    assert not can_proceed
    assert conflict_type == "duplicate"


def test_handle_existing_file_name_conflict(organizer, temp_dir):
    """Test handling of name conflicts with different content"""
    source_path = temp_dir / "source.jpg"
    target_path = temp_dir / "target.jpg"
    
    source_path.write_text("source content")
    target_path.write_text("different content")
    
    can_proceed, conflict_type = organizer._handle_existing_file(source_path, target_path)
    
    assert can_proceed
    assert conflict_type == "name_conflict"


def test_is_in_archive_structure(organizer):
    """Test detection of files already in archive structure"""
    # Files in archive structure
    archive_files = [
        Path("archive/2023/2023-12/photo.jpg"),
        Path("some/path/2023/2023-12/another.jpg"),
        Path("2024/2024-01/test.jpg")
    ]
    
    for file_path in archive_files:
        assert organizer._is_in_archive_structure(file_path)
    
    # Files NOT in archive structure
    non_archive_files = [
        Path("random/photo.jpg"),
        Path("2023-photos/image.jpg"),
        Path("photo.jpg")
    ]
    
    for file_path in non_archive_files:
        assert not organizer._is_in_archive_structure(file_path)


def test_process_file_unsupported_extension(organizer, temp_dir):
    """Test processing file with unsupported extension"""
    txt_file = temp_dir / "document.txt"
    txt_file.write_text("not a photo")
    
    result = organizer.process_file(txt_file)
    
    assert not result['success']
    assert result['action'] == 'skipped'
    assert result['reason'] == 'unsupported_extension'


def test_process_file_already_in_archive(organizer, temp_dir):
    """Test processing file already in archive structure"""
    archive_dir = temp_dir / "2023" / "2023-12"
    archive_dir.mkdir(parents=True)
    
    archive_file = archive_dir / "photo.jpg"
    archive_file.write_text("photo content")
    
    result = organizer.process_file(archive_file)
    
    assert not result['success']
    assert result['reason'] == 'already_in_archive'


def test_process_file_dry_run_mode(organizer, sample_files, sample_config):
    """Test processing in dry run mode"""
    # Set dry run mode
    sample_config.dry_run = True
    
    result = organizer.process_file(sample_files[0])
    
    if result['success']:
        assert result['action'] == 'dry_run'
        # File should not have been moved
        assert sample_files[0].exists()


def test_process_directory_statistics(organizer, sample_files):
    """Test that process_directory returns correct statistics"""
    input_dir = sample_files[0].parent
    
    results = organizer.process_directory(input_dir)
    
    # Should have processed some files
    total_operations = results['processed'] + results['skipped'] + results['duplicates'] + results['errors']
    assert total_operations > 0
    
    # All counts should be non-negative
    for count in results.values():
        assert count >= 0


def test_safety_no_data_loss(organizer, sample_files, logger):
    """Critical test: ensure no data loss occurs during processing"""
    input_dir = sample_files[0].parent
    
    # Calculate checksums before processing
    original_checksums = {}
    for file_path in sample_files:
        if file_path.exists():
            original_checksums[file_path.name] = organizer._get_file_checksum(file_path)
    
    # Process directory
    results = organizer.process_directory(input_dir)
    
    # Verify no data was lost by checking all files still exist somewhere
    # and have correct checksums
    archive_files = list(organizer.config.output_dir.rglob("*.*"))
    
    for original_name, original_checksum in original_checksums.items():
        # Find the file in archive (may have new name)
        found = False
        for archive_file in archive_files:
            if archive_file.is_file():
                try:
                    archive_checksum = organizer._get_file_checksum(archive_file)
                    if archive_checksum == original_checksum:
                        found = True
                        logger.info(f"Verified: {original_name} -> {archive_file.name}")
                        break
                except Exception:
                    continue
        
        # If not found in archive, should still be in original location
        if not found:
            for original_file in sample_files:
                if original_file.name == original_name and original_file.exists():
                    current_checksum = organizer._get_file_checksum(original_file)
                    assert current_checksum == original_checksum, f"Data corruption detected in {original_name}"
                    found = True
                    break
        
        assert found, f"File lost during processing: {original_name}"