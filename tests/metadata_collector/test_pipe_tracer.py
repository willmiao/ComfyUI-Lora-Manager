
import pytest
from types import SimpleNamespace
from py.metadata_collector.metadata_processor import MetadataProcessor
from py.metadata_collector.constants import MODELS, SAMPLING, IS_SAMPLER

class TestPipeTracer:
    
    @pytest.fixture
    def pipe_workflow_metadata(self):
        """
        Creates a mock metadata structure matching the one provided in refs/tmp.
        Structure:
        Load Checkpoint(28) -> Lora Loader(52) -> ToBasicPipe(69) -> FromBasicPipe(71) -> KSampler(32)
        """
        
        original_prompt = {
            '28': {
                'inputs': {'ckpt_name': 'Illustrious\\bananaSplitzXL_vee5PointOh.safetensors'}, 
                'class_type': 'CheckpointLoaderSimple'
            },
            '52': {
                'inputs': {
                    'model': ['28', 0],
                    'clip': ['28', 1]
                }, 
                'class_type': 'Lora Loader (LoraManager)'
            },
            '69': {
                'inputs': {
                    'model': ['52', 0], 
                    'clip': ['52', 1], 
                    'vae': ['28', 2], 
                    'positive': ['75', 0], 
                    'negative': ['30', 0]
                }, 
                'class_type': 'ToBasicPipe'
            },
            '71': {
                'inputs': {'basic_pipe': ['69', 0]}, 
                'class_type': 'FromBasicPipe'
            },
            '32': {
                'inputs': {
                    'seed': 131755205602911, 
                    'steps': 5, 
                    'cfg': 8.0, 
                    'sampler_name': 'euler_ancestral', 
                    'scheduler': 'karras', 
                    'denoise': 1.0, 
                    'model': ['71', 0], 
                    'positive': ['71', 3], 
                    'negative': ['71', 4], 
                    'latent_image': ['76', 0]
                }, 
                'class_type': 'KSampler'
            },
            '75': {'inputs': {'text': 'positive', 'clip': ['52', 1]}, 'class_type': 'CLIPTextEncode'},
            '30': {'inputs': {'text': 'negative', 'clip': ['52', 1]}, 'class_type': 'CLIPTextEncode'},
            '76': {'inputs': {'width': 832, 'height': 1216, 'batch_size': 1}, 'class_type': 'EmptyLatentImage'}
        }
        
        metadata = {
            "current_prompt": SimpleNamespace(original_prompt=original_prompt),
            MODELS: {
                "28": {
                    "type": "checkpoint",
                    "name": "bananaSplitzXL_vee5PointOh.safetensors"
                }
            },
            SAMPLING: {
                "32": {
                    IS_SAMPLER: True,
                    "parameters": {
                        "sampler_name": "euler_ancestral",
                        "scheduler": "karras"
                    }
                }
            }
        }
        
        return metadata

    def test_trace_model_path_through_pipe(self, pipe_workflow_metadata):
        """Verify trace_model_path can follow: KSampler -> FromBasicPipe -> ToBasicPipe -> Lora -> Checkpoint."""
        prompt = pipe_workflow_metadata["current_prompt"]
        
        # Start trace from KSampler (32)
        ckpt_id = MetadataProcessor.trace_model_path(pipe_workflow_metadata, prompt, "32")
        
        assert ckpt_id == "28"

    def test_find_primary_checkpoint_with_pipe(self, pipe_workflow_metadata):
        """Verify find_primary_checkpoint returns the correct name even with pipe nodes."""
        # Providing sampler_id to test the optimization as well
        name = MetadataProcessor.find_primary_checkpoint(pipe_workflow_metadata, primary_sampler_id="32")
        
        assert name == "bananaSplitzXL_vee5PointOh.safetensors"
