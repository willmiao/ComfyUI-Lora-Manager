from __future__ import annotations

"""Qwen-Image LoRA support for Nunchaku models.

Portions of the LoRA mapping/application logic in this file are adapted from
ComfyUI-QwenImageLoraLoader by GitHub user ussoewwin:
https://github.com/ussoewwin/ComfyUI-QwenImageLoraLoader

The upstream project is licensed under Apache License 2.0.
"""

import copy
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import comfy.utils  # type: ignore
import folder_paths  # type: ignore
import torch
import torch.nn as nn
from safetensors import safe_open

from nunchaku.lora.flux.nunchaku_converter import (
    pack_lowrank_weight,
    unpack_lowrank_weight,
)

logger = logging.getLogger(__name__)

KEY_MAPPING = [
    (re.compile(r"^(layers)[._](\d+)[._]attention[._]to[._]([qkv])$"), r"\1.\2.attention.to_qkv", "qkv", lambda m: m.group(3).upper()),
    (re.compile(r"^(layers)[._](\d+)[._]feed_forward[._](w1|w3)$"), r"\1.\2.feed_forward.net.0.proj", "glu", lambda m: m.group(3)),
    (re.compile(r"^(layers)[._](\d+)[._]feed_forward[._]w2$"), r"\1.\2.feed_forward.net.2", "regular", None),
    (re.compile(r"^(layers)[._](\d+)[._](.*)$"), r"\1.\2.\3", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]attn[._]to[._]([qkv])$"), r"\1.\2.attn.to_qkv", "qkv", lambda m: m.group(3).upper()),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]attn[._](q|k|v)[._]proj$"), r"\1.\2.attn.to_qkv", "qkv", lambda m: m.group(3).upper()),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]attn[._]add[._](q|k|v)[._]proj$"), r"\1.\2.attn.add_qkv_proj", "add_qkv", lambda m: m.group(3).upper()),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]out[._]proj[._]context$"), r"\1.\2.attn.to_add_out", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]out[._]proj$"), r"\1.\2.attn.to_out.0", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]attn[._]to[._]out$"), r"\1.\2.attn.to_out.0", "regular", None),
    (re.compile(r"^(single_transformer_blocks)[._](\d+)[._]attn[._]to[._]([qkv])$"), r"\1.\2.attn.to_qkv", "qkv", lambda m: m.group(3).upper()),
    (re.compile(r"^(single_transformer_blocks)[._](\d+)[._]attn[._]to[._]out$"), r"\1.\2.attn.to_out", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]ff[._]net[._]0(?:[._]proj)?$"), r"\1.\2.mlp_fc1", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]ff[._]net[._]2$"), r"\1.\2.mlp_fc2", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]ff_context[._]net[._]0(?:[._]proj)?$"), r"\1.\2.mlp_context_fc1", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]ff_context[._]net[._]2$"), r"\1.\2.mlp_context_fc2", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._](img_mlp)[._](net)[._](0)[._](proj)$"), r"\1.\2.\3.\4.\5.\6", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._](img_mlp)[._](net)[._](2)$"), r"\1.\2.\3.\4.\5", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._](txt_mlp)[._](net)[._](0)[._](proj)$"), r"\1.\2.\3.\4.\5.\6", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._](txt_mlp)[._](net)[._](2)$"), r"\1.\2.\3.\4.\5", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._](img_mod)[._](1)$"), r"\1.\2.\3.\4", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._](txt_mod)[._](1)$"), r"\1.\2.\3.\4", "regular", None),
    (re.compile(r"^(single_transformer_blocks)[._](\d+)[._]proj[._]out$"), r"\1.\2.proj_out", "single_proj_out", None),
    (re.compile(r"^(single_transformer_blocks)[._](\d+)[._]proj[._]mlp$"), r"\1.\2.mlp_fc1", "regular", None),
    (re.compile(r"^(single_transformer_blocks)[._](\d+)[._]norm[._]linear$"), r"\1.\2.norm.linear", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]norm1[._]linear$"), r"\1.\2.norm1.linear", "regular", None),
    (re.compile(r"^(transformer_blocks)[._](\d+)[._]norm1_context[._]linear$"), r"\1.\2.norm1_context.linear", "regular", None),
    (re.compile(r"^(img_in)$"), r"\1", "regular", None),
    (re.compile(r"^(txt_in)$"), r"\1", "regular", None),
    (re.compile(r"^(proj_out)$"), r"\1", "regular", None),
    (re.compile(r"^(norm_out)[._](linear)$"), r"\1.\2", "regular", None),
    (re.compile(r"^(time_text_embed)[._](timestep_embedder)[._](linear_1)$"), r"\1.\2.\3", "regular", None),
    (re.compile(r"^(time_text_embed)[._](timestep_embedder)[._](linear_2)$"), r"\1.\2.\3", "regular", None),
]

