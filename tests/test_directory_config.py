"""Tests for directory configuration management"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open
from datetime import datetime

from photo_organizer.directory_config import (
    BackupDriveConfig,
    GooglePhotosConfig,
    DirectoryConfig,
    DirectoryConfigManager,
)


class TestBackupDriveConfig:
    """Test BackupDriveConfig dataclass"""
    
    def test_backup_drive_config_creation(self):
        """Test creating a basic backup drive config"""
        config = BackupDriveConfig(
            label="Test Drive",
            uuid="1234-5678",
            mount_path="/media/drive1"
        )
        
        assert config.label == "Test Drive"
        assert config.uuid == "1234-5678"
        assert config.mount_path == Path("/media/drive1")
        assert config.target_path == ""
        assert config.enabled is True
        assert config.verify_sync is True
    
    def test_backup_drive_config_defaults(self):
        """Test backup drive config with default values"""
        config = BackupDriveConfig(label="Test Drive")
        
        assert config.label == "Test Drive"
        assert config.uuid is None
        assert config.mount_path is None
        assert config.target_path == ""
        assert config.enabled is True
        assert config.verify_sync is True
    
    def test_backup_drive_config_post_init_string_path(self):
        """Test that string mount_path is converted to Path"""
        config = BackupDriveConfig(
            label="Test Drive",
            mount_path="/media/drive1"
        )
        
        assert isinstance(config.mount_path, Path)
        assert config.mount_path == Path("/media/drive1")
    
    def test_backup_drive_config_post_init_none_path(self):
        """Test that None mount_path remains None"""
        config = BackupDriveConfig(
            label="Test Drive",
            mount_path=None
        )
        
        assert config.mount_path is None


class TestGooglePhotosConfig:
    """Test GooglePhotosConfig dataclass"""
    
    def test_google_photos_config_creation(self):
        """Test creating a basic Google Photos config"""
        config = GooglePhotosConfig(
            account_email="test@gmail.com",
            credentials_file="/path/to/creds.json",
            enabled=True
        )
        
        assert config.account_email == "test@gmail.com"
        assert config.credentials_file == "/path/to/creds.json"
        assert config.enabled is True
        assert config.upload_quality == "original"
        assert config.create_albums_automatically is True
        assert config.group_by == "month"
    
    def test_google_photos_config_defaults(self):
        """Test Google Photos config with default values"""
        config = GooglePhotosConfig()
        
        assert config.account_email == ""
        assert config.credentials_file is None
        assert config.enabled is False
        assert config.upload_quality == "original"
        assert config.create_albums_automatically is True
        assert config.group_by == "month"
        assert config.album_name_pattern == "{year}_{month:02d}"
        assert config.album_description_pattern == "Photos from {year}-{month:02d}"


class TestDirectoryConfig:
    """Test DirectoryConfig dataclass"""
    
    def test_directory_config_creation(self):
        """Test creating a basic directory config"""
        config = DirectoryConfig(
            source_path="/path/to/photos",
            output_dir="/path/to/archive"
        )
        
        assert config.source_path == Path("/path/to/photos")
        assert config.output_dir == Path("/path/to/archive")
        assert config.organize_into_folders is True
        assert config.folder_pattern == "{year}/{year}_{month:02d}"
        assert config.rename_pattern == "{year}-{month:02d}-{day:02d}_{hour:02d}-{minute:02d}-{second:02d}"
    
    def test_directory_config_post_init_string_paths(self):
        """Test that string paths are converted to Path objects"""
        config = DirectoryConfig(source_path="/path/to/photos")
        
        assert isinstance(config.source_path, Path)
        assert isinstance(config.output_dir, Path)
        assert config.source_path == Path("/path/to/photos")
        assert config.output_dir == Path("archive")
    
    def test_directory_config_post_init_defaults(self):
        """Test that default values are set correctly"""
        config = DirectoryConfig(source_path="/path/to/photos")
        
        assert config.extensions == ['jpg', 'jpeg', 'png', 'tiff', 'raw', 'cr2', 'nef', 'arw']
        assert isinstance(config.backup_drives, list)
        assert len(config.backup_drives) == 0
        assert isinstance(config.google_photos, GooglePhotosConfig)
        assert config.created_at is not None
        assert config.updated_at is not None
    
    def test_directory_config_timestamps(self):
        """Test that timestamps are set correctly"""
        before = datetime.now()
        config = DirectoryConfig(source_path="/path/to/photos")
        after = datetime.now()
        
        created = datetime.fromisoformat(config.created_at)
        updated = datetime.fromisoformat(config.updated_at)
        
        assert before <= created <= after
        assert before <= updated <= after
        assert config.created_at == config.updated_at


class TestDirectoryConfigManager:
    """Test DirectoryConfigManager class"""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def config_manager(self, temp_config_dir):
        """Create a config manager with temporary directory"""
        return DirectoryConfigManager(config_dir=temp_config_dir)
    
    def test_config_manager_initialization(self, temp_config_dir):
        """Test config manager initialization"""
        manager = DirectoryConfigManager(config_dir=temp_config_dir)
        
        assert manager.config_dir == temp_config_dir
        assert manager.index_file == temp_config_dir / "directory_index.json"
        assert isinstance(manager._directory_configs, dict)
        assert len(manager._directory_configs) == 0
    
    def test_config_manager_default_config_dir(self):
        """Test config manager uses default config directory"""
        with patch('photo_organizer.directory_config.Path.home') as mock_home:
            mock_home.return_value = Path("/home/test")
            manager = DirectoryConfigManager()
            
            expected_dir = Path("/home/test/.config/photo-organizer")
            assert manager.config_dir == expected_dir
    
    def test_load_index_no_file(self, config_manager):
        """Test loading index when no index file exists"""
        config_manager._load_index()
        
        assert len(config_manager._directory_configs) == 0
    
    def test_load_index_with_file(self, config_manager):
        """Test loading index from existing file"""
        # Create a mock index file
        index_data = {
            "directories": {
                "/path/to/photos": "photos_config.json"
            }
        }
        
        # Mock the config file content
        config_data = {
            "source_path": "/path/to/photos",
            "output_dir": "archive",
            "extensions": ["jpg", "png"],
            "backup_drives": [],
            "google_photos": {}
        }
        
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.return_value.__enter__.return_value.read.side_effect = [
                json.dumps(index_data),
                json.dumps(config_data)
            ]
            
            config_manager._load_index()
            
            # Should have loaded one config
            assert len(config_manager._directory_configs) == 1
            assert "/path/to/photos" in config_manager._directory_configs
    
    def test_load_index_corrupted_file(self, config_manager):
        """Test loading index with corrupted JSON"""
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.return_value.__enter__.return_value.read.return_value = "invalid json"
            
            # Should not raise exception, just log warning
            config_manager._load_index()
            
            assert len(config_manager._directory_configs) == 0
    
    def test_load_config_file_success(self, config_manager):
        """Test loading a single config file successfully"""
        config_data = {
            "source_path": "/path/to/photos",
            "output_dir": "archive",
            "extensions": ["jpg", "png"],
            "backup_drives": [
                {
                    "label": "Test Drive",
                    "uuid": "1234-5678",
                    "target_path": "/backup/archive"
                }
            ],
            "google_photos": {
                "enabled": True,
                "account_email": "test@gmail.com"
            }
        }
        
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(config_data)
            
            config_path = Path("/tmp/test_config.json")
            config = config_manager._load_config_file(config_path)
            
            assert config is not None
            assert config.source_path == Path("/path/to/photos")
            assert config.output_dir == Path("archive")
            assert len(config.backup_drives) == 1
            assert config.backup_drives[0].label == "Test Drive"
            assert config.google_photos.enabled is True
    
    def test_load_config_file_failure(self, config_manager):
        """Test loading config file with invalid JSON"""
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.return_value.__enter__.return_value.read.return_value = "invalid json"
            
            config_path = Path("/tmp/test_config.json")
            config = config_manager._load_config_file(config_path)
            
            assert config is None
    
    def test_dict_to_config(self, config_manager):
        """Test converting dictionary to DirectoryConfig"""
        data = {
            "source_path": "/path/to/photos",
            "output_dir": "archive",
            "extensions": ["jpg", "png"],
            "backup_drives": [
                {
                    "label": "Test Drive",
                    "uuid": "1234-5678"
                }
            ],
            "google_photos": {
                "enabled": True,
                "account_email": "test@gmail.com"
            }
        }
        
        config = config_manager._dict_to_config(data)
        
        assert isinstance(config, DirectoryConfig)
        assert config.source_path == Path("/path/to/photos")
        assert len(config.backup_drives) == 1
        assert config.backup_drives[0].label == "Test Drive"
        assert config.google_photos.enabled is True
    
    def test_save_index(self, config_manager):
        """Test saving the directory index"""
        # Add a test config
        test_config = DirectoryConfig(source_path="/test/path")
        config_manager._directory_configs["/test/path"] = test_config
        
        with patch('builtins.open', mock_open()) as mock_file:
            config_manager._save_index()
            
            # Verify the file was opened for writing
            mock_file.assert_called_once()
            mock_file.return_value.__enter__.return_value.write.assert_called_once()
    
    def test_path_to_filename(self, config_manager):
        """Test converting paths to safe filenames"""
        # Test various path formats
        assert config_manager._path_to_filename("/home/user/photos") == "home_user_photos"
        assert config_manager._path_to_filename("C:\\Users\\Photos") == "C_Users_Photos"
        assert config_manager._path_to_filename("~/Pictures/My Photos") == "home_Pictures_My_Photos"
        assert config_manager._path_to_filename("/path/with:colon") == "path_with_colon"
    
    def test_get_config_existing(self, config_manager):
        """Test getting existing configuration"""
        test_config = DirectoryConfig(source_path="/test/path")
        config_manager._directory_configs["/test/path"] = test_config
        
        result = config_manager.get_config("/test/path")
        assert result == test_config
    
    def test_get_config_nonexistent(self, config_manager):
        """Test getting non-existent configuration"""
        result = config_manager.get_config("/nonexistent/path")
        assert result is None
    
    def test_set_config_success(self, config_manager):
        """Test setting configuration successfully"""
        test_config = DirectoryConfig(source_path="/test/path")
        
        with patch('builtins.open', mock_open()) as mock_file:
            success = config_manager.set_config(test_config)
            
            assert success is True
            assert "/test/path" in config_manager._directory_configs
            assert config_manager._directory_configs["/test/path"] == test_config
    
    def test_set_config_failure(self, config_manager):
        """Test setting configuration with error"""
        test_config = DirectoryConfig(source_path="/test/path")
        
        with patch('builtins.open', side_effect=Exception("Permission denied")):
            success = config_manager.set_config(test_config)
            
            assert success is False
    
    def test_config_to_dict(self, config_manager):
        """Test converting DirectoryConfig to dictionary"""
        test_config = DirectoryConfig(
            source_path="/test/path",
            output_dir="/test/archive"
        )
        test_config.backup_drives = [
            BackupDriveConfig(
                label="Test Drive",
                mount_path="/media/drive1"
            )
        ]
        
        config_dict = config_manager._config_to_dict(test_config)
        
        assert isinstance(config_dict, dict)
        assert config_dict["source_path"] == "/test/path"
        assert config_dict["output_dir"] == "/test/archive"
        assert len(config_dict["backup_drives"]) == 1
        assert config_dict["backup_drives"][0]["mount_path"] == "/media/drive1"
    
    def test_list_configurations(self, config_manager):
        """Test listing all configurations"""
        # Add some test configs
        config1 = DirectoryConfig(source_path="/path1")
        config2 = DirectoryConfig(source_path="/path2")
        config_manager._directory_configs["/path1"] = config1
        config_manager._directory_configs["/path2"] = config2
        
        result = config_manager.list_configurations()
        
        assert len(result) == 2
        assert "/path1" in result
        assert "/path2" in result
        assert result["/path1"] == config1
        assert result["/path2"] == config2
    
    def test_remove_config_success(self, config_manager):
        """Test removing configuration successfully"""
        test_config = DirectoryConfig(source_path="/test/path")
        config_manager._directory_configs["/test/path"] = test_config
        
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.unlink'):
                success = config_manager.remove_config("/test/path")
                
                assert success is True
                assert "/test/path" not in config_manager._directory_configs
    
    def test_remove_config_nonexistent(self, config_manager):
        """Test removing non-existent configuration"""
        success = config_manager.remove_config("/nonexistent/path")
        assert success is False
    
    def test_remove_config_failure(self, config_manager):
        """Test removing configuration with error"""
        test_config = DirectoryConfig(source_path="/test/path")
        config_manager._directory_configs["/test/path"] = test_config
        
        with patch('pathlib.Path.unlink', side_effect=Exception("Permission denied")):
            success = config_manager.remove_config("/test/path")
            
            assert success is False
    
    def test_create_example_configs(self, config_manager):
        """Test creating example configurations"""
        examples = config_manager.create_example_configs()
        
        assert "phone_backup" in examples
        assert "son_camera" in examples
        
        phone_config = examples["phone_backup"]
        assert phone_config.source_path == Path("~/Dropbox/Camera_Downloads")
        assert len(phone_config.backup_drives) == 2
        assert phone_config.google_photos.enabled is True
        
        son_config = examples["son_camera"]
        assert son_config.source_path == Path("~/Pictures/Son_camera")
        assert son_config.google_photos.album_name_pattern == "Son_{year}_{month:02d}"

