from typing import Any


class AnyType(str):
    """A special class that is always equal in not equal comparisons. Credit to pythongosssss"""

    def __ne__(self, __value: object) -> bool:
        return False


# Credit to Regis Gaughan, III (rgthree)
class FlexibleOptionalInputType(dict[str, Any]):
    """A special class to make flexible nodes that pass data to our python handlers.

    Enables both flexible/dynamic input types (like for Any Switch) or a dynamic number of inputs
    (like for Any Switch, Context Switch, Context Merge, Power Lora Loader, etc).

    Note, for ComfyUI, all that's needed is the `__contains__` override below, which tells ComfyUI
    that our node will handle the input, regardless of what it is.

    However, with https://github.com/comfyanonymous/ComfyUI/pull/2666 a large change would occur
    requiring more details on the input itself. There, we need to return a list/tuple where the first
    item is the type. This can be a real type, or use the AnyType for additional flexibility.

    This should be forwards compatible unless more changes occur in the PR.
    """

    def __init__(self, type):
        super().__init__()
        self.type = type

    def __getitem__(self, key):
        return (self.type,)

    def __contains__(self, key):
        return True


any_type = AnyType("*")

# Common methods extracted from lora_loader.py and lora_stacker.py
import os
import re
import logging
import copy
import sys
import asyncio
import folder_paths  # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


def get_lora_syntax_format():
    try:
        from ..services.settings_manager import get_settings_manager
        return get_settings_manager().get("lora_syntax_format", "legacy")
    except Exception:
        return "legacy"


def apply_lora_syntax_format(name):
    fmt = get_lora_syntax_format()
    if fmt == "legacy":
        return name.replace("\\", "/").rstrip("/").split("/")[-1]
    return name


def extract_lora_name(lora_path):
    normalized = lora_path.replace("\\", "/")
    basename = os.path.basename(normalized)
    name_no_ext = os.path.splitext(basename)[0]
    dirname = os.path.dirname(normalized)
    if dirname and dirname not in (".", "/") and not normalized.startswith("/"):
        return apply_lora_syntax_format(f"{dirname}/{name_no_ext}")
    return apply_lora_syntax_format(name_no_ext)


def parse_lora_syntax(text: str) -> list[dict[str, Any]]:
    """Parse <lora:name:strength> syntax from text input into a list of dicts.

    Each entry contains: name, model_strength, clip_strength.
    Supports both ``<lora:name:strength>`` and ``<lora:name:model_strength:clip_strength>``.
    """
    pattern = r"<lora:([^:>]+):([^:>]+)(?::([^:>]+))?>"
    matches = re.findall(pattern, text, re.IGNORECASE)
    loras = []
    for match in matches:
        model_strength = float(match[1])
        loras.append({
            "name": match[0],
            "model_strength": model_strength,
            "clip_strength": float(match[2]) if match[2] else model_strength,
        })
    return loras


def get_loras_list(kwargs):
    """Helper to extract loras list from either old or new kwargs format"""
    if "loras" not in kwargs:
        return []

    loras_data = kwargs["loras"]
    # Handle new format: {'loras': {'__value__': [...]}}
    if isinstance(loras_data, dict) and "__value__" in loras_data:
        return loras_data["__value__"]
    # Handle old format: {'loras': [...]}
    elif isinstance(loras_data, list):
        return loras_data
    # Unexpected format
    else:
        logger.warning(f"Unexpected loras format: {type(loras_data)}")
        return []


_LORA_EXTENSIONS = (".safetensors", ".ckpt", ".pt", ".bin")


def _strip_lora_extension(name: str) -> str:
    """Strip a known LoRA model extension from a name (case-insensitive)."""
    lowered = name.lower()
    for ext in _LORA_EXTENSIONS:
        if lowered.endswith(ext):
            return name[: -len(ext)]
    return name