_RE_LORA_SUFFIX = re.compile(r"\.(?P<tag>lora(?:[._](?:A|B|down|up)))(?:\.[^.]+)*\.weight$")
_RE_ALPHA_SUFFIX = re.compile(r"\.(?:alpha|lora_alpha)(?:\.[^.]+)*$")


def _rename_layer_underscore_layer_name(old_name: str) -> str:
    rules = [
        (r"_(\d+)_attn_to_out_(\d+)", r".\1.attn.to_out.\2"),
        (r"_(\d+)_img_mlp_net_(\d+)_proj", r".\1.img_mlp.net.\2.proj"),
        (r"_(\d+)_txt_mlp_net_(\d+)_proj", r".\1.txt_mlp.net.\2.proj"),
        (r"_(\d+)_img_mlp_net_(\d+)", r".\1.img_mlp.net.\2"),
        (r"_(\d+)_txt_mlp_net_(\d+)", r".\1.txt_mlp.net.\2"),
        (r"_(\d+)_img_mod_(\d+)", r".\1.img_mod.\2"),
        (r"_(\d+)_txt_mod_(\d+)", r".\1.txt_mod.\2"),
        (r"_(\d+)_attn_", r".\1.attn."),
    ]
    new_name = old_name
    for pattern, replacement in rules:
        new_name = re.sub(pattern, replacement, new_name)
    return new_name


def _is_indexable_module(module):
    return isinstance(module, (nn.ModuleList, nn.Sequential, list, tuple))


def _get_module_by_name(model: nn.Module, name: str) -> Optional[nn.Module]:
    if not name:
        return model
    module = model
    for part in name.split("."):
        if not part:
            continue
        if hasattr(module, part):
            module = getattr(module, part)
        elif part.isdigit() and _is_indexable_module(module):
            try:
                module = module[int(part)]
            except (IndexError, TypeError):
                return None
        else:
            return None
    return module


def _resolve_module_name(model: nn.Module, name: str) -> Tuple[str, Optional[nn.Module]]:
    module = _get_module_by_name(model, name)
    if module is not None:
        return name, module

    replacements = [
        (".attn.to_out.0", ".attn.to_out"),
        (".attention.to_qkv", ".attention.qkv"),
        (".attention.to_out.0", ".attention.out"),
        (".feed_forward.net.0.proj", ".feed_forward.w13"),
        (".feed_forward.net.2", ".feed_forward.w2"),
        (".ff.net.0.proj", ".mlp_fc1"),
        (".ff.net.2", ".mlp_fc2"),
        (".ff_context.net.0.proj", ".mlp_context_fc1"),
        (".ff_context.net.2", ".mlp_context_fc2"),
    ]
    for src, dst in replacements:
        if src in name:
            alt = name.replace(src, dst)
            module = _get_module_by_name(model, alt)
            if module is not None:
                return alt, module
    return name, None


