
import pytest
from types import SimpleNamespace
from py.metadata_collector.metadata_processor import MetadataProcessor
from py.metadata_collector.constants import MODELS, SAMPLING, IS_SAMPLER

class TestMetadataTracer:
    
    @pytest.fixture
    def mock_workflow_metadata(self):
        """
        Creates a mock metadata structure with a complex workflow graph.
        Structure:
        Sampler(246) -> Guider(241) -> LoraLoader(264) -> CheckpointLoader(238)
        
        Also includes a "Decoy" checkpoint (ID 999) that is NOT connected,
        to verify we found the *connected* one, not just *any* one.
        """
        
        # 1. Define the Graph (Original Prompt)
        # Using IDs as strings to match typical ComfyUI behavior in metadata
        original_prompt = {
            "246": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "guider": ["241", 0],
                    "noise": ["255", 0],
                    "sampler": ["247", 0],
                    "sigmas": ["248", 0],
                    "latent_image": ["153", 0]
                }
            },
            "241": {
                "class_type": "CFGGuider",
                "inputs": {
                    "model": ["264", 0],
                    "positive": ["239", 0],
                    "negative": ["240", 0]
                }
            },
            "264": {
                "class_type": "LoraLoader", # Simplified name
                "inputs": {
                    "model": ["238", 0],
                    "lora_name": "some_style_lora.safetensors"
                }
            },
            "238": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "Correct_Model.safetensors"
                }
            },
            
            # unconnected / decoy nodes
            "999": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "Decoy_Model.safetensors"
                }
            },
            "154": { # Downstream VAE Decode
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["246", 0]
                }
            }
        }
        
        # 2. Define the Metadata (Collected execution data)
        metadata = {
            "current_prompt": SimpleNamespace(original_prompt=original_prompt),
            "execution_order": ["238", "264", "241", "246", "154", "999"], # 999 execs last or separately
            
            # Models Registry
            MODELS: {
                "238": {
                    "type": "checkpoint",
                    "name": "Correct_Model.safetensors"
                },
                "999": {
                    "type": "checkpoint",
                    "name": "Decoy_Model.safetensors"
                }
            },
            
            # Sampling Registry
            SAMPLING: {
                "246": {
                    IS_SAMPLER: True,
                    "parameters": {
                        "sampler_name": "euler",
                        "scheduler": "normal"
                    }
                }
            },
            "images": {
                "first_decode": {
                    "node_id": "154"
                }
            }
        }
        
        return metadata

    def test_find_primary_sampler_identifies_correct_node(self, mock_workflow_metadata):
        """Verify find_primary_sampler correctly identifies the sampler connected to the downstream decode."""
        sampler_id, sampler_info = MetadataProcessor.find_primary_sampler(mock_workflow_metadata, downstream_id="154")
        
        assert sampler_id == "246"
        assert sampler_info is not None
        assert sampler_info["parameters"]["sampler_name"] == "euler"

    def test_trace_model_path_follows_topology(self, mock_workflow_metadata):
        """Verify trace_model_path follows: Sampler -> Guider -> Lora -> Checkpoint."""
        prompt = mock_workflow_metadata["current_prompt"]
        
        # Start trace from Sampler (246)
        # Should find Checkpoint (238)
        ckpt_id = MetadataProcessor.trace_model_path(mock_workflow_metadata, prompt, "246")
        
        assert ckpt_id == "238" # Should be the ID of the connected checkpoint

    def test_find_primary_checkpoint_prioritizes_connected_model(self, mock_workflow_metadata):
        """Verify find_primary_checkpoint returns the NAME of the topologically connected checkpoint, honoring the graph."""
        name = MetadataProcessor.find_primary_checkpoint(mock_workflow_metadata, downstream_id="154")
        
        assert name == "Correct_Model.safetensors"
        assert name != "Decoy_Model.safetensors"

    def test_trace_model_path_simple_direct_connection(self):
        """Verify it works for a simple Sampler -> Checkpoint connection."""
        original_prompt = {
            "100": { # Sampler
                "class_type": "KSampler",
                "inputs": {
                    "model": ["101", 0]
                }
            },
            "101": { # Checkpoint
                "class_type": "CheckpointLoaderSimple",
                "inputs": {}
            }
        }
        
        metadata = {
            "current_prompt": SimpleNamespace(original_prompt=original_prompt),
            MODELS: {
                "101": {"type": "checkpoint", "name": "Simple_Model.safetensors"}
            }
        }
        
        ckpt_id = MetadataProcessor.trace_model_path(metadata, metadata["current_prompt"], "100")
        assert ckpt_id == "101"

    def test_trace_stops_at_max_depth(self):
        """Verify logic halts if graph is infinitely cyclic or too deep."""
        # Create a cycle: Node 1 -> Node 2 -> Node 1
        original_prompt = {
            "1": {"inputs": {"model": ["2", 0]}},
            "2": {"inputs": {"model": ["1", 0]}}
        }
        
        metadata = {
            "current_prompt": SimpleNamespace(original_prompt=original_prompt),
            MODELS: {} # No checkpoints registered
        }
        
        # Should return None, not hang forever
        ckpt_id = MetadataProcessor.trace_model_path(metadata, metadata["current_prompt"], "1")
        assert ckpt_id is None

