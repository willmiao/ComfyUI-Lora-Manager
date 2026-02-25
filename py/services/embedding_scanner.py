import logging
from typing import List

from ..utils.models import EmbeddingMetadata
from ..config import config
from .model_scanner import ModelScanner
from .model_hash_index import ModelHashIndex

logger = logging.getLogger(__name__)

class EmbeddingScanner(ModelScanner):
    """Service for scanning and managing embedding files"""
    
    def __init__(self):
        # Define supported file extensions
        file_extensions = {'.ckpt', '.pt', '.pt2', '.bin', '.pth', '.safetensors', '.pkl', '.sft'}
        super().__init__(
            model_type="embedding",
            model_class=EmbeddingMetadata,
            file_extensions=file_extensions,
            hash_index=ModelHashIndex()
        )

    def get_model_roots(self) -> List[str]:
        """Get embedding root directories (including extra paths)"""
        roots: List[str] = []
        roots.extend(config.embeddings_roots or [])
        roots.extend(config.extra_embeddings_roots or [])
        # Remove duplicates while preserving order
        seen: set = set()
        unique_roots: List[str] = []
        for root in roots:
            if root and root not in seen:
                seen.add(root)
                unique_roots.append(root)
        return unique_roots