def _classify_and_map_key(key: str) -> Optional[Tuple[str, str, Optional[str], str]]:
    normalized = key
    if normalized.startswith("transformer."):
        normalized = normalized[len("transformer."):]
    if normalized.startswith("diffusion_model."):
        normalized = normalized[len("diffusion_model."):]
    if normalized.startswith("lora_unet_"):
        normalized = _rename_layer_underscore_layer_name(normalized[len("lora_unet_"):])

    match = _RE_LORA_SUFFIX.search(normalized)
    if match:
        tag = match.group("tag")
        base = normalized[:match.start()]
        ab = "A" if ("lora_A" in tag or tag.endswith(".A") or "down" in tag) else "B"
    else:
        match = _RE_ALPHA_SUFFIX.search(normalized)
        if not match:
            return None
        base = normalized[:match.start()]
        ab = "alpha"

    for pattern, template, group, comp_fn in KEY_MAPPING:
        key_match = pattern.match(base)
        if key_match:
            return group, key_match.expand(template), comp_fn(key_match) if comp_fn else None, ab
    return None


def _detect_lora_format(lora_state_dict: Dict[str, torch.Tensor]) -> bool:
    standard_patterns = (
        ".lora_up.",
        ".lora_down.",
        ".lora_A.",
        ".lora_B.",
        ".lora.up.",
        ".lora.down.",
        ".lora.A.",
        ".lora.B.",
    )
    return any(pattern in key for key in lora_state_dict for pattern in standard_patterns)


def _load_lora_state_dict(path_or_dict: Union[str, Path, Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
    if isinstance(path_or_dict, dict):
        return path_or_dict
    path = Path(path_or_dict)
    if path.suffix == ".safetensors":
        state_dict: Dict[str, torch.Tensor] = {}
        with safe_open(path, framework="pt", device="cpu") as handle:
            for key in handle.keys():
                state_dict[key] = handle.get_tensor(key)
        return state_dict
    return comfy.utils.load_torch_file(str(path), safe_load=True)


def _fuse_glu_lora(glu_weights: Dict[str, torch.Tensor]) -> Tuple[Optional[torch.Tensor], Optional[torch.Tensor], Optional[torch.Tensor]]:
    if "w1_A" not in glu_weights or "w3_A" not in glu_weights:
        return None, None, None
    a_w1, b_w1 = glu_weights["w1_A"], glu_weights["w1_B"]
    a_w3, b_w3 = glu_weights["w3_A"], glu_weights["w3_B"]
    if a_w1.shape[1] != a_w3.shape[1]:
        return None, None, None
    a_fused = torch.cat([a_w1, a_w3], dim=0)
    out1, out3 = b_w1.shape[0], b_w3.shape[0]
    rank1, rank3 = b_w1.shape[1], b_w3.shape[1]
    b_fused = torch.zeros(out1 + out3, rank1 + rank3, dtype=b_w1.dtype, device=b_w1.device)
    b_fused[:out1, :rank1] = b_w1
    b_fused[out1:, rank1:] = b_w3
    return a_fused, b_fused, glu_weights.get("w1_alpha")


def _fuse_qkv_lora(qkv_weights: Dict[str, torch.Tensor], model: Optional[nn.Module] = None, base_key: Optional[str] = None) -> Tuple[Optional[torch.Tensor], Optional[torch.Tensor], Optional[torch.Tensor]]:
    required_keys = ["Q_A", "Q_B", "K_A", "K_B", "V_A", "V_B"]
    if not all(key in qkv_weights for key in required_keys):
        return None, None, None
    a_q, a_k, a_v = qkv_weights["Q_A"], qkv_weights["K_A"], qkv_weights["V_A"]
    b_q, b_k, b_v = qkv_weights["Q_B"], qkv_weights["K_B"], qkv_weights["V_B"]
    if not (a_q.shape == a_k.shape == a_v.shape):
        return None, None, None
    if not (b_q.shape[1] == b_k.shape[1] == b_v.shape[1]):
        return None, None, None

    out_features = None
    if model is not None and base_key is not None:
        _, module = _resolve_module_name(model, base_key)
        out_features = getattr(module, "out_features", None) if module is not None else None

    alpha_fused = None
    alpha_q = qkv_weights.get("Q_alpha")
    alpha_k = qkv_weights.get("K_alpha")
    alpha_v = qkv_weights.get("V_alpha")
    if alpha_q is not None and alpha_k is not None and alpha_v is not None and alpha_q.item() == alpha_k.item() == alpha_v.item():
        alpha_fused = alpha_q

    a_fused = torch.cat([a_q, a_k, a_v], dim=0)
    rank = b_q.shape[1]
    out_q, out_k, out_v = b_q.shape[0], b_k.shape[0], b_v.shape[0]
    total_out = out_features if out_features is not None else out_q + out_k + out_v
    b_fused = torch.zeros(total_out, 3 * rank, dtype=b_q.dtype, device=b_q.device)
    b_fused[:out_q, :rank] = b_q
    b_fused[out_q:out_q + out_k, rank:2 * rank] = b_k
    b_fused[out_q + out_k:out_q + out_k + out_v, 2 * rank:] = b_v
    return a_fused, b_fused, alpha_fused


def _handle_proj_out_split(lora_dict: Dict[str, Dict[str, torch.Tensor]], base_key: str, model: nn.Module) -> Tuple[Dict[str, Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]], List[str]]:
    result: Dict[str, Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]] = {}
    consumed: List[str] = []
    match = re.search(r"single_transformer_blocks\.(\d+)", base_key)
    if not match or base_key not in lora_dict:
        return result, consumed
    block_idx = match.group(1)
    block = _get_module_by_name(model, f"single_transformer_blocks.{block_idx}")
    if block is None:
        return result, consumed
    a_full = lora_dict[base_key].get("A")
    b_full = lora_dict[base_key].get("B")
    alpha = lora_dict[base_key].get("alpha")
    attn_to_out = getattr(getattr(block, "attn", None), "to_out", None)
    mlp_fc2 = getattr(block, "mlp_fc2", None)
    if a_full is None or b_full is None or attn_to_out is None or mlp_fc2 is None:
        return result, consumed
    attn_in = getattr(attn_to_out, "in_features", None)
    mlp_in = getattr(mlp_fc2, "in_features", None)
    if attn_in is None or mlp_in is None or a_full.shape[1] != attn_in + mlp_in:
        return result, consumed
    result[f"single_transformer_blocks.{block_idx}.attn.to_out"] = (a_full[:, :attn_in], b_full.clone(), alpha)
    result[f"single_transformer_blocks.{block_idx}.mlp_fc2"] = (a_full[:, attn_in:], b_full.clone(), alpha)
    consumed.append(base_key)
    return result, consumed


