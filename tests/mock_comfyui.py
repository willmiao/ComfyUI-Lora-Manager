#!/usr/bin/env python3
"""
Mock ComfyUI dependencies for testing
"""
import sys
from unittest.mock import Mock

# Mock folder_paths module
folder_paths = Mock()
folder_paths.get_directory = Mock(return_value="/fake/path")
folder_paths.get_folder_names = Mock(return_value=["loras", "checkpoints"])

sys.modules['folder_paths'] = folder_paths

# Mock other ComfyUI modules that might be imported
nodes = Mock()
sys.modules['nodes'] = nodes

execution = Mock()
sys.modules['execution'] = execution

comfy = Mock()
comfy.model_management = Mock()
sys.modules['comfy'] = comfy
sys.modules['comfy.model_management'] = comfy.model_management