def _find_missing_loras(names: list[str]) -> list[str]:
    """Return the names that cannot be resolved to an existing local LoRA file.

    Mirrors the matching semantics of ``get_lora_info_absolute``
    (py/utils/utils.py): after stripping the extension, a name matches a cached
    LoRA when it equals the cached file name or the ``folder/file`` path. As a
    fallback, a name containing a folder that only matches by basename resolves
    to the first basename match (same behavior as the runtime resolver). Raw
    absolute paths that exist on disk are always considered available.

    The scanner cache is fetched once for all names; the cache may be stale, so
    resolved paths are additionally verified with ``os.path.isfile``.
    """
    if not names:
        return []

    async def _check() -> list[str]:
        from ..services.service_registry import ServiceRegistry

        scanner = await ServiceRegistry.get_lora_scanner()
        # The scanner cache may not be hydrated yet (startup, library path
        # change). An empty cache is not authoritative — treat it as "cannot
        # verify" and skip validation instead of flagging every active LoRA
        # as missing.
        if getattr(scanner, "_cache", None) is None or getattr(
            scanner, "_is_initializing", False
        ):
            return []
        cache = await scanner.get_cached_data()

        lookup = {}
        basename_candidates = {}
        for item in cache.raw_data:
            file_path = item.get("file_path")
            if not file_path:
                continue
            file_name = item.get("file_name", "")
            folder = item.get("folder", "")
            file_name_no_ext = _strip_lora_extension(file_name)
            path_name_no_ext = (
                f"{folder}/{file_name_no_ext}".replace("\\", "/")
                if folder
                else file_name_no_ext
            )
            lookup.setdefault(file_name_no_ext, file_path)
            lookup.setdefault(path_name_no_ext, file_path)
            basename_candidates.setdefault(file_name_no_ext, []).append(
                (folder, file_path)
            )

        missing = []
        for name in names:
            if not name:
                continue
            normalized = name.replace("\\", "/")
            # Raw absolute paths (outside the library) are usable as-is.
            if os.path.isfile(normalized):
                continue
            no_ext = _strip_lora_extension(normalized)
            file_path = lookup.get(no_ext)
            if file_path is None and "/" in no_ext:
                # A name with a folder that matches only by basename resolves
                # at runtime like get_lora_info_absolute's fallback does:
                # prefer a candidate whose folder prefixes the name, else the
                # first basename match.
                folder, basename = no_ext.rsplit("/", 1)
                candidates = basename_candidates.get(basename, [])
                file_path = next(
                    (
                        fp
                        for fld, fp in candidates
                        if fld and no_ext.startswith(fld + "/")
                    ),
                    None,
                )
                if file_path is None and candidates:
                    file_path = candidates[0][1]
            if file_path is None or not os.path.isfile(file_path):
                missing.append(name)
        return missing

    try:
        # Check if we're already in an event loop
        loop = asyncio.get_running_loop()
        # If we're in a running loop, run the async check in a separate thread
        import concurrent.futures

        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(_check())
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            return future.result()
    except RuntimeError:
        # No event loop is running, we can use asyncio.run()
        return asyncio.run(_check())


def validate_lora_entries(kwargs):
    """Validate active LoRA widget entries against the local library.

    Used by node ``VALIDATE_INPUTS`` implementations so ComfyUI rejects the
    prompt at queue time (``custom_validation_failed``) when an active entry
    references a LoRA that is not available locally — mirroring how built-in
    loader nodes flag missing models before execution starts.

    Returns:
        None when every active entry resolves to an existing local file,
        otherwise a descriptive error string listing the missing LoRAs.
        Verification failures (e.g. scanner not ready) are treated as valid
        so queueing is never blocked by validation machinery itself.
    """
    # Missing/empty loras input is always valid; skip get_loras_list so it
    # does not log a warning for the None case on every queue.
    if not kwargs.get("loras"):
        return None
    loras = get_loras_list(kwargs)
    active_names = []
    for lora in loras:
        if not isinstance(lora, dict):
            continue
        if not lora.get("active", False):
            continue
        active_names.append(apply_lora_syntax_format(str(lora.get("name") or "")))
    try:
        missing = _find_missing_loras(active_names)
    except Exception:
        logger.exception("Failed to validate LoRA entries against the local library")
        return None
    if not missing:
        return None
    return "Missing LoRA(s) in local library: " + ", ".join(missing)