def _apply_lora_to_module(module: nn.Module, a_tensor: torch.Tensor, b_tensor: torch.Tensor, module_name: str, model: nn.Module) -> None:
    if not hasattr(module, "in_features") or not hasattr(module, "out_features"):
        raise ValueError(f"{module_name}: unsupported module without in/out features")
    if a_tensor.shape[1] != module.in_features or b_tensor.shape[0] != module.out_features:
        raise ValueError(f"{module_name}: LoRA shape mismatch")

    if module.__class__.__name__ == "AWQW4A16Linear" and hasattr(module, "qweight"):
        if not hasattr(module, "_lora_original_forward"):
            module._lora_original_forward = module.forward
        if not hasattr(module, "_nunchaku_lora_bundle"):
            module._nunchaku_lora_bundle = []
        module._nunchaku_lora_bundle.append((a_tensor, b_tensor))

        def _awq_lora_forward(x, *args, **kwargs):
            out = module._lora_original_forward(x, *args, **kwargs)
            x_flat = x.reshape(-1, module.in_features)
            for local_a, local_b in module._nunchaku_lora_bundle:
                local_a = local_a.to(device=out.device, dtype=out.dtype)
                local_b = local_b.to(device=out.device, dtype=out.dtype)
                lora_term = (x_flat @ local_a.transpose(0, 1)) @ local_b.transpose(0, 1)
                try:
                    out = out + lora_term.reshape(out.shape)
                except Exception:
                    pass
            return out

        module.forward = _awq_lora_forward
        if not hasattr(model, "_lora_slots"):
            model._lora_slots = {}
        model._lora_slots[module_name] = {"type": "awq_w4a16"}
        return

    if hasattr(module, "proj_down") and hasattr(module, "proj_up"):
        proj_down = unpack_lowrank_weight(module.proj_down.data, down=True)
        proj_up = unpack_lowrank_weight(module.proj_up.data, down=False)
        base_rank = proj_down.shape[0] if proj_down.shape[1] == module.in_features else proj_down.shape[1]
        if proj_down.shape[1] == module.in_features:
            updated_down = torch.cat([proj_down, a_tensor], dim=0)
            axis_down = 0
        else:
            updated_down = torch.cat([proj_down, a_tensor.T], dim=1)
            axis_down = 1
        updated_up = torch.cat([proj_up, b_tensor], dim=1)
        module.proj_down.data = pack_lowrank_weight(updated_down, down=True)
        module.proj_up.data = pack_lowrank_weight(updated_up, down=False)
        module.rank = base_rank + a_tensor.shape[0]
        if not hasattr(model, "_lora_slots"):
            model._lora_slots = {}
        model._lora_slots[module_name] = {
            "type": "nunchaku",
            "base_rank": base_rank,
            "axis_down": axis_down,
        }
        return

    if isinstance(module, nn.Linear):
        if not hasattr(model, "_lora_slots"):
            model._lora_slots = {}
        if module_name not in model._lora_slots:
            model._lora_slots[module_name] = {
                "type": "linear",
                "original_weight": module.weight.detach().cpu().clone(),
            }
        module.weight.data.add_((b_tensor @ a_tensor).to(dtype=module.weight.dtype, device=module.weight.device))
        return

    raise ValueError(f"{module_name}: unsupported module type {type(module)}")


