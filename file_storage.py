"""
File Storage module for BYOV Enrollment Engine.
Provides unified API for file operations that works with both local storage
and Replit Object Storage.
"""
import os
import io
import base64
import requests
from datetime import datetime
from uuid import uuid4
from typing import Optional, List, Tuple, Union
from PIL import Image

PRIVATE_OBJECT_DIR = os.environ.get("PRIVATE_OBJECT_DIR", "")
USE_OBJECT_STORAGE = bool(PRIVATE_OBJECT_DIR)

REPLIT_SIDECAR_ENDPOINT = "http://127.0.0.1:1106"


class FileStorageError(Exception):
    """Custom exception for file storage operations."""
    pass


def _sign_url(bucket_name: str, object_name: str, method: str, ttl_sec: int = 900) -> str:
    """Sign a URL for object access using the sidecar API."""
    from datetime import timedelta
    expires_at = datetime.utcnow() + timedelta(seconds=ttl_sec)
    
    request_body = {
        "bucket_name": bucket_name,
        "object_name": object_name,
        "method": method,
        "expires_at": expires_at.isoformat() + "Z"
    }
    
    try:
        response = requests.post(
            f"{REPLIT_SIDECAR_ENDPOINT}/object-storage/signed-object-url",
            json=request_body,
            timeout=10
        )
        if not response.ok:
            raise FileStorageError(
                f"Failed to sign URL: {response.status_code} - {response.text}"
            )
        data = response.json()
        return data.get("signed_url", "")
    except requests.exceptions.RequestException as e:
        raise FileStorageError(f"Sidecar request failed: {e}")


def _parse_object_path(path: str) -> Tuple[str, str]:
    """Parse a path into bucket name and object name."""
    if not path.startswith("/"):
        path = "/" + path
    parts = path.split("/")
    if len(parts) < 3:
        raise FileStorageError(f"Invalid path format: {path}")
    bucket_name = parts[1]
    object_name = "/".join(parts[2:])
    return bucket_name, object_name


def is_object_storage_path(path: str) -> bool:
    """Check if a path is an Object Storage path."""
    return path and path.startswith("/objects/")


def create_upload_folder(tech_id: str, record_id: str) -> str:
    """Create upload folder structure for enrollment files.
    
    Returns base path for local storage, or a key prefix for Object Storage.
    """
    import re
    safe_tech_id = re.sub(r'[<>:"/\\|?*]', '_', tech_id).strip('. ') or 'unnamed'
    folder_name = f"{safe_tech_id}_{record_id}"
    
    if USE_OBJECT_STORAGE:
        return f"enrollments/{folder_name}"
    else:
        base_path = os.path.join("uploads", folder_name)
        os.makedirs(os.path.join(base_path, "vehicle"), exist_ok=True)
        os.makedirs(os.path.join(base_path, "insurance"), exist_ok=True)
        os.makedirs(os.path.join(base_path, "registration"), exist_ok=True)
        os.makedirs("pdfs", exist_ok=True)
        return base_path


def save_uploaded_files(uploaded_files, folder_path: str, prefix: str, compress: bool = True) -> List[str]:
    """Save uploaded files and return list of paths.
    
    Uses Object Storage if configured, otherwise local filesystem.
    For Object Storage, returns /objects/... paths.
    For local storage, returns file system paths.
    """
    file_paths = []
    
    for idx, uploaded_file in enumerate(uploaded_files, 1):
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        filename = f"{prefix}_{idx}{ext}"
        
        file_bytes = None
        content_type = "application/octet-stream"
        
        if compress and ext in ['.jpg', '.jpeg', '.png']:
            try:
                img = Image.open(uploaded_file)
                
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                max_size = 1200
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                buffer = io.BytesIO()
                img.save(buffer, 'JPEG', quality=75, optimize=True)
                file_bytes = buffer.getvalue()
                content_type = "image/jpeg"
                
            except Exception as e:
                print(f"Warning: Image compression failed for {filename}: {e}")
                uploaded_file.seek(0)
                file_bytes = uploaded_file.read()
        else:
            uploaded_file.seek(0)
            file_bytes = uploaded_file.read()
            
            if ext in ['.pdf']:
                content_type = "application/pdf"
            elif ext in ['.jpg', '.jpeg']:
                content_type = "image/jpeg"
            elif ext in ['.png']:
                content_type = "image/png"
        
        if USE_OBJECT_STORAGE:
            object_key = f"{folder_path}/{prefix}/{uuid4().hex[:8]}_{filename}"
            saved_path = _upload_to_object_storage(file_bytes, object_key, content_type)
        else:
            local_path = os.path.join(folder_path, filename)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(file_bytes)
            saved_path = local_path
        
        file_paths.append(saved_path)
    
    return file_paths