def load_state_dict_in_safetensors(path, device="cpu", filter_prefix=""):
    """Simplified version of load_state_dict_in_safetensors that just loads from a local path"""
    import safetensors.torch

    state_dict = {}
    with safetensors.torch.safe_open(path, framework="pt", device=device) as f:  # type: ignore[attr-defined]
        for k in f.keys():
            if filter_prefix and not k.startswith(filter_prefix):
                continue
            state_dict[k.removeprefix(filter_prefix)] = f.get_tensor(k)
    return state_dict


def to_diffusers(input_lora):
    """Simplified version of to_diffusers for Flux LoRA conversion"""
    import torch
    from diffusers.utils.state_dict_utils import convert_unet_state_dict_to_peft
    from diffusers.loaders import FluxLoraLoaderMixin  # type: ignore[attr-defined]

    if isinstance(input_lora, str):
        tensors = load_state_dict_in_safetensors(input_lora, device="cpu")
    else:
        tensors = {k: v for k, v in input_lora.items()}

    # Convert FP8 tensors to BF16
    for k, v in tensors.items():
        if v.dtype not in [torch.float64, torch.float32, torch.bfloat16, torch.float16]:
            tensors[k] = v.to(torch.bfloat16)

    new_tensors = FluxLoraLoaderMixin.lora_state_dict(tensors)
    new_tensors = convert_unet_state_dict_to_peft(new_tensors)

    return new_tensors


def nunchaku_load_lora(model, lora_name, lora_strength):
    """Load a Flux LoRA for Nunchaku model"""
    # Get full path to the LoRA file. Allow both direct paths and registered LoRA names.
    lora_path = (
        lora_name
        if os.path.isfile(lora_name)
        else folder_paths.get_full_path("loras", lora_name)
    )
    if not lora_path or not os.path.isfile(lora_path):
        logger.warning("Skipping LoRA '%s' because it could not be found", lora_name)
        return model

    model_wrapper = model.model.diffusion_model

    # Try to find copy_with_ctx in the same module as ComfyFluxWrapper
    module_name = model_wrapper.__class__.__module__
    module = sys.modules.get(module_name)
    copy_with_ctx = getattr(module, "copy_with_ctx", None)

    if copy_with_ctx is not None:
        # New logic using copy_with_ctx from ComfyUI-nunchaku 1.1.0+
        ret_model_wrapper, ret_model = copy_with_ctx(model_wrapper)
        ret_model_wrapper.loras = [*model_wrapper.loras, (lora_path, lora_strength)]
    else:
        # Fallback to legacy logic
        logger.warning(
            "Please upgrade ComfyUI-nunchaku to 1.1.0 or above for better LoRA support. Falling back to legacy loading logic."
        )
        transformer = model_wrapper.model

        # Save the transformer temporarily
        model_wrapper.model = None
        ret_model = copy.deepcopy(model)  # copy everything except the model
        ret_model_wrapper = ret_model.model.diffusion_model

        # Restore the model and set it for the copy
        model_wrapper.model = transformer
        ret_model_wrapper.model = transformer
        ret_model_wrapper.loras.append((lora_path, lora_strength))

    # Convert the LoRA to diffusers format
    sd = to_diffusers(lora_path)

    # Handle embedding adjustment if needed
    if "transformer.x_embedder.lora_A.weight" in sd:
        new_in_channels = sd["transformer.x_embedder.lora_A.weight"].shape[1]
        assert new_in_channels % 4 == 0
        new_in_channels = new_in_channels // 4

        old_in_channels = ret_model.model.model_config.unet_config["in_channels"]
        if old_in_channels < new_in_channels:
            ret_model.model.model_config.unet_config["in_channels"] = new_in_channels

    return ret_model


def detect_nunchaku_model_kind(model):
    """Return the supported Nunchaku model kind for a Comfy model, if any."""
    try:
        model_wrapper = model.model.diffusion_model
    except (AttributeError, TypeError):
        return None

    wrapper_name = model_wrapper.__class__.__name__
    if wrapper_name == "ComfyFluxWrapper":
        return "flux"

    inner_model = getattr(model_wrapper, "model", None)
    inner_name = inner_model.__class__.__name__ if inner_model is not None else ""
    if wrapper_name.endswith("NunchakuQwenImageTransformer2DModel"):
        return "qwen_image"
    if inner_name.endswith("NunchakuQwenImageTransformer2DModel"):
        return "qwen_image"

    return None