def reset_lora_v2(model: nn.Module) -> None:
    slots = getattr(model, "_lora_slots", None)
    if not slots:
        return
    for name, info in list(slots.items()):
        module = _get_module_by_name(model, name)
        if module is None:
            continue
        module_type = info.get("type", "nunchaku")
        if module_type == "nunchaku":
            base_rank = info["base_rank"]
            proj_down = unpack_lowrank_weight(module.proj_down.data, down=True)
            proj_up = unpack_lowrank_weight(module.proj_up.data, down=False)
            if info.get("axis_down", 0) == 0:
                proj_down = proj_down[:base_rank, :].clone()
            else:
                proj_down = proj_down[:, :base_rank].clone()
            proj_up = proj_up[:, :base_rank].clone()
            module.proj_down.data = pack_lowrank_weight(proj_down, down=True)
            module.proj_up.data = pack_lowrank_weight(proj_up, down=False)
            module.rank = base_rank
        elif module_type == "linear" and "original_weight" in info:
            module.weight.data.copy_(info["original_weight"].to(device=module.weight.device, dtype=module.weight.dtype))
        elif module_type == "awq_w4a16":
            if hasattr(module, "_lora_original_forward"):
                module.forward = module._lora_original_forward
            for attr in ("_lora_original_forward", "_nunchaku_lora_bundle"):
                if hasattr(module, attr):
                    delattr(module, attr)
    model._lora_slots = {}


