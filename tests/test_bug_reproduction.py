"""
Test that reproduces the file deletion bug
"""

import shutil
from datetime import datetime

from photo_organizer.organizer import PhotoOrganizer
from photo_organizer.config import Config


def test_current_implementation_deletes_files_on_error(temp_dir, logger):
    """
    This test demonstrates the current dangerous behavior where
    shutil.move() deletes the source file even when the operation fails.

    This test should FAIL with the current implementation, proving the bug exists.
    Once we fix it to use safe operations, this test should PASS.
    """
    # Setup config for move operation (not copy)
    config = Config(
        output_dir=temp_dir / "archive",
        extensions=['jpg'],
        dry_run=False,
        copy_mode=False,  # This is the dangerous mode
        verify_checksums=True
    )

    organizer = PhotoOrganizer(config, logger)

    # Create a test file
    test_file = temp_dir / "doomed_file.jpg"
    original_content = "this file should never be deleted!"
    test_file.write_text(original_content)

    # Verify it exists
    assert test_file.exists()
    original_size = test_file.stat().st_size

    # Mock the creation date extraction to return a valid date
    creation_date = datetime(2023, 12, 25, 14, 30, 45)
    organizer.metadata_extractor.get_creation_date = lambda x: creation_date

    # Now let's create a scenario where the copy operation will fail
    # We'll monkey-patch shutil.copy2 to simulate a failure AFTER it runs
    original_copy2 = shutil.copy2

    def failing_copy2(src, dst):
        # First do the copy (this should work)
        original_copy2(src, dst)
        # Then fail - this simulates a failure after copy but before we can verify
        raise OSError("Simulated failure after copy but before verification")

    # Replace shutil.copy2 with our failing version
    shutil.copy2 = failing_copy2

    try:
        # Process the file - this will fail and delete the original
        result = organizer.process_file(test_file)

        # The operation should have failed
        assert not result['success'], "Operation should have failed"

        # CRITICAL SAFETY CHECK: The original file should still exist!
        # This will FAIL with current implementation, proving the bug
        assert test_file.exists(), (
            "CRITICAL BUG: Original file was deleted even though operation failed! "
            f"File {test_file} no longer exists. This proves the current implementation "
            "is unsafe and can lose user data."
        )

        # If the file still exists, verify its content is intact
        if test_file.exists():
            assert test_file.read_text() == original_content
            assert test_file.stat().st_size == original_size

    finally:
        # Restore original shutil.copy2
        shutil.copy2 = original_copy2


def test_safe_operation_should_never_delete_source_on_failure(temp_dir, logger):
    """
    This test shows how the safe operations should behave -
    never delete source until destination is confirmed.

    This test should PASS once we implement safe operations.
    """
    from photo_organizer.file_utils import FileOperations

    config = Config(verify_checksums=True)
    file_ops = FileOperations(config, logger)

    # Create test file
    source_file = temp_dir / "safe_test.jpg"
    source_file.write_text("safe operation test")

    # Create impossible target (file instead of directory)
    target_dir = temp_dir / "target"
    target_dir.write_text("this is a file, not a directory")
    target_file = target_dir / "should_fail.jpg"  # This will fail

    # Attempt safe move - should fail but preserve source
    success = file_ops.safe_move(source_file, target_file, verify=True)

    # Operation should fail
    assert not success, "Operation should have failed"

    # Source file should still exist and be intact
    assert source_file.exists(), "Source file should still exist after failed safe operation"
    assert source_file.read_text() == "safe operation test"

    # Target should not exist
    assert not target_file.exists(), "Target file should not exist after failed operation"
