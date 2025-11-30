"""
Replit Object Storage helper for Python.
Uses Replit's sidecar endpoint for credential management and presigned URLs.
"""
import os
import json
import requests
from datetime import datetime
from uuid import uuid4
from typing import Optional, Tuple
from urllib.parse import urlparse

REPLIT_SIDECAR_ENDPOINT = "http://127.0.0.1:1106"

class ObjectStorageError(Exception):
    """Custom exception for object storage operations."""
    pass


class ObjectStorageClient:
    """Python client for Replit Object Storage using the sidecar API."""
    
    def __init__(self):
        self._private_dir = os.environ.get("PRIVATE_OBJECT_DIR", "")
        self._public_paths = os.environ.get("PUBLIC_OBJECT_SEARCH_PATHS", "")
    
    def get_private_prefix(self) -> str:
        """Get the private object directory path."""
        if not self._private_dir:
            raise ObjectStorageError(
                "PRIVATE_OBJECT_DIR not set. Create a bucket in Object Storage tool."
            )
        return self._private_dir
    
    def get_public_prefixes(self) -> list:
        """Get list of public object search paths."""
        if not self._public_paths:
            return []
        return [p.strip() for p in self._public_paths.split(",") if p.strip()]
    
    def _sign_url(self, bucket_name: str, object_name: str, method: str, ttl_sec: int = 900) -> str:
        """Sign a URL for object access using the sidecar API."""
        request_body = {
            "bucket_name": bucket_name,
            "object_name": object_name,
            "method": method,
            "expires_at": datetime.utcnow().isoformat() + "Z"
        }
        
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_sec)
        request_body["expires_at"] = expires_at.isoformat() + "Z"
        
        try:
            response = requests.post(
                f"{REPLIT_SIDECAR_ENDPOINT}/object-storage/signed-object-url",
                json=request_body,
                timeout=10
            )
            if not response.ok:
                raise ObjectStorageError(
                    f"Failed to sign URL: {response.status_code} - {response.text}"
                )
            data = response.json()
            return data.get("signed_url", "")
        except requests.exceptions.RequestException as e:
            raise ObjectStorageError(f"Sidecar request failed: {e}")
    
    def _parse_object_path(self, path: str) -> Tuple[str, str]:
        """Parse a path into bucket name and object name."""
        if not path.startswith("/"):
            path = "/" + path
        parts = path.split("/")
        if len(parts) < 3:
            raise ObjectStorageError(f"Invalid path format: {path}")
        bucket_name = parts[1]
        object_name = "/".join(parts[2:])
        return bucket_name, object_name
    
    def generate_upload_url(self, object_key: str, ttl_sec: int = 900) -> str:
        """Generate a presigned PUT URL for uploading a file."""
        private_dir = self.get_private_prefix()
        full_path = f"{private_dir}/{object_key}".replace("//", "/")
        bucket_name, object_name = self._parse_object_path(full_path)
        return self._sign_url(bucket_name, object_name, "PUT", ttl_sec)
    
    def generate_download_url(self, object_key: str, ttl_sec: int = 3600) -> str:
        """Generate a presigned GET URL for downloading a file."""
        if object_key.startswith("/objects/"):
            private_dir = self.get_private_prefix()
            if not private_dir.endswith("/"):
                private_dir += "/"
            entity_id = object_key[9:]
            full_path = f"{private_dir}{entity_id}"
        elif object_key.startswith("https://"):
            parsed = urlparse(object_key)
            full_path = parsed.path
        else:
            private_dir = self.get_private_prefix()
            full_path = f"{private_dir}/{object_key}".replace("//", "/")
        
        bucket_name, object_name = self._parse_object_path(full_path)
        return self._sign_url(bucket_name, object_name, "GET", ttl_sec)
    
    def delete_object(self, object_key: str) -> bool:
        """Delete an object from storage."""
        try:
            if object_key.startswith("/objects/"):
                private_dir = self.get_private_prefix()
                if not private_dir.endswith("/"):
                    private_dir += "/"
                entity_id = object_key[9:]
                full_path = f"{private_dir}{entity_id}"
            else:
                private_dir = self.get_private_prefix()
                full_path = f"{private_dir}/{object_key}".replace("//", "/")
            
            bucket_name, object_name = self._parse_object_path(full_path)
            delete_url = self._sign_url(bucket_name, object_name, "DELETE", 60)
            
            response = requests.delete(delete_url, timeout=30)
            return response.ok or response.status_code == 404
        except Exception as e:
            print(f"Error deleting object {object_key}: {e}")
            return False
    
    def normalize_path(self, raw_url: str) -> str:
        """Normalize a signed URL or full path to a canonical /objects/... path."""
        if not raw_url:
            return ""
        
        if raw_url.startswith("/objects/"):
            return raw_url
        
        private_dir = self.get_private_prefix()
        if not private_dir.endswith("/"):
            private_dir += "/"
        
        if raw_url.startswith("https://storage.googleapis.com/"):
            parsed = urlparse(raw_url)
            path = parsed.path
            if path.startswith(private_dir):
                entity_id = path[len(private_dir):]
                return f"/objects/{entity_id}"
        
        if raw_url.startswith(private_dir):
            entity_id = raw_url[len(private_dir):]
            return f"/objects/{entity_id}"
        
        return raw_url
    
    def generate_object_key(self, enrollment_id: int, doc_type: str, filename: str) -> str:
        """Generate a unique object key for a document."""
        ext = os.path.splitext(filename)[1] if filename else ""
        unique_id = uuid4().hex[:12]
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")[:50]
        return f"enrollments/{enrollment_id}/{doc_type}/{unique_id}_{safe_filename}"
    
    def upload_file(self, file_bytes: bytes, object_key: str, content_type: str = "application/octet-stream") -> str:
        """Upload file bytes to object storage and return the normalized path."""
        upload_url = self.generate_upload_url(object_key, ttl_sec=300)
        
        response = requests.put(
            upload_url,
            data=file_bytes,
            headers={"Content-Type": content_type},
            timeout=120
        )
        
        if not response.ok:
            raise ObjectStorageError(
                f"Upload failed: {response.status_code} - {response.text}"
            )
        
        return f"/objects/{object_key}"
    
    def download_file(self, object_path: str) -> bytes:
        """Download file bytes from object storage."""
        download_url = self.generate_download_url(object_path, ttl_sec=300)
        
        response = requests.get(download_url, timeout=120)
        
        if not response.ok:
            raise ObjectStorageError(
                f"Download failed: {response.status_code}"
            )
        
        return response.content
    
    def file_exists(self, object_path: str) -> bool:
        """Check if a file exists in object storage."""
        try:
            if object_path.startswith("/objects/"):
                private_dir = self.get_private_prefix()
                if not private_dir.endswith("/"):
                    private_dir += "/"
                entity_id = object_path[9:]
                full_path = f"{private_dir}{entity_id}"
            else:
                private_dir = self.get_private_prefix()
                full_path = f"{private_dir}/{object_path}".replace("//", "/")
            
            bucket_name, object_name = self._parse_object_path(full_path)
            head_url = self._sign_url(bucket_name, object_name, "HEAD", 60)
            
            response = requests.head(head_url, timeout=10)
            return response.ok
        except Exception:
            return False


_client = None

def get_client() -> ObjectStorageClient:
    """Get or create the singleton object storage client."""
    global _client
    if _client is None:
        _client = ObjectStorageClient()
    return _client


def is_object_storage_configured() -> bool:
    """Check if object storage environment variables are configured."""
    return bool(os.environ.get("PRIVATE_OBJECT_DIR"))