def compose_loras_v2(model: nn.Module, lora_configs: List[Tuple[Union[str, Path, Dict[str, torch.Tensor]], float]], apply_awq_mod: bool = True) -> bool:
    del apply_awq_mod  # retained for interface compatibility
    reset_lora_v2(model)
    aggregated_weights: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    saw_supported_format = False
    unresolved_targets = 0

    for index, (path_or_dict, strength) in enumerate(lora_configs):
        if abs(strength) < 1e-5:
            continue
        lora_name = str(path_or_dict) if not isinstance(path_or_dict, dict) else f"lora_{index}"
        lora_state_dict = _load_lora_state_dict(path_or_dict)
        if not lora_state_dict or not _detect_lora_format(lora_state_dict):
            logger.warning("Skipping unsupported Qwen LoRA: %s", lora_name)
            continue
        saw_supported_format = True

        grouped_weights: Dict[str, Dict[str, torch.Tensor]] = defaultdict(dict)
        for key, value in lora_state_dict.items():
            parsed = _classify_and_map_key(key)
            if parsed is None:
                continue
            group, base_key, component, ab = parsed
            if component and ab:
                grouped_weights[base_key][f"{component}_{ab}"] = value
            else:
                grouped_weights[base_key][ab] = value

        processed_groups: Dict[str, Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]] = {}
        handled: set[str] = set()
        for base_key, weights in grouped_weights.items():
            if base_key in handled:
                continue
            a_tensor = b_tensor = alpha = None
            if "qkv" in base_key or "add_qkv_proj" in base_key:
                a_tensor, b_tensor, alpha = _fuse_qkv_lora(weights, model=model, base_key=base_key)
            elif "w1_A" in weights or "w3_A" in weights:
                a_tensor, b_tensor, alpha = _fuse_glu_lora(weights)
            elif ".proj_out" in base_key and "single_transformer_blocks" in base_key:
                split_map, consumed = _handle_proj_out_split(grouped_weights, base_key, model)
                processed_groups.update(split_map)
                handled.update(consumed)
                continue
            else:
                a_tensor, b_tensor, alpha = weights.get("A"), weights.get("B"), weights.get("alpha")
            if a_tensor is not None and b_tensor is not None:
                processed_groups[base_key] = (a_tensor, b_tensor, alpha)

        for module_name, (a_tensor, b_tensor, alpha) in processed_groups.items():
            aggregated_weights[module_name].append({
                "A": a_tensor,
                "B": b_tensor,
                "alpha": alpha,
                "strength": strength,
            })

    for module_name, weight_list in aggregated_weights.items():
        resolved_name, module = _resolve_module_name(model, module_name)
        if module is None:
            logger.warning("Skipping unresolved Qwen LoRA target: %s", module_name)
            unresolved_targets += 1
            continue
        all_a = []
        all_b_scaled = []
        for item in weight_list:
            a_tensor = item["A"]
            b_tensor = item["B"]
            alpha = item["alpha"]
            strength = float(item["strength"])
            rank = a_tensor.shape[0]
            scale = strength * ((alpha / rank) if alpha is not None else 1.0)
            if module.__class__.__name__ == "AWQW4A16Linear" and hasattr(module, "qweight"):
                target_dtype = torch.float16
                target_device = module.qweight.device
            elif hasattr(module, "proj_down"):
                target_dtype = module.proj_down.dtype
                target_device = module.proj_down.device
            elif hasattr(module, "weight"):
                target_dtype = module.weight.dtype
                target_device = module.weight.device
            else:
                target_dtype = torch.float16
                target_device = "cuda" if torch.cuda.is_available() else "cpu"
            all_a.append(a_tensor.to(dtype=target_dtype, device=target_device))
            all_b_scaled.append((b_tensor * scale).to(dtype=target_dtype, device=target_device))
        if not all_a:
            continue
        _apply_lora_to_module(module, torch.cat(all_a, dim=0), torch.cat(all_b_scaled, dim=1), resolved_name, model)

    slot_count = len(getattr(model, "_lora_slots", {}) or {})
    logger.info(
        "Qwen LoRA composition finished: requested=%d supported=%s applied_targets=%d unresolved=%d",
        len(lora_configs),
        saw_supported_format,
        slot_count,
        unresolved_targets,
    )
    return saw_supported_format


