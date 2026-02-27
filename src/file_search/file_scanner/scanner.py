import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

class FileScanner:
    """
    A class to handle directory scanning and file collection.
    """
    def __init__(self):
        # No base directory needed if path is passed to scan_directory
        self.files: List[Path] = []

    def scan_directory(self, directory: str, recursive: bool = True) -> None:
        """
        Scan a directory for files and add them to the internal file list.
        
        Args:
            directory: Path to the directory to scan.
            recursive: If True, scan subdirectories recursively.
        """
        self.files = [] # Clear previous results before new scan
        path = Path(directory)
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {directory}")

        if recursive:
            pattern = "**/*" # Scan all subdirectories
        else:
            pattern = "*"   # Scan only the top-level directory
            
        for file_path in path.glob(pattern):
            if file_path.is_file():
                self.files.append(file_path)

    def get_files(self) -> List[Path]:
        """Return all scanned files."""
        return self.files.copy()

    def group_files_by_extension(self, supported_extensions: Optional[List[str]] = None) -> Dict[str, List[Dict]]:
        """Groups scanned files by their extension and gets metadata."""
        grouped_files: Dict[str, List[Dict]] = {}
        for file_path in self.files:
            extension = file_path.suffix.lower()
            if supported_extensions and extension not in supported_extensions:
                continue
            
            metadata = self._get_file_metadata(file_path)
            if extension not in grouped_files:
                grouped_files[extension] = []
            grouped_files[extension].append(metadata)
        return grouped_files

    def _get_file_metadata(self, file_path: Path) -> Dict[str, any]:
        """
        Collect metadata for a single file.
        Args:
            file_path: Path object pointing to the file
        Returns:
            Dictionary containing file metadata
        """
        stats = file_path.stat()
        return {
            'name': file_path.name,
            'path': str(file_path.absolute()),
            'size': stats.st_size,  # Size in bytes
            'created': datetime.fromtimestamp(stats.st_ctime),
            'modified': datetime.fromtimestamp(stats.st_mtime),
            'extension': file_path.suffix.lower(),
            'is_hidden': file_path.name.startswith('.'),
            'parent_dir': str(file_path.parent)
        }

    def get_directory_statistics(self) -> Dict[str, any]:
        """
        Get statistics about the scanned directory based on the internal file list.
        """
        file_count = len([f for f in self.files if f.is_file()])
        # Note: This approach doesn't track directories explicitly during the glob scan
        # We can estimate directories if needed, but the primary focus is files.
        dir_count = len(set(f.parent for f in self.files)) # Approximation
        total_size = sum(f.stat().st_size for f in self.files if f.is_file())
        extension_counts: Dict[str, int] = {}
        for f in self.files:
            if f.is_file():
                ext = f.suffix.lower()
                extension_counts[ext] = extension_counts.get(ext, 0) + 1

        return {
            'total_files': file_count,
            'total_directories': dir_count, # Approximation based on file paths
            'total_size': total_size,
            'extension_counts': extension_counts
        }