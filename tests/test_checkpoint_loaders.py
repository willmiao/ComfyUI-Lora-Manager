"""Tests for checkpoint and unet loaders with extra folder paths support"""

import pytest
import os


# Get project root directory (ComfyUI-Lora-Manager folder)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCheckpointLoaderLM:
    """Test CheckpointLoaderLM node"""

    def test_class_attributes(self):
        """Test that CheckpointLoaderLM has required class attributes"""
        # Import in a way that doesn't require ComfyUI
        import ast

        filepath = os.path.join(PROJECT_ROOT, "py", "nodes", "checkpoint_loader.py")

        with open(filepath, "r") as f:
            tree = ast.parse(f.read())

        # Find CheckpointLoaderLM class
        classes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }
        assert "CheckpointLoaderLM" in classes

        cls = classes["CheckpointLoaderLM"]

        # Check for NAME attribute
        name_attr = [
            n
            for n in cls.body
            if isinstance(n, ast.Assign)
            and any(t.id == "NAME" for t in n.targets if isinstance(t, ast.Name))
        ]
        assert len(name_attr) > 0, "CheckpointLoaderLM should have NAME attribute"

        # Check for CATEGORY attribute
        cat_attr = [
            n
            for n in cls.body
            if isinstance(n, ast.Assign)
            and any(t.id == "CATEGORY" for t in n.targets if isinstance(t, ast.Name))
        ]
        assert len(cat_attr) > 0, "CheckpointLoaderLM should have CATEGORY attribute"

        # Check for INPUT_TYPES method
        input_types = [
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "INPUT_TYPES"
        ]
        assert len(input_types) > 0, "CheckpointLoaderLM should have INPUT_TYPES method"

        # Check for load_checkpoint method
        load_method = [
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "load_checkpoint"
        ]
        assert len(load_method) > 0, (
            "CheckpointLoaderLM should have load_checkpoint method"
        )


class TestUNETLoaderLM:
    """Test UNETLoaderLM node"""

    def test_class_attributes(self):
        """Test that UNETLoaderLM has required class attributes"""
        # Import in a way that doesn't require ComfyUI
        import ast

        filepath = os.path.join(PROJECT_ROOT, "py", "nodes", "unet_loader.py")

        with open(filepath, "r") as f:
            tree = ast.parse(f.read())

        # Find UNETLoaderLM class
        classes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }
        assert "UNETLoaderLM" in classes

        cls = classes["UNETLoaderLM"]

        # Check for NAME attribute
        name_attr = [
            n
            for n in cls.body
            if isinstance(n, ast.Assign)
            and any(t.id == "NAME" for t in n.targets if isinstance(t, ast.Name))
        ]
        assert len(name_attr) > 0, "UNETLoaderLM should have NAME attribute"

        # Check for CATEGORY attribute
        cat_attr = [
            n
            for n in cls.body
            if isinstance(n, ast.Assign)
            and any(t.id == "CATEGORY" for t in n.targets if isinstance(t, ast.Name))
        ]
        assert len(cat_attr) > 0, "UNETLoaderLM should have CATEGORY attribute"

        # Check for INPUT_TYPES method
        input_types = [
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "INPUT_TYPES"
        ]
        assert len(input_types) > 0, "UNETLoaderLM should have INPUT_TYPES method"

        # Check for load_unet method
        load_method = [
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "load_unet"
        ]
        assert len(load_method) > 0, "UNETLoaderLM should have load_unet method"


class TestUtils:
    """Test utility functions"""

    def test_get_checkpoint_info_absolute_exists(self):
        """Test that get_checkpoint_info_absolute function exists in utils"""
        import ast

        filepath = os.path.join(PROJECT_ROOT, "py", "utils", "utils.py")

        with open(filepath, "r") as f:
            tree = ast.parse(f.read())

        functions = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        assert "get_checkpoint_info_absolute" in functions, (
            "get_checkpoint_info_absolute should exist"
        )

    def test_format_model_name_for_comfyui_exists(self):
        """Test that _format_model_name_for_comfyui function exists in utils"""
        import ast

        filepath = os.path.join(PROJECT_ROOT, "py", "utils", "utils.py")

        with open(filepath, "r") as f:
            tree = ast.parse(f.read())

        functions = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        ]
        assert "_format_model_name_for_comfyui" in functions, (
            "_format_model_name_for_comfyui should exist"
        )