class ComfyQwenImageWrapperLM(nn.Module):
    def __init__(self, model: nn.Module, config=None, apply_awq_mod: bool = True):
        super().__init__()
        self.model = model
        self.config = {} if config is None else config
        self.dtype = next(model.parameters()).dtype
        self.loras: List[Tuple[Union[str, Path, Dict[str, torch.Tensor]], float]] = []
        self._applied_loras: Optional[List[Tuple[Union[str, Path, Dict[str, torch.Tensor]], float]]] = None
        self.apply_awq_mod = apply_awq_mod

    def __getattr__(self, name):
        try:
            inner = object.__getattribute__(self, "_modules").get("model")
        except (AttributeError, KeyError):
            inner = None
        if inner is None:
            raise AttributeError(f"{type(self).__name__!s} has no attribute {name}")
        if name == "model":
            return inner
        return getattr(inner, name)

    def process_img(self, *args, **kwargs):
        return self.model.process_img(*args, **kwargs)

    def _ensure_composed(self):
        if self._applied_loras != self.loras or (not self.loras and getattr(self.model, "_lora_slots", None)):
            is_supported_format = compose_loras_v2(self.model, self.loras, apply_awq_mod=self.apply_awq_mod)
            self._applied_loras = self.loras.copy()
            has_slots = bool(getattr(self.model, "_lora_slots", None))
            if self.loras and is_supported_format and not has_slots:
                logger.warning("Qwen LoRA compose produced 0 target modules. Resetting and retrying once.")
                reset_lora_v2(self.model)
                compose_loras_v2(self.model, self.loras, apply_awq_mod=self.apply_awq_mod)
                has_slots = bool(getattr(self.model, "_lora_slots", None))
                logger.info("Qwen LoRA retry result: applied_targets=%d", len(getattr(self.model, "_lora_slots", {}) or {}))

            offload_manager = getattr(self.model, "offload_manager", None)
            if offload_manager is not None:
                offload_settings = {
                    "num_blocks_on_gpu": getattr(offload_manager, "num_blocks_on_gpu", 1),
                    "use_pin_memory": getattr(offload_manager, "use_pin_memory", False),
                }
                logger.info(
                    "Rebuilding Qwen offload manager after LoRA compose: num_blocks_on_gpu=%s use_pin_memory=%s",
                    offload_settings["num_blocks_on_gpu"],
                    offload_settings["use_pin_memory"],
                )
                self.model.set_offload(False)
                self.model.set_offload(True, **offload_settings)

    def forward(self, *args, **kwargs):
        self._ensure_composed()
        return self.model(*args, **kwargs)


def _get_qwen_wrapper_and_transformer(model):
    model_wrapper = model.model.diffusion_model
    if hasattr(model_wrapper, "model") and hasattr(model_wrapper, "loras"):
        transformer = model_wrapper.model
        if transformer.__class__.__name__.endswith("NunchakuQwenImageTransformer2DModel"):
            return model_wrapper, transformer
    if model_wrapper.__class__.__name__.endswith("NunchakuQwenImageTransformer2DModel"):
        wrapped_model = ComfyQwenImageWrapperLM(model_wrapper, getattr(model_wrapper, "config", {}))
        model.model.diffusion_model = wrapped_model
        return wrapped_model, wrapped_model.model
    raise TypeError(f"This LoRA loader only works with Nunchaku Qwen Image models, but got {type(model_wrapper).__name__}.")


def nunchaku_load_qwen_loras(model, lora_configs: List[Tuple[str, float]], apply_awq_mod: bool = True):
    model_wrapper, transformer = _get_qwen_wrapper_and_transformer(model)
    model_wrapper.apply_awq_mod = apply_awq_mod

    saved_config = None
    if hasattr(model, "model") and hasattr(model.model, "model_config"):
        saved_config = model.model.model_config
        model.model.model_config = None

    model_wrapper.model = None
    try:
        ret_model = copy.deepcopy(model)
    finally:
        if saved_config is not None:
            model.model.model_config = saved_config
        model_wrapper.model = transformer

    ret_model_wrapper = ret_model.model.diffusion_model
    if saved_config is not None:
        ret_model.model.model_config = saved_config
    ret_model_wrapper.model = transformer
    ret_model_wrapper.apply_awq_mod = apply_awq_mod
    ret_model_wrapper.loras = list(getattr(model_wrapper, "loras", []))

    for lora_name, lora_strength in lora_configs:
        lora_path = lora_name if os.path.isfile(lora_name) else folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.isfile(lora_path):
            logger.warning("Skipping Qwen LoRA '%s' because it could not be found", lora_name)
            continue
        ret_model_wrapper.loras.append((lora_path, lora_strength))

    return ret_model
