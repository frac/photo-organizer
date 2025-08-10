"""EXIF metadata extraction using Python libraries"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    import exifread
    EXIFREAD_AVAILABLE = True
except ImportError:
    EXIFREAD_AVAILABLE = False


class MetadataExtractor:
    """Extract metadata from image files using available Python libraries"""
    
    def __init__(self):
        self.logger = logging.getLogger('photo_organizer.metadata')
        
        if not PILLOW_AVAILABLE and not EXIFREAD_AVAILABLE:
            self.logger.warning("Neither Pillow nor exifread available. Install one for EXIF support.")
    
    def get_creation_date(self, file_path: Path) -> Optional[datetime]:
        """Extract creation date from image EXIF data"""
        
        # Try multiple methods in order of preference
        methods = []
        
        if PILLOW_AVAILABLE:
            methods.append(self._get_date_with_pillow)
        
        if EXIFREAD_AVAILABLE:
            methods.append(self._get_date_with_exifread)
        
        # Fallback to file system date
        methods.append(self._get_date_from_filesystem)
        
        for method in methods:
            try:
                date = method(file_path)
                if date:
                    self.logger.debug(f"Got creation date for {file_path.name}: {date}")
                    return date
            except Exception as e:
                self.logger.debug(f"Method {method.__name__} failed for {file_path}: {e}")
                continue
        
        self.logger.warning(f"Could not extract creation date from {file_path}")
        return None
    
    def _get_date_with_pillow(self, file_path: Path) -> Optional[datetime]:
        """Extract date using Pillow/PIL"""
        if not PILLOW_AVAILABLE:
            return None
        
        try:
            with Image.open(file_path) as img:
                exifdata = img.getexif()
                
                # Common EXIF date tags in order of preference
                date_tags = [
                    'DateTimeOriginal',    # Camera shooting date
                    'DateTimeDigitized',   # Date digitized
                    'DateTime'             # Date modified
                ]
                
                for tag_name in date_tags:
                    for tag_id, tag_value in exifdata.items():
                        tag_key = TAGS.get(tag_id, tag_id)
                        if tag_key == tag_name and tag_value:
                            return self._parse_exif_date(tag_value)
                            
        except Exception as e:
            self.logger.debug(f"Pillow extraction failed: {e}")
        
        return None
    
    def _get_date_with_exifread(self, file_path: Path) -> Optional[datetime]:
        """Extract date using exifread library"""
        if not EXIFREAD_AVAILABLE:
            return None
        
        try:
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f)
                
                # Common EXIF date tags in order of preference
                date_tag_names = [
                    'EXIF DateTimeOriginal',
                    'EXIF DateTimeDigitized', 
                    'Image DateTime'
                ]
                
                for tag_name in date_tag_names:
                    if tag_name in tags and str(tags[tag_name]):
                        return self._parse_exif_date(str(tags[tag_name]))
                        
        except Exception as e:
            self.logger.debug(f"ExifRead extraction failed: {e}")
        
        return None
    
    def _get_date_from_filesystem(self, file_path: Path) -> Optional[datetime]:
        """Fallback: use file modification time"""
        try:
            # Use modification time as last resort
            mtime = file_path.stat().st_mtime
            return datetime.fromtimestamp(mtime)
        except Exception as e:
            self.logger.debug(f"Filesystem date extraction failed: {e}")
            return None
    
    def _parse_exif_date(self, date_string: str) -> Optional[datetime]:
        """Parse EXIF date string to datetime object"""
        try:
            # EXIF date format: "2023:12:25 14:30:45"
            date_string = str(date_string).strip()
            
            # Common EXIF date formats
            formats = [
                '%Y:%m:%d %H:%M:%S',  # Standard EXIF format
                '%Y-%m-%d %H:%M:%S',  # Alternative format
                '%Y:%m:%d',           # Date only
                '%Y-%m-%d'            # Date only alternative
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_string, fmt)
                except ValueError:
                    continue
            
            self.logger.debug(f"Could not parse date string: {date_string}")
            return None
            
        except Exception as e:
            self.logger.debug(f"Date parsing error: {e}")
            return None