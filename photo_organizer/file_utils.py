"""File operation utilities with safety checks"""

import shutil
import hashlib
from pathlib import Path
from typing import Optional
import logging

from .config import Config


class FileOperations:
    """Safe file operations with verification"""
    
    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
    
    def safe_copy(self, source: Path, target: Path, verify: bool = True) -> bool:
        """Safely copy file with optional verification"""
        try:
            # Ensure target directory exists
            target.parent.mkdir(parents=True, exist_ok=True)
            
            if self.config.dry_run:
                self.logger.info(f"DRY RUN: Would copy {source} -> {target}")
                return True
            
            # Get original checksum if verification is enabled
            original_checksum = None
            if verify:
                original_checksum = self._calculate_checksum(source)
            
            # Perform copy with metadata preservation
            shutil.copy2(source, target)
            
            # Verify copy if requested
            if verify and original_checksum:
                new_checksum = self._calculate_checksum(target)
                if original_checksum != new_checksum:
                    # Remove corrupted copy
                    target.unlink(missing_ok=True)
                    raise ValueError(f"Copy verification failed: checksums don't match")
            
            self.logger.debug(f"Successfully copied: {source} -> {target}")
            return True
            
        except Exception as e:
            self.logger.error(f"Copy failed {source} -> {target}: {e}")
            return False
    
    def safe_move(self, source: Path, target: Path, verify: bool = True) -> bool:
        """Safely move file with optional verification"""
        try:
            # Ensure target directory exists
            target.parent.mkdir(parents=True, exist_ok=True)
            
            if self.config.dry_run:
                self.logger.info(f"DRY RUN: Would move {source} -> {target}")
                return True
            
            # Get original checksum if verification is enabled
            original_checksum = None
            if verify:
                original_checksum = self._calculate_checksum(source)
            
            # ALWAYS use safe copy-then-delete approach for maximum safety
            # Never use shutil.move() which can delete source before ensuring target is safe
            
            # Copy to destination first
            shutil.copy2(source, target)
            
            # Verify copy if requested
            if verify and original_checksum:
                new_checksum = self._calculate_checksum(target)
                if original_checksum != new_checksum:
                    # Remove corrupted copy, keep original
                    target.unlink(missing_ok=True)
                    raise ValueError(f"Move verification failed: checksums don't match")
            
            # Only delete original after successful copy and verification
            source.unlink()
            
            self.logger.debug(f"Successfully moved: {source} -> {target}")
            return True
            
        except Exception as e:
            self.logger.error(f"Move failed {source} -> {target}: {e}")
            return False
    
    def safe_rename(self, source: Path, target: Path, verify: bool = True) -> bool:
        """Safely rename file in same directory with optional verification"""
        try:
            if self.config.dry_run:
                self.logger.info(f"DRY RUN: Would rename {source} -> {target}")
                return True
            
            # Get original checksum if verification is enabled
            original_checksum = None
            if verify:
                original_checksum = self._calculate_checksum(source)
            
            # Use Python's rename which is atomic on most filesystems
            source.rename(target)
            
            # Verify rename if requested
            if verify and original_checksum:
                new_checksum = self._calculate_checksum(target)
                if original_checksum != new_checksum:
                    # This shouldn't happen with atomic rename, but check anyway
                    raise ValueError(f"Rename verification failed: checksums don't match")
            
            self.logger.debug(f"Successfully renamed: {source} -> {target}")
            return True
            
        except Exception as e:
            self.logger.error(f"Rename failed {source} -> {target}: {e}")
            return False
    
    def _calculate_checksum(self, file_path: Path, algorithm: str = 'sha256') -> str:
        """Calculate file checksum"""
        if algorithm == 'sha256':
            hash_obj = hashlib.sha256()
        elif algorithm == 'md5':
            hash_obj = hashlib.md5()
        else:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")
        
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except Exception as e:
            self.logger.error(f"Checksum calculation failed for {file_path}: {e}")
            raise
    
    def verify_file_integrity(self, file_path: Path, expected_checksum: str, 
                            algorithm: str = 'sha256') -> bool:
        """Verify file integrity against expected checksum"""
        try:
            actual_checksum = self._calculate_checksum(file_path, algorithm)
            return actual_checksum == expected_checksum
        except Exception:
            return False
    
    def create_backup(self, file_path: Path, backup_dir: Optional[Path] = None) -> Optional[Path]:
        """Create backup of file"""
        if not self.config.create_backups:
            return None
        
        try:
            if backup_dir is None:
                backup_dir = file_path.parent / ".backups"
            
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{file_path.name}.backup"
            
            # Handle multiple backups
            counter = 1
            while backup_path.exists():
                backup_path = backup_dir / f"{file_path.name}.backup.{counter}"
                counter += 1
            
            shutil.copy2(file_path, backup_path)
            self.logger.debug(f"Created backup: {backup_path}")
            return backup_path
            
        except Exception as e:
            self.logger.error(f"Backup creation failed for {file_path}: {e}")
            return None