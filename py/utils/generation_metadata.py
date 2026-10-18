"""Offline extraction of reusable generation settings from image metadata.

Embedded graphs are data: only explicit adapters are followed, never executed.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any


class MetadataError(ValueError):
    """Metadata cannot be interpreted without a user decision."""


@dataclass
class GenerationMetadata:
    values: dict[str, Any] = field(default_factory=dict)
    loras: list[tuple[str, float, float]] = field(default_factory=list)
    issues: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    resource_hints: list[dict[str, Any]] = field(default_factory=list)


LORA_PATTERN = re.compile(r"<lora:([^<>]+?):([+-]?[\d.eE]+)(?::([+-]?[\d.eE]+))?>", re.I)
SAMPLERS = {
    "euler": "euler", "euler a": "euler_ancestral", "heun": "heun",
    "lms": "lms", "dpm2": "dpm_2", "dpm2 a": "dpm_2_ancestral",
    "dpm++ 2m": "dpmpp_2m", "dpm++ 2s a": "dpmpp_2s_ancestral",
    "dpm++ sde": "dpmpp_sde", "dpm++ 2m sde": "dpmpp_2m_sde",
    "dpm++ 3m sde": "dpmpp_3m_sde", "ddim": "ddim", "uni pc": "uni_pc",
}


def finite_number(value: Any) -> float:
    if isinstance(value, bool):
        raise MetadataError("Boolean is not a numeric generation setting")
    number = float(value)
    if not math.isfinite(number):
        raise MetadataError("Generation settings must be finite numbers")
    return number


def split_lora_tags(text: str) -> tuple[str, list[tuple[str, float, float]]]:
    loras = []

    def remove(match: re.Match[str]) -> str:
        model = finite_number(match[2])
        clip = finite_number(match[3]) if match[3] is not None else model
        loras.append((match[1].strip(), model, clip))
        return ""

    clean = LORA_PATTERN.sub(remove, text).strip()
    if re.search(r"<lora:", clean, re.I):
        raise MetadataError("Malformed LoRA directive; correct the prompt with overrides_json")
    return clean, loras


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        if len(value) > 16 * 1024 * 1024:
            raise MetadataError("Metadata exceeds the 16 MiB parsing limit")
        value = json.loads(value)
    if not isinstance(value, dict):
        raise MetadataError("Expected a metadata JSON object")
    return value


class GraphReader:
    """Follow a selected sampler's inputs without mixing workflow branches."""

    def __init__(self, graph: dict[str, Any], inactive_ids: set[str] | None = None) -> None:
        if len(graph) > 10000:
            raise MetadataError("Workflow exceeds the 10,000 node parsing limit")
        self.graph = {str(key): value for key, value in graph.items()}
        self.inactive_ids = inactive_ids or set()
        self.result = GenerationMetadata()

    def node(self, link: Any, seen: tuple[str, ...]) -> tuple[str, str, dict[str, Any]]:
        if not (isinstance(link, list) and len(link) == 2 and isinstance(link[1], int)):
            raise MetadataError("Expected a workflow connection")
        node_id = str(link[0])
        if node_id in seen or len(seen) >= 100:
            raise MetadataError("Cyclic or excessively deep workflow connection")
        node = self.graph.get(node_id)
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            raise MetadataError(f"Missing or malformed node {node_id}")
        return node_id, node.get("class_type", ""), node["inputs"]

    def scalar(self, value: Any, seen: tuple[str, ...] = ()) -> Any:
        if not isinstance(value, list):
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                return value
            raise MetadataError("Missing or non-scalar setting")
        node_id, kind, inputs = self.node(value, seen)
        if kind == "Input Parameters (Image Saver)":
            keys = ("seed", "steps", "cfg", "sampler", "scheduler", "denoise")
            if not 0 <= value[1] < len(keys):
                raise MetadataError(f"Unsupported parameter output {value[1]} on {node_id}")
            return self.scalar(inputs.get(keys[value[1]]), (*seen, node_id))
        if value[1] != 0:
            raise MetadataError(f"Unsupported output {value[1]} on {kind} ({node_id})")
        keys = {
            "PrimitiveNode": "value", "PrimitiveInt": "value", "PrimitiveFloat": "value",
            "PrimitiveString": "value", "PrimitiveStringMultiline": "value",
            "easy int": "value", "easy float": "value", "easy string": "value",
            "Seed (rgthree)": "seed",
            "Sampler Selector (Image Saver)": "sampler_name",
            "Scheduler Selector (Image Saver)": "scheduler",
            "Text (LoraManager)": "text", "Reroute": "value",
        }
        if kind not in keys:
            raise MetadataError(f"Unsupported value node {kind} ({node_id})")
        resolved = self.scalar(inputs.get(keys[kind]), (*seen, node_id))
        if kind == "Text (LoraManager)" and isinstance(resolved, str) and re.search(r"__[^\n]+?__|\{[^{}]*\|[^{}]*\}", resolved):
            raise MetadataError("Dynamic text expansion requires an explicit prompt override")
        return resolved

    def text(self, link: Any, seen: tuple[str, ...] = ()) -> str:
        node_id, kind, inputs = self.node(link, seen)
        if link[1] != 0:
            raise MetadataError(f"Unsupported conditioning output on {kind} ({node_id})")
        if kind in ("CLIPTextEncode", "Prompt (LoraManager)"):
            if kind == "Prompt (LoraManager)" and any(k.startswith("trigger_words") for k in inputs):
                raise MetadataError("Prompt has dynamic trigger words; provide an explicit prompt override")
            value = self.scalar(inputs.get("text"), (*seen, node_id))
            if not isinstance(value, str):
                raise MetadataError("Prompt is not text")
            if kind == "Prompt (LoraManager)" and re.search(r"__[^\n]+?__|\{[^{}]*\|[^{}]*\}", value):
                raise MetadataError("Dynamic prompt expansion cannot be recovered from source text; provide an explicit prompt override")
            return value
        if kind in ("CLIPTextEncodeSDXL", "CLIPTextEncodeFlux"):
            keys = ("text_g", "text_l") if kind == "CLIPTextEncodeSDXL" else ("clip_l", "t5xxl")
            texts = [self.scalar(inputs.get(key), (*seen, node_id)) for key in keys]
            if texts[0] != texts[1] or not isinstance(texts[0], str):
                raise MetadataError(f"{kind} has distinct encoder prompts; a single string cannot reproduce it")
            self.result.notes.append(f"{kind}: restore architecture-specific conditioning separately.")
            return texts[0]
        if kind == "ConditioningZeroOut":
            raise MetadataError("Zeroed conditioning is not equivalent to encoding an empty prompt")
        raise MetadataError(f"Unsupported conditioning node {kind} ({node_id}); use a prompt override")

    def widget_loras(self, value: Any) -> list[tuple[str, float, float]]:
        if isinstance(value, dict):
            value = value.get("__value__")
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
            value = value[0]
        if not isinstance(value, list):
            raise MetadataError("Unsupported LoRA widget data")
        entries = []
        for item in value:
            if not isinstance(item, dict):
                raise MetadataError("Malformed LoRA widget entry")
            if item.get("active", False):
                name = item.get("name")
                if not isinstance(name, str) or not name:
                    raise MetadataError("LoRA name is missing")
                strength = finite_number(item.get("strength"))
                entries.append((name, strength, finite_number(item.get("clipStrength", strength))))
        return entries

    def stack(self, link: Any, seen: tuple[str, ...] = ()) -> list[tuple[str, float, float]]:
        node_id, kind, inputs = self.node(link, seen)
        if link[1] != 0:
            raise MetadataError("Unsupported LoRA stack output")
        seen = (*seen, node_id)
        if kind == "Lora Stacker (LoraManager)":
            previous = self.stack(inputs["lora_stack"], seen) if "lora_stack" in inputs else []
            return previous + self.widget_loras(inputs.get("loras", []))
        if kind == "Lora Stack Combiner (LoraManager)":
            entries = []
            keys = [key for key in inputs if re.fullmatch(r"lora_stack\d+", key)]
            for key in sorted(keys, key=lambda key: int(key[len("lora_stack"):])):
                entries.extend(self.stack(inputs[key], seen))
            return entries
        raise MetadataError(f"Unsupported LoRA stack node {kind} ({node_id})")

    def model(self, link: Any, seen: tuple[str, ...] = ()) -> None:
        node_id, kind, inputs = self.node(link, seen)
        if link[1] != 0:
            raise MetadataError("Unsupported model output")
        seen = (*seen, node_id)
        loaders = {
            "CheckpointLoaderSimple": ("checkpoint_name", "ckpt_name"),
            "CheckpointLoader": ("checkpoint_name", "ckpt_name"),
            "Checkpoint Loader (LoraManager)": ("checkpoint_name", "ckpt_name"),
            "UNETLoader": ("unet_name", "unet_name"),
            "Unet Loader (LoraManager)": ("unet_name", "unet_name"),
        }
        if kind in loaders:
            output, key = loaders[kind]
            self.result.values[output] = self.scalar(inputs.get(key), seen)
            return
        if kind in ("LoraLoader", "LoraLoaderModelOnly", "Lora Loader (LoraManager)", "LoraLoaderLM", "LoRA Text Loader (LoraManager)"):
            self.model(inputs.get("model"), seen)
            if "lora_stack" in inputs:
                self.result.loras.extend(self.stack(inputs["lora_stack"], seen))
            if kind in ("LoraLoader", "LoraLoaderModelOnly"):
                strength = finite_number(self.scalar(inputs.get("strength_model"), seen))
                clip = 0.0 if kind == "LoraLoaderModelOnly" else finite_number(self.scalar(inputs.get("strength_clip"), seen))
                name = self.scalar(inputs.get("lora_name"), seen)
                if not isinstance(name, str):
                    raise MetadataError("LoRA name is not text")
                self.result.loras.append((name, strength, clip))
            elif kind == "LoRA Text Loader (LoraManager)":
                _, entries = split_lora_tags(self.scalar(inputs.get("lora_syntax"), seen))
                self.result.loras.extend(entries)
            else:
                self.result.loras.extend(self.widget_loras(inputs.get("loras", [])))
            return
        raise MetadataError(f"Unsupported model node {kind} ({node_id}); model/LoRA chain is incomplete")

    def clip_loras(self, link: Any, seen: tuple[str, ...] = ()) -> list[tuple[str, float]]:
        """Check that prompt CLIP branches actually use the recovered LoRA stack."""
        node_id, kind, inputs = self.node(link, seen)
        seen = (*seen, node_id)
        if kind in ("CheckpointLoaderSimple", "CheckpointLoader", "Checkpoint Loader (LoraManager)") and link[1] == 1:
            return []
        if kind in ("CLIPLoader", "DualCLIPLoader", "TripleCLIPLoader") and link[1] == 0:
            return []
        if kind in ("LoraLoader", "Lora Loader (LoraManager)", "LoraLoaderLM", "LoRA Text Loader (LoraManager)") and link[1] == 1:
            previous = self.clip_loras(inputs.get("clip"), seen)
            entries = self.stack(inputs["lora_stack"], seen) if "lora_stack" in inputs else []
            if kind == "LoraLoader":
                entries.append((self.scalar(inputs.get("lora_name")), 0, finite_number(self.scalar(inputs.get("strength_clip")))))
            elif kind == "LoRA Text Loader (LoraManager)":
                _, parsed = split_lora_tags(self.scalar(inputs.get("lora_syntax")))
                entries.extend(parsed)
            else:
                entries.extend(self.widget_loras(inputs.get("loras", [])))
            return previous + [(name, clip) for name, _, clip in entries if clip != 0]
        raise MetadataError(f"Unsupported CLIP branch {kind} ({node_id}); restore text encoder/conditioning separately")

    def select_sampler(self, sampler_id: str) -> str:
        candidates = [key for key, node in self.graph.items() if isinstance(node, dict) and node.get("class_type") in ("KSampler", "KSamplerAdvanced", "SamplerCustomAdvanced")
                      and node.get("mode", 0) == 0
                      and not any(key == prefix or key.startswith(prefix + ":") for prefix in self.inactive_ids)]
        selector = sampler_id.strip()
        if selector in candidates:
            return selector
        # ComfyUI API prompts expand native subgraphs into colon-qualified IDs.
        # Accept slash paths too, as well as an unambiguous container/leaf ID.
        selector = selector.replace("/", ":")
        if selector in self.graph and selector not in candidates:
            raise MetadataError(f"Sampler {selector} is muted, bypassed or unsupported; active sampler IDs: {', '.join(candidates) or 'none'}")
        if selector in candidates:
            return selector
        matches = candidates if not selector else [key for key in candidates if key.startswith(selector + ":") or key.endswith(":" + selector)]
        if len(matches) == 1:
            return matches[0]
        choices = ", ".join(matches or candidates) or "none"
        raise MetadataError(f"Choose a unique sampler_node_id; supported sampler IDs: {choices}")

    def custom_sampler_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Adapt the core advanced sampling pipeline without executing any nodes."""
        result = {"latent_image": inputs.get("latent_image")}
        adapters = (
            ("noise", {"RandomNoise": {"seed": "noise_seed"}}, ("seed",)),
            ("guider", {
                "CFGGuider": {"cfg": "cfg", "model": "model", "positive": "positive", "negative": "negative"},
                "BasicGuider": {"model": "model", "positive": "conditioning"},
            }, ("cfg", "model", "positive", "negative")),
            ("sigmas", {"BasicScheduler": {"steps": "steps", "scheduler": "scheduler", "denoise": "denoise"}}, ("steps", "scheduler", "denoise")),
        )
        for key, kinds, fields in adapters:
            try:
                link = inputs.get(key)
                node_id, kind, upstream = self.node(link, ())
                if link[1] != 0 or kind not in kinds:
                    raise MetadataError(f"Unsupported {key} node {kind} ({node_id})")
                for output, source in kinds[kind].items():
                    result[output] = upstream.get(source)
                if kind == "BasicGuider":
                    result["cfg"] = 1.0
                    self.result.issues["negative"] = "BasicGuider has no negative conditioning; restore that architecture-specific setup separately"
            except MetadataError as exc:
                for field in fields:
                    self.result.issues[field] = str(exc)
        try:
            link = inputs.get("sampler")
            seen = ()
            while True:
                node_id, kind, upstream = self.node(link, seen)
                seen = (*seen, node_id)
                if link[1] != 0:
                    raise MetadataError("Unsupported sampler output")
                if kind == "KSamplerSelect":
                    result["sampler_name"] = upstream.get("sampler_name")
                    break
                if kind == "DetailDaemonSamplerNode":
                    self.result.issues["sampler_effects"] = "Detail Daemon modifies sampling; recovered base sampler settings do not reproduce this effect"
                    link = upstream.get("sampler")
                    continue
                raise MetadataError(f"Unsupported sampler node {kind} ({node_id})")
        except MetadataError as exc:
            self.result.issues["sampler_name"] = str(exc)
        return result

    def read(self, sampler_id: str) -> GenerationMetadata:
        sampler_id = self.select_sampler(sampler_id)
        node = self.graph[sampler_id]
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            raise MetadataError("Malformed sampler inputs")
        self.result.notes.append(f"ComfyUI API graph; sampler {sampler_id} ({node['class_type']}).")
        if node["class_type"] == "SamplerCustomAdvanced":
            inputs = self.custom_sampler_inputs(inputs)
        for output, key in {"seed": "noise_seed" if node["class_type"] == "KSamplerAdvanced" else "seed", "steps": "steps", "cfg": "cfg", "sampler_name": "sampler_name", "scheduler": "scheduler"}.items():
            try:
                self.result.values[output] = self.scalar(inputs.get(key))
            except (ValueError, TypeError) as exc:
                self.result.issues[output] = str(exc)
        if node["class_type"] == "KSamplerAdvanced":
            self.result.issues["denoise"] = "KSamplerAdvanced start/end/noise settings cannot be represented by denoise alone"
        else:
            try:
                self.result.values["denoise"] = self.scalar(inputs.get("denoise", 1.0))
            except (ValueError, TypeError) as exc:
                self.result.issues["denoise"] = str(exc)
        for key in ("positive", "negative"):
            try:
                self.result.values[key] = self.text(inputs.get(key))
            except (ValueError, TypeError) as exc:
                self.result.issues[key] = str(exc)
        try:
            self.model(inputs.get("model"))
        except (ValueError, TypeError) as exc:
            self.result.issues["model"] = str(exc)
            self.result.issues["loras"] = "Model/LoRA chain could not be fully recovered"
        expected_clip = [(name, clip) for name, _, clip in self.result.loras if clip != 0]
        for polarity in ("positive", "negative"):
            if polarity in self.result.issues:
                continue
            try:
                _, _, encoder = self.node(inputs.get(polarity), ())
                if "clip" in encoder:
                    actual_clip = self.clip_loras(encoder["clip"])
                    if actual_clip != expected_clip:
                        self.result.issues["loras"] = "Model and prompt CLIP branches use different LoRAs; explicitly choose a reusable stack with a loras override"
            except MetadataError as exc:
                self.result.issues[polarity] = str(exc)
        try:
            _, kind, latent = self.node(inputs.get("latent_image"), ())
            if kind in ("EmptyLatentImage", "EmptySD3LatentImage"):
                for key in ("width", "height"):
                    self.result.values[key] = self.scalar(latent.get(key))
            else:
                self.result.notes.append("Latent dimensions unavailable; using image dimensions. Restore the original latent/img2img setup separately.")
        except MetadataError:
            self.result.notes.append("Latent dimensions unavailable; using image dimensions.")
        return self.result


def _parameter_fields(text: str) -> dict[str, str]:
    """Split multiline parameters without splitting JSON objects or quoted names."""
    parts = []
    start = 0
    depth = 0
    quoted = False
    escaped = False
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    fields = {}
    for part in parts:
        match = re.match(r"^\s*([\w ]+):\s*([\s\S]*)$", part)
        if match:
            fields[match[1].strip()] = match[2].strip()
    return fields


def _parameter_loras(fields: dict[str, str], result: GenerationMetadata) -> None:
    for key in ("positive", "negative"):
        result.values[key], entries = split_lora_tags(result.values[key])
        result.loras.extend(entries)
    try:
        hashes = json.loads(fields.get("Hashes", "{}"))
        resources = json.loads(fields.get("Civitai resources", "[]"))
        if not isinstance(hashes, dict) or not isinstance(resources, list):
            raise ValueError("Invalid resource containers")
    except (ValueError, TypeError) as exc:
        result.issues["loras"] = f"Malformed embedded resource metadata: {exc}"
        return
    names = [(key[5:], value) for key, value in hashes.items() if key.upper().startswith("LORA:")]
    weighted = [item for item in resources if isinstance(item, dict) and "weight" in item]
    result.resource_hints = [{"name": name, "hash": value} for name, value in names]
    if result.loras:
        if len(names) == 1 and len(weighted) == 1:
            strength = finite_number(weighted[0]["weight"])
            single = (names[0][0], strength, strength)
            if len(result.loras) > 1 and all(entry == single for entry in result.loras):
                result.loras = [single]
                result.notes.append("Repeated identical prompt tags collapsed to the single LoRA recorded in resource metadata.")
        return
    # Without a catalog there is no general mapping between a hash name and
    # a Civitai version ID. One name and one resource are unambiguous; multiple
    # resources must not be paired by their incidental JSON ordering.
    if len(names) == 1 and len(weighted) == 1:
        strength = finite_number(weighted[0]["weight"])
        result.loras.append((names[0][0], strength, strength))
        result.resource_hints[0].update(weighted[0])
        result.notes.append("LoRA name recovered from Hashes and its sole resource weight; separate CLIP strength was not saved, so model strength is used for both.")
    elif names or weighted:
        result.issues["loras"] = "LoRA resource names/weights cannot be paired unambiguously without a catalog; provide an explicit loras override"


def parse_parameters(text: str) -> GenerationMetadata:
    match = re.search(r"^Steps:\s*\d+.*$", text, re.M)
    if not match:
        raise MetadataError("No supported A1111/Forge generation parameters found")
    prompt = text[:match.start()].strip()
    positive, separator, negative = prompt.partition("Negative prompt:")
    fields = _parameter_fields(text[match.start():])
    result = GenerationMetadata(notes=["A1111/Forge parameters."])
    result.values.update(positive=positive.strip(), negative=negative.strip() if separator else "")
    for output, key in {"seed": "Seed", "steps": "Steps", "cfg": "CFG scale", "sampler_name": "Sampler", "scheduler": "Schedule type", "checkpoint_name": "Model", "denoise": "Denoising strength"}.items():
        if key in fields:
            result.values[output] = fields[key].strip().strip('"')
    result.values.setdefault("denoise", 1.0)
    size = re.fullmatch(r"(\d+)x(\d+)", fields.get("Size", "").strip())
    if size:
        result.values.update(width=int(size[1]), height=int(size[2]))
    sampler = str(result.values.get("sampler_name", "")).lower().strip()
    for suffix, scheduler in (
        (" sgm uniform", "sgm_uniform"), (" sgm_uniform", "sgm_uniform"),
        (" karras", "karras"), (" exponential", "exponential"),
        (" simple", "simple"), ("_simple", "simple"),
        (" normal", "normal"), ("_normal", "normal"), ("_sgm_uniform", "sgm_uniform"),
        (" ddim uniform", "ddim_uniform"),
        (" beta", "beta"), (" linear quadratic", "linear_quadratic"),
    ):
        if sampler.endswith(suffix):
            sampler = sampler[:-len(suffix)]
            result.values.setdefault("scheduler", scheduler)
            break
    result.values["sampler_name"] = SAMPLERS.get(sampler, sampler)
    if "scheduler" in result.values:
        result.values["scheduler"] = result.values["scheduler"].lower()
        if result.values["scheduler"] == "automatic":
            result.values.pop("scheduler")
    if "scheduler" not in result.values:
        result.issues["scheduler"] = "A1111 scheduler is unspecified/Automatic; choose an explicit ComfyUI scheduler"
    for key in ("Clip skip", "Hires upscale", "Hires steps", "Hires upscaler"):
        if key in fields:
            result.notes.append(f"Restore separately: {key}: {fields[key]}")
    _parameter_loras(fields, result)
    return result


def inactive_workflow_nodes(workflow: dict[str, Any]) -> set[str]:
    """Map muted/bypassed instances and nested nodes to API-qualified IDs."""
    inactive: set[str] = set()
    definitions = {str(item["id"]): item for item in workflow.get("definitions", {}).get("subgraphs", []) if isinstance(item, dict) and "id" in item}
    count = 0

    def visit(container: dict[str, Any], prefix: str, ancestors: tuple[str, ...]) -> None:
        nonlocal count
        for node in container.get("nodes", []):
            count += 1
            if count > 10000 or len(ancestors) > 100:
                raise MetadataError("Workflow subgraph traversal limit exceeded")
            if not isinstance(node, dict) or "id" not in node:
                continue
            node_id = prefix + str(node["id"])
            if node.get("mode", 0) != 0:
                inactive.add(node_id)
                continue
            kind = node.get("type")
            if kind in definitions:
                if kind in ancestors:
                    raise MetadataError("Cyclic workflow subgraph definition")
                visit(definitions[kind], node_id + ":", (*ancestors, kind))

    visit(workflow, "", ())
    return inactive


def extract_generation_metadata(
    fields: dict[str, Any], sampler_id: str = "", prefer_saved_image_metadata: bool = True,
) -> GenerationMetadata:
    parameters = fields.get("parameters") or fields.get("comment")
    saved_text = isinstance(parameters, str) and bool(parameters.strip()) and not parameters.lstrip().startswith("{")
    recovery_notes = []
    if prefer_saved_image_metadata and saved_text:
        try:
            result = parse_parameters(parameters)
            result.notes.append("Source: saved image generation parameters (preferred).")
            if sampler_id.strip():
                result.notes.append("sampler_node_id is ignored while using saved image generation parameters.")
            return result
        except (ValueError, TypeError) as exc:
            recovery_notes.append(f"ERROR: Saved image metadata could not be parsed: {exc}; trying workflow metadata.")
    prompt = fields.get("prompt")
    workflow = _json_object(fields["workflow"]) if fields.get("workflow") else None
    if prompt:
        try:
            graph = _json_object(prompt)
        except (ValueError, TypeError) as exc:
            raise MetadataError(f"Malformed embedded prompt: {exc}") from exc
        result = GraphReader(graph, inactive_workflow_nodes(workflow) if workflow else None).read(sampler_id.strip())
    elif isinstance(parameters, str) and parameters.lstrip().startswith("{"):
        result = GraphReader(_json_object(parameters), inactive_workflow_nodes(workflow) if workflow else None).read(sampler_id.strip())
    elif workflow:
        result = GraphReader(workflow_to_prompt(workflow)).read(sampler_id.strip())
        result.notes.insert(0, "UI workflow fallback: only known core widget layouts are supported; saved widget values may differ from executed values.")
    elif saved_text:
        result = parse_parameters(parameters)
        result.notes.append("Source: saved image generation parameters; no workflow metadata available.")
    else:
        raise MetadataError("Image contains no supported generation metadata")
    result.notes.extend(recovery_notes)
    return result


def workflow_to_prompt(workflow: dict[str, Any]) -> dict[str, Any]:
    """Decode only known core widget layouts; preserve links to unknown nodes."""
    nodes = workflow.get("nodes")
    links = workflow.get("links", [])
    if not isinstance(nodes, list) or not isinstance(links, list) or len(nodes) > 10000:
        raise MetadataError("Malformed or excessively large UI workflow")
    link_map = {}
    for link in links:
        if isinstance(link, list) and len(link) >= 5:
            link_map[str(link[0])] = [str(link[1]), link[2]]
    layouts = {
        "CheckpointLoaderSimple": ["ckpt_name"],
        "UNETLoader": ["unet_name", "weight_dtype"],
        "LoraLoader": ["lora_name", "strength_model", "strength_clip"],
        "LoraLoaderModelOnly": ["lora_name", "strength_model"],
        "CLIPTextEncode": ["text"],
        "EmptyLatentImage": ["width", "height", "batch_size"],
        "EmptySD3LatentImage": ["width", "height", "batch_size"],
        "KSampler": ["seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler", "denoise"],
        "PrimitiveNode": ["value"],
        "PrimitiveInt": ["value"], "PrimitiveFloat": ["value"],
        "PrimitiveString": ["value"], "PrimitiveStringMultiline": ["value"],
    }
    graph = {}
    for node in nodes:
        if not isinstance(node, dict) or "id" not in node:
            raise MetadataError("Malformed workflow node")
        kind = node.get("type", "")
        widgets = node.get("widgets_values", [])
        inputs = {}
        layout = layouts.get(kind)
        if node.get("mode", 0) != 0:
            kind = "Unsupported muted/bypassed " + kind
        elif layout is not None:
            if not isinstance(widgets, list):
                raise MetadataError(f"Unsupported widget layout for {kind}")
            if kind == "KSampler" and len(widgets) == 6:
                layout = [key for key in layout if key != "control_after_generate"]
            for key, value in zip(layout, widgets):
                inputs[key] = value
        for slot in node.get("inputs", []):
            if not isinstance(slot, dict) or not isinstance(slot.get("name"), str):
                raise MetadataError("Malformed workflow input")
            if slot.get("link") is not None:
                inputs[slot["name"]] = link_map.get(str(slot["link"]), ["missing", 0])
        graph[str(node["id"])] = {"class_type": kind, "inputs": inputs}
    return graph
