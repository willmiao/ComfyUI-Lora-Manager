import os
import hashlib
import json
from typing import Dict, Optional
from .models import LoraMetadata

async def calculate_sha256(file_path: str) -> str:
    """Calculate SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def _find_preview_file(base_name: str, dir_path: str) -> str:
    """Find preview file for given base name in directory"""
    preview_patterns = [
        f"{base_name}.preview.png",
        f"{base_name}.preview.jpg",
        f"{base_name}.preview.jpeg",
        f"{base_name}.preview.mp4",
        f"{base_name}.png",
        f"{base_name}.jpg", 
        f"{base_name}.jpeg",
        f"{base_name}.mp4"
    ]
    
    for pattern in preview_patterns:
        full_pattern = os.path.join(dir_path, pattern)
        if os.path.exists(full_pattern):
            return full_pattern.replace(os.sep, "/")
    return ""

async def get_file_info(file_path: str) -> LoraMetadata:
    """Get basic file information as LoraMetadata object"""
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    dir_path = os.path.dirname(file_path)
    
    preview_url = _find_preview_file(base_name, dir_path)
    
    return LoraMetadata(
        file_name=base_name,
        model_name=base_name,
        file_path=file_path,
        size=os.path.getsize(file_path),
        modified=os.path.getmtime(file_path),
        sha256=await calculate_sha256(file_path),
        base_model="Unknown",  # Will be updated later
        from_civitai=True,
        preview_url=preview_url,
    )

async def save_metadata(file_path: str, metadata: LoraMetadata) -> None:
    """Save metadata to .metadata.json file"""
    metadata_path = f"{os.path.splitext(file_path)[0]}.metadata.json"
    try:
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata.to_dict(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving metadata to {metadata_path}: {str(e)}")

async def load_metadata(file_path: str) -> Optional[LoraMetadata]:
    """Load metadata from .metadata.json file"""
    metadata_path = f"{os.path.splitext(file_path)[0]}.metadata.json"
    try:
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                preview_url = data.get('preview_url', '')
                # preview_path = os.path.join(loras_root, preview_url) if preview_url else ''
                if not preview_url or not os.path.exists(preview_url):
                    base_name = os.path.splitext(os.path.basename(file_path))[0]
                    dir_path = os.path.dirname(file_path)
                    data['preview_url'] = _find_preview_file(base_name, dir_path)
                    if data['preview_url']:
                        with open(metadata_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                return LoraMetadata.from_dict(data)
    except Exception as e:
        print(f"Error loading metadata from {metadata_path}: {str(e)}")
    return None

async def update_civitai_metadata(file_path: str, civitai_data: Dict) -> None:
    """Update metadata file with Civitai data"""
    metadata = await load_metadata(file_path)
    metadata['civitai'] = civitai_data
    await save_metadata(file_path, metadata)