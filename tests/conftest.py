"""Pytest configuration and fixtures for photo organizer tests"""

import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import pytest
import logging

from photo_organizer.config import Config
from photo_organizer.logger import setup_logger


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_config(temp_dir):
    """Create a sample configuration for tests"""
    return Config(
        output_dir=temp_dir / "archive",
        extensions=['jpg', 'jpeg', 'png'],
        dry_run=False,
        copy_mode=False,
        verify_checksums=True
    )


@pytest.fixture
def logger():
    """Create logger for tests"""
    return setup_logger(level=logging.DEBUG)


@pytest.fixture
def sample_jpg(temp_dir):
    """Create a sample JPG file with basic EXIF data"""
    from PIL import Image
    
    # Create a simple test image
    img = Image.new('RGB', (100, 100), color='red')
    
    # Add fake EXIF data (this is limited without proper EXIF writing)
    file_path = temp_dir / "test_photo.jpg"
    img.save(file_path, "JPEG")
    
    # Set file timestamp to a known date for testing
    import os
    test_time = datetime(2023, 12, 25, 14, 30, 45).timestamp()
    os.utime(file_path, (test_time, test_time))
    
    return file_path


@pytest.fixture
def sample_files(temp_dir):
    """Create multiple sample files for testing"""
    files = []
    
    # Create test files with different timestamps
    test_dates = [
        datetime(2023, 1, 15, 10, 30, 0),
        datetime(2023, 6, 20, 16, 45, 30),  
        datetime(2024, 3, 10, 9, 15, 20)
    ]
    
    for i, test_date in enumerate(test_dates):
        file_path = temp_dir / f"photo_{i+1}.jpg"
        file_path.write_text(f"fake image content {i}")
        
        # Set file timestamp
        import os
        timestamp = test_date.timestamp()
        os.utime(file_path, (timestamp, timestamp))
        files.append(file_path)
    
    return files