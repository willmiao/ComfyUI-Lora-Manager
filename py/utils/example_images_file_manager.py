import logging
import os
import re
import subprocess
import sys
from urllib.parse import quote

from aiohttp import web
from ..services.settings_manager import get_settings_manager
from ..utils.example_images_paths import (
    get_model_folder,
)
from ..utils.constants import SUPPORTED_MEDIA_EXTENSIONS

logger = logging.getLogger(__name__)


_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:/")


def _is_within_root(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:
        return False


def _join_local_example_path(local_root: str, relative_path: str) -> str:
    separator = "\\" if "\\" in local_root and "/" not in local_root else "/"
    normalized_root = local_root.rstrip("\\/")
    normalized_relative = relative_path.replace("/", separator)
    if not normalized_root:
        return normalized_relative
    return f"{normalized_root}{separator}{normalized_relative}"


def _build_file_uri(path: str) -> str:
    normalized = path.replace("\\", "/")
    if _WINDOWS_DRIVE_PATTERN.match(normalized):
        return f"file:///{quote(normalized, safe='/:')}"
    if normalized.startswith("/"):
        return f"file://{quote(normalized, safe='/:')}"
    return f"file:///{quote(normalized.lstrip('/'), safe='/:')}"


def _render_open_uri_template(template: str, local_path: str, relative_path: str) -> str:
    file_uri = _build_file_uri(local_path)
    replacements = {
        "{{local_path}}": local_path,
        "{{encoded_local_path}}": quote(local_path, safe=""),
        "{{relative_path}}": relative_path,
        "{{encoded_relative_path}}": quote(relative_path, safe=""),
        "{{file_uri}}": file_uri,
        "{{encoded_file_uri}}": quote(file_uri, safe=""),
    }

    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


def _open_system_folder(model_folder: str) -> dict[str, object]:
    if os.name == "nt":  # Windows
        os.startfile(model_folder)
    elif os.name == "posix":  # macOS and Linux
        if sys.platform == "darwin":  # macOS
            subprocess.Popen(["open", model_folder])
        else:  # Linux
            subprocess.Popen(["xdg-open", model_folder])

    return {
        "success": True,
        "message": f"Opened example images folder for {model_folder}",
        "path": model_folder,
    }


class ExampleImagesFileManager:
    """Manages access and operations for example image files"""
    
    @staticmethod
    async def open_folder(request):
        """
        Open the example images folder for a specific model
        
        Expects a JSON request body with:
        {
            "model_hash": "sha256_hash"  # SHA256 hash of the model
        }
        """
        try:
            # Parse request body
            data = await request.json()
            model_hash = data.get('model_hash')
            
            if not model_hash:
                return web.json_response({
                    'success': False,
                    'error': 'Missing model_hash parameter'
                }, status=400)
            
            # Get example images path from settings
            settings_manager = get_settings_manager()
            example_images_path = settings_manager.get('example_images_path')
            if not example_images_path:
                return web.json_response({
                    'success': False,
                    'error': 'No example images path configured. Please set it in the settings panel first.'
                }, status=400)
            
            # Construct folder path for this model
            model_folder = get_model_folder(model_hash)
            if not model_folder:
                return web.json_response({
                    'success': False,
                    'error': 'Failed to resolve example images folder for this model.'
                }, status=500)

            # Path validation: ensure model_folder is under example_images_path
            if not _is_within_root(model_folder, example_images_path):
                return web.json_response({
                    'success': False,
                    'error': 'Invalid model folder path'
                }, status=400)

            # Check if folder exists
            if not os.path.exists(model_folder):
                return web.json_response({
                    'success': False,
                    'error': 'No example images found for this model. Download example images first.'
                }, status=404)

            root_path = os.path.abspath(example_images_path)
            relative_path = os.path.relpath(model_folder, root_path).replace("\\", "/")
            open_mode = settings_manager.get("example_images_open_mode") or "system"

            if open_mode == "clipboard":
                local_root = settings_manager.get("example_images_local_root") or root_path
                local_path = _join_local_example_path(local_root, relative_path)
                return web.json_response({
                    'success': True,
                    'mode': 'clipboard',
                    'path': local_path,
                    'relative_path': relative_path,
                })

            if open_mode == "uri_template":
                local_root = settings_manager.get("example_images_local_root") or root_path
                uri_template = settings_manager.get("example_images_open_uri_template") or ""
                if not uri_template.strip():
                    return web.json_response({
                        'success': False,
                        'error': 'No example image open URI template configured.'
                    }, status=400)

                local_path = _join_local_example_path(local_root, relative_path)
                return web.json_response({
                    'success': True,
                    'mode': 'uri',
                    'path': local_path,
                    'relative_path': relative_path,
                    'uri': _render_open_uri_template(uri_template, local_path, relative_path),
                })

            return web.json_response(_open_system_folder(model_folder))
            
        except Exception as e:
            logger.error(f"Failed to open example images folder: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)

    @staticmethod
    async def get_files(request):
        """
        Get the list of example image files for a specific model
        
        Expects:
        - model_hash in query parameters
        
        Returns:
        - List of image files and their paths
        """
        try:
            # Get model_hash from query parameters
            model_hash = request.query.get('model_hash')
            
            if not model_hash:
                return web.json_response({
                    'success': False,
                    'error': 'Missing model_hash parameter'
                }, status=400)
            
            # Get example images path from settings
            settings_manager = get_settings_manager()
            example_images_path = settings_manager.get('example_images_path')
            if not example_images_path:
                return web.json_response({
                    'success': False,
                    'error': 'No example images path configured'
                }, status=400)
            
            # Construct folder path for this model
            model_folder = get_model_folder(model_hash)
            if not model_folder:
                return web.json_response({
                    'success': False,
                    'error': 'Failed to resolve example images folder for this model'
                }, status=500)

            # Check if folder exists
            if not os.path.exists(model_folder):
                return web.json_response({
                    'success': False, 
                    'error': 'No example images found for this model',
                    'files': []
                }, status=404)
            
            # Get list of files in the folder
            files = []
            for file in os.listdir(model_folder):
                file_path = os.path.join(model_folder, file)
                if os.path.isfile(file_path):
                    # Check if file is a supported media file
                    file_ext = os.path.splitext(file)[1].lower()
                    if (file_ext in SUPPORTED_MEDIA_EXTENSIONS['images'] or 
                        file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos']):
                        relative_path = os.path.relpath(model_folder, os.path.abspath(example_images_path)).replace("\\", "/")
                        files.append({
                            'name': file,
                            'path': f'/example_images_static/{relative_path}/{file}',
                            'extension': file_ext,
                            'is_video': file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos']
                        })
            
            return web.json_response({
                'success': True,
                'files': files
            })
            
        except Exception as e:
            logger.error(f"Failed to get example image files: {e}", exc_info=True)
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @staticmethod
    async def has_images(request):
        """
        Check if the example images folder for a model exists and is not empty
        
        Expects:
        - model_hash in query parameters
        
        Returns:
        - Boolean indicating whether the folder exists and contains images/videos
        """
        try:
            # Get model_hash from query parameters
            model_hash = request.query.get('model_hash')
            
            if not model_hash:
                return web.json_response({
                    'success': False,
                    'error': 'Missing model_hash parameter'
                }, status=400)
            
            # Get example images path from settings
            settings_manager = get_settings_manager()
            example_images_path = settings_manager.get('example_images_path')
            if not example_images_path:
                return web.json_response({
                    'has_images': False
                })
            
            # Construct folder path for this model
            model_folder = get_model_folder(model_hash)
            if not model_folder:
                return web.json_response({
                    'has_images': False,
                    'error': 'Failed to resolve example images folder for this model'
                })

            # Check if folder exists
            if not os.path.exists(model_folder) or not os.path.isdir(model_folder):
                return web.json_response({
                    'has_images': False
                })
            
            # Check if folder contains any supported media files
            for file in os.listdir(model_folder):
                file_path = os.path.join(model_folder, file)
                if os.path.isfile(file_path):
                    file_ext = os.path.splitext(file)[1].lower()
                    if (file_ext in SUPPORTED_MEDIA_EXTENSIONS['images'] or 
                        file_ext in SUPPORTED_MEDIA_EXTENSIONS['videos']):
                        return web.json_response({
                            'has_images': True
                        })
            
            # If reached here, folder exists but has no supported media files
            return web.json_response({
                'has_images': False
            })
            
        except Exception as e:
            logger.error(f"Failed to check example images folder: {e}", exc_info=True)
            return web.json_response({
                'has_images': False,
                'error': str(e)
            })
