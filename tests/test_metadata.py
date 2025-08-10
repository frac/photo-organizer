"""Tests for metadata extraction"""

from datetime import datetime
from pathlib import Path
import pytest

from photo_organizer.metadata import MetadataExtractor


@pytest.fixture
def metadata_extractor():
    return MetadataExtractor()


def test_get_creation_date_from_filesystem(metadata_extractor, sample_jpg):
    """Test getting creation date from filesystem when EXIF unavailable"""
    date = metadata_extractor.get_creation_date(sample_jpg)
    
    # Should get some date (from filesystem)
    assert isinstance(date, datetime)
    assert date.year >= 2020  # Reasonable sanity check


def test_parse_exif_date_standard_format(metadata_extractor):
    """Test parsing standard EXIF date format"""
    date_string = "2023:12:25 14:30:45"
    expected = datetime(2023, 12, 25, 14, 30, 45)
    
    result = metadata_extractor._parse_exif_date(date_string)
    assert result == expected


def test_parse_exif_date_alternative_format(metadata_extractor):
    """Test parsing alternative date formats"""
    test_cases = [
        ("2023-12-25 14:30:45", datetime(2023, 12, 25, 14, 30, 45)),
        ("2023:12:25", datetime(2023, 12, 25)),
        ("2023-12-25", datetime(2023, 12, 25))
    ]
    
    for date_string, expected in test_cases:
        result = metadata_extractor._parse_exif_date(date_string)
        assert result == expected


def test_parse_exif_date_invalid_format(metadata_extractor):
    """Test handling of invalid date formats"""
    invalid_dates = [
        "invalid date",
        "2023/12/25",  # Unsupported format
        "",
        None
    ]
    
    for invalid_date in invalid_dates:
        result = metadata_extractor._parse_exif_date(str(invalid_date))
        assert result is None


def test_get_creation_date_nonexistent_file(metadata_extractor):
    """Test handling of nonexistent files"""
    nonexistent = Path("does_not_exist.jpg")
    result = metadata_extractor.get_creation_date(nonexistent)
    assert result is None