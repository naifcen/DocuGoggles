# file_search/cache/content_cache.py
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import os

class ContentCache:
    """
    JSON-based cache for storing extracted file contents between sessions
    and preparing for future Meilisearch integration
    """
    
    def __init__(self, cache_dir=None):
        """Initialize the content cache"""
        if cache_dir is None:
            home_dir = Path.home()
            self.cache_dir = home_dir / ".file_search_cache"
        else:
            self.cache_dir = Path(cache_dir)
            
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        
        self.index_file = self.cache_dir / "cache_index.json"
        
        self.docs_dir = self.cache_dir / "documents"
        self.docs_dir.mkdir(exist_ok=True)
        
        self.cache_index = self._load_index()
        self.content_cache = {}
    
    def _generate_document_id(self, file_path: str) -> str:
        """Generate a consistent document ID from file path"""
        return hashlib.md5(file_path.encode('utf-8')).hexdigest()
    
    def _get_document_path(self, doc_id: str) -> Path:
        """Get the path to a cached document JSON file"""
        return self.docs_dir / f"{doc_id}.json"
    
    def _load_index(self) -> Dict[str, Any]:
        """Load the cache index from disk"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading cache index: {e}")
                return {"files": {}, "last_updated": None}
        return {"files": {}, "last_updated": None}
    
    def _save_index(self):
        """Save the cache index to disk"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache_index, f, ensure_ascii=False, indent=2)
    
    def load_cache(self) -> Dict[str, Any]:
        """Load content cache for all files in the index"""
        self.content_cache = {}
        
        for file_path, file_info in self.cache_index.get("files", {}).items():
            doc_id = file_info.get("doc_id")
            if not doc_id:
                continue
                
            doc_path = self._get_document_path(doc_id)
            if doc_path.exists():
                try:
                    with open(doc_path, 'r', encoding='utf-8') as f:
                        document = json.load(f)
                        self.content_cache[file_path] = {
                            'content': document.get('content', ''),
                            'metadata': document.get('metadata', {})
                        }
                except Exception as e:
                    print(f"Error loading document {doc_id}: {e}")
        
        return self.content_cache
    
    def save_document(self, file_path: str, content: Dict[str, Any]):
        """Save a single document to the cache"""
        file_path = str(Path(file_path).resolve())
        doc_id = self._generate_document_id(file_path)
        
        # Prepare document in a format for future Meilisearch integration
        metadata = content.get('metadata', {})
        
        for key, value in metadata.items():
            if isinstance(value, datetime):
                metadata[key] = value.isoformat()
        
        document = {
            'id': doc_id,
            'file_path': file_path,
            'content': content.get('content', ''),
            'metadata': metadata
        }
        
        # Save JSON file
        doc_path = self._get_document_path(doc_id)
        with open(doc_path, 'w', encoding='utf-8') as f:
            json.dump(document, f, ensure_ascii=False)
        
        # Update index
        if "files" not in self.cache_index:
            self.cache_index["files"] = {}
            
        self.cache_index["files"][file_path] = {
            "doc_id": doc_id,
            "mtime": os.path.getmtime(file_path) if os.path.exists(file_path) else 0,
            "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            "cached_at": datetime.now().isoformat(),
            "extension": metadata.get("extension", ""),
            "name": metadata.get("name", "")
        }
    
    def save_cache(self, content_cache: Dict[str, Any]):
        """Save all content cache to disk"""
        self.content_cache = content_cache
        
        for file_path, content in content_cache.items():
            self.save_document(file_path, content)
        
        self.cache_index["last_updated"] = datetime.now().isoformat()
        self._save_index()
    
    def is_file_cached(self, file_path: str) -> bool:
        """Check if a file is cached and up to date"""
        file_path = str(Path(file_path).resolve())
        file_info = self.cache_index.get("files", {}).get(file_path)
        
        if not file_info:
            return False
            
        # Check if file has been modified since last cached (will use hash in future)
        try:
            if not os.path.exists(file_path):
                return False
                
            mtime = os.path.getmtime(file_path)
            cached_mtime = file_info.get("mtime")
            
            # Also verify the document exists
            doc_id = file_info.get("doc_id")
            if not doc_id:
                return False
                
            doc_path = self._get_document_path(doc_id)
            if not doc_path.exists():
                return False
            
            return cached_mtime is not None and mtime <= cached_mtime
        except Exception:
            return False
    
    def update_file_index(self, file_path: str, metadata: Dict[str, Any]):
        """Update the cache index for a file"""
        file_path = str(Path(file_path).resolve())
        
        if os.path.exists(file_path):
            if "files" not in self.cache_index:
                self.cache_index["files"] = {}
            
            if file_path not in self.cache_index["files"]:
                doc_id = self._generate_document_id(file_path)
            else:
                doc_id = self.cache_index["files"][file_path].get("doc_id", self._generate_document_id(file_path))
            
            self.cache_index["files"][file_path] = {
                "doc_id": doc_id,
                "mtime": os.path.getmtime(file_path),
                "size": os.path.getsize(file_path),
                "cached_at": datetime.now().isoformat(),
                "extension": metadata.get("extension", ""),
                "name": metadata.get("name", "")
            }
            self._save_index()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache"""
        file_count = len(self.cache_index.get("files", {}))
        
        total_size = 0
        for doc_id in [info.get("doc_id") for info in self.cache_index.get("files", {}).values() if info.get("doc_id")]:
            doc_path = self._get_document_path(doc_id)
            if doc_path.exists():
                total_size += os.path.getsize(doc_path)
        
        if self.index_file.exists():
            total_size += os.path.getsize(self.index_file)
        
        extensions = {}
        for file_info in self.cache_index.get("files", {}).values():
            ext = file_info.get("extension", "unknown")
            extensions[ext] = extensions.get(ext, 0) + 1
            
        return {
            "file_count": file_count,
            "total_size": total_size,
            "extensions": extensions,
            "last_updated": self.cache_index.get("last_updated")
        }
    
    def clear_cache(self):
        """Clear the entire content cache"""
        for doc_file in self.docs_dir.glob("*.json"):
            try:
                doc_file.unlink()
            except Exception as e:
                print(f"Error deleting {doc_file}: {e}")
        
        if self.index_file.exists():
            self.index_file.unlink()
            
        self.cache_index = {"files": {}, "last_updated": None}
        self.content_cache = {}
        
        self._save_index()
    
    def export_for_meilisearch(self) -> List[Dict[str, Any]]:
        """
        Export cache data in a format ready for Meilisearch indexing
        """
        documents = []
        
        for file_path, file_info in self.cache_index.get("files", {}).items():
            doc_id = file_info.get("doc_id")
            if not doc_id:
                continue
            
            doc_path = self._get_document_path(doc_id)
            if not doc_path.exists():
                continue
                
            try:
                with open(doc_path, 'r', encoding='utf-8') as f:
                    document = json.load(f)
                    
                    meilisearch_doc = {
                        'id': doc_id,
                        'file_path': file_path,
                        'file_name': file_info.get("name", ""),
                        'extension': file_info.get("extension", ""),
                        'content': document.get('content', ''),
                        'size': file_info.get("size", 0),
                        'modified': file_info.get("mtime", 0),
                        'cached_at': file_info.get("cached_at", "")
                    }
                    
                    # Add any additional metadata
                    metadata = document.get('metadata', {})
                    for key, value in metadata.items():
                        if key not in meilisearch_doc:
                            meilisearch_doc[key] = value
                    
                    documents.append(meilisearch_doc)
            except Exception as e:
                print(f"Error processing document {doc_id} for export: {e}")
        
        return documents