def save_pdf(pdf_bytes: bytes, filename: str, folder_path: str = "pdfs") -> str:
    """Save a PDF file and return the path."""
    if USE_OBJECT_STORAGE:
        object_key = f"pdfs/{uuid4().hex[:8]}_{filename}"
        return _upload_to_object_storage(pdf_bytes, object_key, "application/pdf")
    else:
        os.makedirs(folder_path, exist_ok=True)
        local_path = os.path.join(folder_path, filename)
        with open(local_path, 'wb') as f:
            f.write(pdf_bytes)
        return local_path


def _upload_to_object_storage(file_bytes: bytes, object_key: str, content_type: str) -> str:
    """Upload bytes to Object Storage and return normalized path."""
    if not PRIVATE_OBJECT_DIR:
        raise FileStorageError("Object Storage not configured")
    
    full_path = f"{PRIVATE_OBJECT_DIR}/{object_key}".replace("//", "/")
    bucket_name, object_name = _parse_object_path(full_path)
    
    upload_url = _sign_url(bucket_name, object_name, "PUT", 300)
    
    response = requests.put(
        upload_url,
        data=file_bytes,
        headers={"Content-Type": content_type},
        timeout=120
    )
    
    if not response.ok:
        raise FileStorageError(f"Upload failed: {response.status_code}")
    
    return f"/objects/{object_key}"


def read_file(path: str) -> bytes:
    """Read file bytes from storage."""
    if is_object_storage_path(path):
        return _download_from_object_storage(path)
    else:
        if os.path.exists(path):
            with open(path, 'rb') as f:
                return f.read()
        else:
            raise FileStorageError(f"File not found: {path}")


def _download_from_object_storage(object_path: str) -> bytes:
    """Download file bytes from Object Storage."""
    if not PRIVATE_OBJECT_DIR:
        raise FileStorageError("Object Storage not configured")
    
    entity_id = object_path[9:] if object_path.startswith("/objects/") else object_path
    full_path = f"{PRIVATE_OBJECT_DIR}/{entity_id}".replace("//", "/")
    bucket_name, object_name = _parse_object_path(full_path)
    
    download_url = _sign_url(bucket_name, object_name, "GET", 300)
    
    response = requests.get(download_url, timeout=120)
    
    if not response.ok:
        raise FileStorageError(f"Download failed: {response.status_code}")
    
    return response.content


def file_exists(path: str) -> bool:
    """Check if a file exists."""
    if not path:
        return False
    
    if is_object_storage_path(path):
        try:
            if not PRIVATE_OBJECT_DIR:
                return False
            entity_id = path[9:] if path.startswith("/objects/") else path
            full_path = f"{PRIVATE_OBJECT_DIR}/{entity_id}".replace("//", "/")
            bucket_name, object_name = _parse_object_path(full_path)
            head_url = _sign_url(bucket_name, object_name, "GET", 60)
            response = requests.head(head_url, timeout=10)
            return response.ok
        except Exception:
            try:
                read_file(path)
                return True
            except Exception:
                return False
    else:
        return os.path.exists(path)


def delete_file(path: str) -> bool:
    """Delete a file from storage."""
    try:
        if is_object_storage_path(path):
            if not PRIVATE_OBJECT_DIR:
                return False
            entity_id = path[9:] if path.startswith("/objects/") else path
            full_path = f"{PRIVATE_OBJECT_DIR}/{entity_id}".replace("//", "/")
            bucket_name, object_name = _parse_object_path(full_path)
            delete_url = _sign_url(bucket_name, object_name, "DELETE", 60)
            response = requests.delete(delete_url, timeout=30)
            return response.ok or response.status_code == 404
        else:
            if os.path.exists(path):
                os.remove(path)
            return True
    except Exception as e:
        print(f"Error deleting file {path}: {e}")
        return False


def get_file_as_image(path: str) -> Optional[Image.Image]:
    """Read file and return as PIL Image."""
    try:
        file_bytes = read_file(path)
        return Image.open(io.BytesIO(file_bytes))
    except Exception as e:
        print(f"Error reading image {path}: {e}")
        return None


def get_file_as_base64(path: str) -> Optional[str]:
    """Read file and return as base64 string."""
    try:
        file_bytes = read_file(path)
        return base64.b64encode(file_bytes).decode('utf-8')
    except Exception as e:
        print(f"Error reading file as base64 {path}: {e}")
        return None


def get_storage_mode() -> str:
    """Return current storage mode description."""
    if USE_OBJECT_STORAGE:
        return "Object Storage (persistent)"
    else:
        return "Local Filesystem (not persistent across deployments)"


print(f"File Storage: {get_storage_mode()}")
