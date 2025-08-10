"""Configuration management for photo organizer"""

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Config:
    """Configuration for photo organizer"""
    
    output_dir: Path = Path("archive")
    extensions: List[str] = None
    dry_run: bool = False
    copy_mode: bool = False  # If True, copy instead of move
    create_backups: bool = False
    verify_checksums: bool = True
    max_duplicate_suffix: int = 999  # photo_001.jpg, photo_002.jpg, etc.
    
    def __post_init__(self):
        if self.extensions is None:
            self.extensions = ['jpg', 'jpeg', 'png', 'tiff', 'raw', 'cr2', 'nef', 'arw']
        
        # Normalize extensions to lowercase
        self.extensions = [ext.lower().lstrip('.') for ext in self.extensions]
        
        # Ensure output_dir is a Path object
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
    
    def is_supported_extension(self, file_path: Path) -> bool:
        """Check if file extension is supported"""
        return file_path.suffix.lower().lstrip('.') in self.extensions