"""Conversion of ComfyUI decode image tensors to PNG bytes.

Shared by the recipe "Save Recipe" flow and the workflow preview creation
flow: both read the first decoded image out of the metadata registry, which
is a torch tensor (or numpy-compatible array) rather than encoded bytes.
"""

from __future__ import annotations

import io
import logging
from typing import Any, Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def tensor_to_png_bytes(image_data: Any) -> Optional[bytes]:
    """Serialize a ComfyUI IMAGE value to PNG bytes.

    Accepts the registry's raw shape (a tensor, a numpy array, a one-element
    tuple/list, or a batched array). Returns ``None`` for unsupported shapes
    and never raises.
    """

    try:
        if isinstance(image_data, tuple):
            tensor_image = image_data[0] if image_data else None
            if tensor_image is None:
                return None
        else:
            tensor_image = image_data

        if hasattr(tensor_image, "shape"):
            logger.debug(
                "Tensor shape: %s, dtype: %s",
                tensor_image.shape,
                getattr(tensor_image, "dtype", None),
            )

        import torch  # pyright: ignore[reportMissingImports]

        if isinstance(tensor_image, torch.Tensor):
            image_np = tensor_image.cpu().numpy()
        else:
            image_np = np.array(tensor_image)

        while len(image_np.shape) > 3:
            image_np = image_np[0]

        if image_np.dtype in (np.float32, np.float64) and image_np.max() <= 1.0:
            image_np = (image_np * 255).astype(np.uint8)

        if len(image_np.shape) == 3 and image_np.shape[2] == 3:
            pil_image = Image.fromarray(image_np)
            img_byte_arr = io.BytesIO()
            pil_image.save(img_byte_arr, format="PNG")
            return img_byte_arr.getvalue()
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.error("Error processing image data: %s", exc, exc_info=True)
        return None

    return None


__all__ = ["tensor_to_png_bytes"]
