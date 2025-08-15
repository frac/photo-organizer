"""Tests for configuration management"""

from pathlib import Path

from photo_organizer.config import Config


def test_config_defaults():
    """Test default configuration values"""
    config = Config()

    assert config.output_dir == Path("archive")
    assert 'jpg' in config.extensions
    assert 'jpeg' in config.extensions
    assert not config.dry_run
    assert not config.copy_mode
    assert config.verify_checksums
    assert config.max_duplicate_suffix == 999


def test_config_custom_values():
    """Test configuration with custom values"""
    config = Config(
        output_dir=Path("custom_archive"),
        extensions=['png', 'tiff'],
        dry_run=True,
        copy_mode=True
    )

    assert config.output_dir == Path("custom_archive")
    assert config.extensions == ['png', 'tiff']
    assert config.dry_run
    assert config.copy_mode


def test_config_extension_normalization():
    """Test that extensions are normalized to lowercase without dots"""
    config = Config(extensions=['.JPG', 'JPEG', '.png', 'TIFF'])

    expected = ['jpg', 'jpeg', 'png', 'tiff']
    assert config.extensions == expected


def test_is_supported_extension():
    """Test file extension support checking"""
    config = Config(extensions=['jpg', 'png'])

    assert config.is_supported_extension(Path("photo.jpg"))
    assert config.is_supported_extension(Path("photo.JPG"))
    assert config.is_supported_extension(Path("photo.png"))
    assert not config.is_supported_extension(Path("photo.gif"))
    assert not config.is_supported_extension(Path("document.txt"))


def test_config_string_path_conversion():
    """Test that string paths are converted to Path objects"""
    config = Config(output_dir="string/path")

    assert isinstance(config.output_dir, Path)
    assert config.output_dir == Path("string/path")
