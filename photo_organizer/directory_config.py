"""Per-directory configuration management for photo organizer"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Union
from datetime import datetime


@dataclass
class BackupDriveConfig:
    """Configuration for a backup drive"""
    
    # Drive identification
    label: str  # Human-readable name like "Backup_HDD_1"
    uuid: Optional[str] = None  # Drive UUID for reliable identification
    mount_path: Optional[Path] = None  # Where it's currently mounted
    
    # Backup settings
    target_path: str = ""  # Path on the drive like "/Pictures/archive" 
    enabled: bool = True
    verify_sync: bool = True  # Check if drive has all files
    
    def __post_init__(self):
        if isinstance(self.mount_path, str):
            self.mount_path = Path(self.mount_path) if self.mount_path else None


@dataclass
class GooglePhotosConfig:
    """Configuration for Google Photos integration"""
    
    # Account settings
    account_email: str = ""
    credentials_file: Optional[str] = None  # Path to OAuth credentials
    
    # Album settings
    album_name_pattern: str = "{year}_{month:02d}"  # e.g. "2025_08"
    album_description_pattern: str = "Photos from {year}-{month:02d}"
    
    # Upload settings
    enabled: bool = False
    upload_quality: str = "original"  # "original" or "high"
    create_albums_automatically: bool = True
    
    # Organization
    group_by: str = "month"  # "month", "year", "day"


@dataclass
class DirectoryConfig:
    """Configuration for a specific directory"""
    
    # Basic settings
    source_path: Path
    output_dir: Path = Path("archive")
    
    # Processing settings  
    extensions: List[str] = None
    rename_pattern: str = "{year}-{month:02d}-{day:02d}_{hour:02d}-{minute:02d}-{second:02d}"
    organize_into_folders: bool = True
    folder_pattern: str = "{year}/{year}_{month:02d}"
    
    # Backup drives
    backup_drives: List[BackupDriveConfig] = None
    
    # Google Photos
    google_photos: GooglePhotosConfig = None
    
    # Metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def __post_init__(self):
        if isinstance(self.source_path, str):
            self.source_path = Path(self.source_path)
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
            
        if self.extensions is None:
            self.extensions = ['jpg', 'jpeg', 'png', 'tiff', 'raw', 'cr2', 'nef', 'arw']
            
        if self.backup_drives is None:
            self.backup_drives = []
            
        if self.google_photos is None:
            self.google_photos = GooglePhotosConfig()
            
        # Set timestamps
        now = datetime.now().isoformat()
        if self.created_at is None:
            self.created_at = now
        self.updated_at = now


class DirectoryConfigManager:
    """Manages per-directory configurations"""
    
    def __init__(self, config_dir: Path = None):
        """Initialize config manager
        
        Args:
            config_dir: Directory to store config files. Defaults to ~/.config/photo-organizer/
        """
        if config_dir is None:
            config_dir = Path.home() / ".config" / "photo-organizer"
        
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Global config file for directory mappings
        self.index_file = self.config_dir / "directory_index.json"
        
        # Load existing configurations
        self._directory_configs: Dict[str, DirectoryConfig] = {}
        self._load_index()
    
    def _load_index(self):
        """Load the directory index and all configurations"""
        if not self.index_file.exists():
            return
            
        try:
            with open(self.index_file, 'r') as f:
                index_data = json.load(f)
                
            for source_path_str, config_file in index_data.get("directories", {}).items():
                config_path = self.config_dir / config_file
                if config_path.exists():
                    config = self._load_config_file(config_path)
                    if config:
                        self._directory_configs[source_path_str] = config
                        
        except Exception as e:
            print(f"Warning: Could not load config index: {e}")
    
    def _load_config_file(self, config_path: Path) -> Optional[DirectoryConfig]:
        """Load a single config file"""
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            
            # Convert dict back to dataclass
            config = self._dict_to_config(data)
            return config
            
        except Exception as e:
            print(f"Warning: Could not load config {config_path}: {e}")
            return None
    
    def _dict_to_config(self, data: dict) -> DirectoryConfig:
        """Convert dictionary to DirectoryConfig with nested objects"""
        # Handle backup drives
        backup_drives = []
        for drive_data in data.get("backup_drives", []):
            backup_drives.append(BackupDriveConfig(**drive_data))
        
        # Handle Google Photos config
        google_photos_data = data.get("google_photos", {})
        google_photos = GooglePhotosConfig(**google_photos_data)
        
        # Create main config
        config_data = data.copy()
        config_data["backup_drives"] = backup_drives
        config_data["google_photos"] = google_photos
        
        return DirectoryConfig(**config_data)
    
    def _save_index(self):
        """Save the directory index"""
        index_data = {
            "directories": {
                str(source_path): f"{self._path_to_filename(source_path)}.json"
                for source_path in self._directory_configs.keys()
            },
            "updated_at": datetime.now().isoformat()
        }
        
        with open(self.index_file, 'w') as f:
            json.dump(index_data, f, indent=2)
    
    def _path_to_filename(self, path: Union[str, Path]) -> str:
        """Convert a path to a safe filename"""
        path_str = str(path)
        # Replace path separators and problematic characters
        safe_name = path_str.replace("/", "_").replace("\\", "_").replace(":", "_")
        safe_name = safe_name.replace(" ", "_").replace("~", "home")
        return safe_name.strip("_")
    
    def get_config(self, source_path: Union[str, Path]) -> Optional[DirectoryConfig]:
        """Get configuration for a directory"""
        source_path_str = str(Path(source_path).resolve())
        return self._directory_configs.get(source_path_str)
    
    def set_config(self, config: DirectoryConfig) -> bool:
        """Save configuration for a directory"""
        try:
            source_path_str = str(config.source_path.resolve())
            config.updated_at = datetime.now().isoformat()
            
            # Save to memory
            self._directory_configs[source_path_str] = config
            
            # Save config file
            config_filename = f"{self._path_to_filename(source_path_str)}.json"
            config_path = self.config_dir / config_filename
            
            with open(config_path, 'w') as f:
                # Convert to dict for JSON serialization
                config_dict = self._config_to_dict(config)
                json.dump(config_dict, f, indent=2)
            
            # Update index
            self._save_index()
            return True
            
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def _config_to_dict(self, config: DirectoryConfig) -> dict:
        """Convert DirectoryConfig to dict for JSON serialization"""
        config_dict = asdict(config)
        
        # Convert Path objects to strings
        config_dict["source_path"] = str(config.source_path)
        config_dict["output_dir"] = str(config.output_dir)
        
        # Handle backup drives mount_path
        for drive in config_dict["backup_drives"]:
            if drive["mount_path"]:
                drive["mount_path"] = str(drive["mount_path"])
        
        return config_dict
    
    def list_configurations(self) -> Dict[str, DirectoryConfig]:
        """List all configured directories"""
        return self._directory_configs.copy()
    
    def remove_config(self, source_path: Union[str, Path]) -> bool:
        """Remove configuration for a directory"""
        try:
            source_path_str = str(Path(source_path).resolve())
            
            if source_path_str in self._directory_configs:
                # Remove from memory
                del self._directory_configs[source_path_str]
                
                # Remove config file
                config_filename = f"{self._path_to_filename(source_path_str)}.json"
                config_path = self.config_dir / config_filename
                if config_path.exists():
                    config_path.unlink()
                
                # Update index
                self._save_index()
                return True
            
            return False
            
        except Exception as e:
            print(f"Error removing config: {e}")
            return False
    
    def create_example_configs(self) -> Dict[str, DirectoryConfig]:
        """Create example configurations for documentation/testing"""
        examples = {}
        
        # Example 1: Phone backup to Google Photos
        phone_backup = DirectoryConfig(
            source_path=Path("~/Dropbox/Camera_Downloads"),
            backup_drives=[
                BackupDriveConfig(
                    label="Primary_HDD",
                    target_path="/Pictures/archive",
                    uuid="1234-5678-9012",
                ),
                BackupDriveConfig(
                    label="Secondary_HDD", 
                    target_path="/Pictures/archive",
                    uuid="2345-6789-0123",
                )
            ],
            google_photos=GooglePhotosConfig(
                enabled=True,
                account_email="your@gmail.com",
                album_name_pattern="Phone_{year}_{month:02d}",
                album_description_pattern="Phone photos from {year}-{month:02d}"
            )
        )
        examples["phone_backup"] = phone_backup
        
        # Example 2: Son's camera with different settings
        son_camera = DirectoryConfig(
            source_path=Path("~/Pictures/Son_camera"),
            backup_drives=[
                BackupDriveConfig(
                    label="Primary_HDD",
                    target_path="/Pictures/Son/archive",
                    uuid="1234-5678-9012",
                ),
                BackupDriveConfig(
                    label="Secondary_HDD",
                    target_path="/Pictures/Son/archive", 
                    uuid="2345-6789-0123",
                )
            ],
            google_photos=GooglePhotosConfig(
                enabled=True,
                account_email="your@gmail.com",
                album_name_pattern="Son_{year}_{month:02d}",
                album_description_pattern="Son's photos from {year}-{month:02d}"
            )
        )
        examples["son_camera"] = son_camera
        
        return examples