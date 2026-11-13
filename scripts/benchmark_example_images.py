#!/usr/bin/env python3
"""Reproducible A/B benchmark for example-image downloads.

The benchmark keeps real model files read-only and runs every candidate in a
pinned settings directory whose cache, sidecars and example folder are copies
under ``--workdir``. It selects one model subset from the user's cache/sidecars,
then runs the same subset against:

* ``serial``: the pre-pipeline tree (or any tree), model concurrency forced to 1
* ``new-serial``: the current tree with the model pipeline disabled
* ``pipeline``: the current tree, model concurrency 2, AIMD ceiling = base 6
* ``aimd``: the current tree, model concurrency 2, AIMD ceiling 8

Each run starts from an empty examples directory and a fresh cache/sidecar
copy. The script never writes to the real settings directory or model library.

The A/B subset skips models outside ``folder_paths`` roots: those resolve their
sidecar alongside the model file, so the sandbox sidecar copy is not used and
the old tree cannot read their media at all. Pass ``--any-root`` to include
them (the ``--full`` selection always includes every model).

CDN cache control
-----------------
Civitai's image CDN is a Cloudflare edge cache: the 301 that maps a rendition
to its blob is stored for 48 h and the blob itself for 1 h. The same URL set
therefore gets much faster after its first visit (measured: 2.8 req/s cold vs
6.6 req/s warm at concurrency 6). Because every mode of this harness requests
the *same* URLs, an un-warmed baseline is slower than every later mode and the
A/B reports a fake gain.

``--warm-cache`` (default for ``compare``) fetches every URL the mode will
request *before* timing starts, then probes a sample and records the edge hit
ratio in the result. A run whose probe hit ratio is below 1.0 is reported as a
cache warning instead of being silently mixed into the median. A single ``run``
(e.g. the full-library validation) skips warming unless the flag is passed, so
it does not pay for a second full download. Use ``--no-warm-cache`` only to
measure the edge state as-is; read the per-run table rather than the medians in
that mode.

``reverify``
------------
``compare`` only measures the download phase. A large library whose images are
already on disk spends its time in per-model bookkeeping instead, which the
download benchmark cannot see. The ``reverify`` command populates the sandbox
examples tree from the selected sidecars and times a library-wide
``force=True`` pass (the UI's *Re-process All*) or a ``force=False`` skip pass,
reporting milliseconds per model.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKDIR = REPO_ROOT / ".tmp" / "example-images-bench"
REAL_CONFIG = Path.home() / ".config" / "ComfyUI-LoRA-Manager"
MODES = {
    # Old tree, historical serial baseline.
    "serial": {"model_concurrency": 1, "probe_ceiling": 6},
    # New tree with the model pipeline disabled: isolates the pipeline gain
    # from the earlier per-model media-pool gain.
    "new-serial": {"model_concurrency": 1, "probe_ceiling": 6},
    "pipeline": {"model_concurrency": 2, "probe_ceiling": 6},
    "aimd": {"model_concurrency": 2, "probe_ceiling": 8},
}

# Rendition width used both in the sandbox settings and in the cache warm-up.
# Pinned so the warm-up requests exactly the URLs the server will request.
DEFAULT_IMAGE_WIDTH = 800
# Number of URLs re-fetched after the warm-up pass to verify the edge state.
CACHE_PROBE_SAMPLE = 24
# Names of the URLs each tree would request, resolved inside that tree so the
# warm-up cannot drift from the code under test.
_URL_DUMP_SCRIPT = r"""
import json, re, sys

payload = json.load(sys.stdin)
width = payload["width"]
images = payload["images"]

try:
    from py.utils.civitai_utils import build_civitai_media_url as build
    builder = "civitai_utils.build_civitai_media_url"
except Exception:
    build = None
    builder = "legacy.get_civitai_optimized_url"


def legacy(url):
    match = re.match(r"(https://image\.civitai\.com/[^/]+/[^/]+)", url)
    return f"{match.group(1)}/optimized=true" if match else url


urls = []
for item in images:
    url = (item.get("url") or "").strip()
    if not url:
        continue
    if build is not None:
        urls.append(build(url, item.get("type"), width=width, optimize=True) or url)
    else:
        urls.append(legacy(url))

json.dump({"builder": builder, "urls": urls}, sys.stdout)
"""

_IMAGE_INDEX_CACHE: dict[str, dict[str, list[dict[str, Any]]]] = {}
# The pre-`build_civitai_media_url` helper matched the first two path segments
# and replaced everything after them with `optimized=true`.
_LEGACY_URL_PATTERN = re.compile(r"(https://image\.civitai\.com/[^/]+/[^/]+)")


def _log(message: str) -> None:
    print(message, flush=True)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _http_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 30.0):
    data = None
    headers = {}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for_server(base_url: str, proc: subprocess.Popen, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited with code {proc.returncode}")
        try:
            _http_json(base_url + "/api/lm/example-images-status", timeout=3.0)
            return
        except Exception as exc:  # noqa: BLE001 - startup polling
            last_error = exc
            time.sleep(0.5)
    raise TimeoutError(f"server did not become ready: {last_error}")


def _configured_model_roots() -> list[Path]:
    """Return the ``folder_paths`` roots from the real settings file."""

    try:
        settings = _read_json(REAL_CONFIG / "settings.json")
    except (OSError, ValueError):
        return []
    roots: list[Path] = []
    for values in (settings.get("folder_paths") or {}).values():
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str) and value.strip():
                roots.append(Path(os.path.normcase(os.path.abspath(value))))
    return roots


def _is_under_roots(path: Path, roots: list[Path]) -> bool:
    """Return whether *path* lives under one of *roots* (empty = allow all)."""

    if not roots:
        return True
    candidate = os.path.normcase(os.path.abspath(str(path)))
    for root in roots:
        root_text = str(root)
        if candidate == root_text or candidate.startswith(root_text + os.sep):
            return True
    return False


def _sidecar_image_index(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Return ``{sha256: [{"url", "type"}]}`` for every sidecar under *root*.

    Only the media list is kept, so a full-library index costs far less memory
    than parsing the sidecars into dicts and retaining them. The index is
    memoized per root: ``compare`` builds it once for four modes and repeats.
    """

    key = str(root)
    cached = _IMAGE_INDEX_CACHE.get(key)
    if cached is not None:
        return cached

    index: dict[str, list[dict[str, Any]]] = {}
    for path in root.rglob("*.metadata.json"):
        try:
            payload = _read_json(path)
        except (OSError, ValueError):
            continue
        sha = str(payload.get("sha256") or "").lower()
        if len(sha) != 64:
            continue
        civitai = payload.get("civitai") or {}
        media = []
        for image in civitai.get("images") or []:
            if not isinstance(image, dict):
                continue
            url = (image.get("url") or "").strip()
            if url:
                media.append({"url": url, "type": image.get("type")})
        index.setdefault(sha, media)

    _IMAGE_INDEX_CACHE[key] = index
    _log(f"indexed media for {len(index)} sidecars under {root}")
    return index


def _selected_images(workdir: Path, selection: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the media entries the selected models will ask the server for."""

    index = _sidecar_image_index(workdir / "sidecars")
    images: list[dict[str, Any]] = []
    for model in selection["models"]:
        images.extend(index.get(str(model["sha256"]).lower(), []))
    return images


def _legacy_media_url(url: str) -> str:
    """Reproduce the pre-``build_civitai_media_url`` rendition URL."""

    match = _LEGACY_URL_PATTERN.match(url)
    return f"{match.group(1)}/optimized=true" if match else url


def _tree_media_urls(
    tree: Path, images: list[dict[str, Any]], width: int
) -> tuple[list[str], str]:
    """Resolve the URLs *tree* would request, using that tree's own builder.

    The builder runs in a subprocess with ``cwd=tree``: the old and new trees
    define the same module names, so importing both in one process would alias
    whichever was imported first. If the tree cannot be loaded, the harness
    falls back to the frozen legacy rewrite and says so.
    """

    if not images:
        return [], "none"
    payload = json.dumps({"width": width, "images": images})
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _URL_DUMP_SCRIPT],
            cwd=str(tree),
            input=payload,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            return list(data["urls"]), str(data.get("builder") or "unknown")
        _log(f"warning: URL builder in {tree} failed: {proc.stderr.strip()[-300:]}")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        _log(f"warning: URL builder in {tree} failed: {exc}")
    return [_legacy_media_url(str(item.get("url") or "")) for item in images], "legacy-fallback"


async def _http_pass(
    urls: list[str], concurrency: int = 6
) -> dict[str, Any]:
    """Fetch *urls* concurrently and summarize the edge cache state."""

    import aiohttp

    stats: dict[str, Any] = {
        "requests": len(urls),
        "hit": 0,
        "miss": 0,
        "other": 0,
        "errors": 0,
        "bytes": 0,
    }
    latencies: list[float] = []
    if not urls:
        stats["elapsed_seconds"] = 0.0
        stats["latency_p50_ms"] = 0.0
        return stats

    semaphore = asyncio.Semaphore(max(1, concurrency))
    timeout = aiohttp.ClientTimeout(total=120)
    connector = aiohttp.TCPConnector(limit=max(1, concurrency))

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:

        async def fetch(url: str) -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    async with session.get(url, allow_redirects=True) as response:
                        body = await response.read()
                except Exception:  # noqa: BLE001 - a failed probe must not abort the run
                    stats["errors"] += 1
                    return
                state = (response.headers.get("cf-cache-status") or "").upper()
                if state == "HIT":
                    stats["hit"] += 1
                elif state == "MISS":
                    stats["miss"] += 1
                else:
                    stats["other"] += 1
                stats["bytes"] += len(body)
                latencies.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        await asyncio.gather(*(fetch(url) for url in urls))
        stats["elapsed_seconds"] = round(time.perf_counter() - started, 3)

    if latencies:
        latencies.sort()
        stats["latency_p50_ms"] = round(latencies[len(latencies) // 2], 1)
    else:
        stats["latency_p50_ms"] = 0.0
    return stats


def _warm_cdn_cache(
    urls: list[str],
    *,
    concurrency: int = 6,
    probe_sample: int = CACHE_PROBE_SAMPLE,
) -> dict[str, Any]:
    """Warm every URL a run will request, then verify the edge is hot.

    Civitai's CDN caches both the rendition redirect (48 h) and the blob (1 h),
    so an un-warmed first pass is ~2.3x slower than every later pass. Warming
    outside the timed run and probing afterwards makes every mode comparable
    and records whether that assumption actually held.
    """

    if not urls:
        return {"enabled": False, "hit_ratio": None, "urls": 0}

    _log(f"warming {len(urls)} CDN URLs before timing ...")
    warm = asyncio.run(_http_pass(urls, concurrency))
    _log(
        f"warm-up: {warm['elapsed_seconds']:.1f}s "
        f"{warm['bytes'] / 1e6:.1f} MB "
        f"(hit={warm['hit']} miss={warm['miss']} other={warm['other']} "
        f"errors={warm['errors']})"
    )

    sample = (
        list(urls)
        if len(urls) <= probe_sample
        else random.Random(0).sample(urls, probe_sample)
    )
    probe = asyncio.run(_http_pass(sample, concurrency))
    hit_ratio = probe["hit"] / max(probe["requests"], 1)
    if hit_ratio < 1.0:
        _log(
            f"WARNING: only {probe['hit']}/{probe['requests']} probed URLs are edge-cached; "
            "this run is not cache-neutral"
        )
    return {
        "enabled": True,
        "urls": len(urls),
        "warmup": warm,
        "probe": probe,
        "hit_ratio": round(hit_ratio, 3),
    }


def _index_sidecars() -> tuple[Path, dict[str, Path]]:
    """Index real centralized sidecars by sha256 without touching settings.

    Sidecar names mirror model names, but the authoritative link is the
    ``sha256`` inside the JSON. Building the map once is cheaper than resolving
    each path through the app (which also may initialize settings).
    """

    real_root = REAL_CONFIG / "sidecars"
    if not real_root.is_dir():
        raise FileNotFoundError(f"real sidecar root missing: {real_root}")
    index: dict[str, Path] = {}
    for path in real_root.rglob("*.metadata.json"):
        try:
            payload = _read_json(path)
        except (OSError, ValueError):
            continue
        sha = str(payload.get("sha256") or "").lower()
        if len(sha) == 64:
            index.setdefault(sha, path)
    _log(f"indexed {len(index)} sidecars under {real_root}")
    return real_root, index


def _copy_model_cache(source_cache: Path, dest_cache: Path) -> None:
    shutil.copytree(source_cache, dest_cache, dirs_exist_ok=True)


def prepare(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    cache_source = REAL_CONFIG / "cache"
    cache_dest = workdir / "cache"
    if cache_dest.exists():
        shutil.rmtree(cache_dest)
    _log(f"copying cache -> {cache_dest}")
    _copy_model_cache(cache_source, cache_dest)

    db_path = cache_dest / "model" / "comfyui.sqlite"
    if args.full:
        # Full production-shaped run: all example-capable model types, no
        # sidecar/image filters, and a complete sidecar copy. The download
        # manager's explicit target path then processes the same 987 models
        # as the normal UI run.
        connection = sqlite3.connect(str(db_path))
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "select model_type, file_path, file_name, model_name, sha256 "
            "from models where model_type in ('lora','checkpoint','embedding')"
        ).fetchall()
        connection.close()
        selected = []
        for row in rows:
            sha = (row["sha256"] or "").lower()
            if len(sha) != 64:
                continue
            selected.append(
                {
                    "sha256": sha,
                    "model_name": row["model_name"],
                    "model_type": row["model_type"],
                    "file_path": row["file_path"],
                    "sidecar": "",
                    "image_count": 0,
                }
            )
        if not selected:
            raise RuntimeError("no models found for full benchmark")
        sidecar_dest = workdir / "sidecars"
        if sidecar_dest.exists():
            shutil.rmtree(sidecar_dest)
        _log(f"copying full sidecars -> {sidecar_dest}")
        shutil.copytree(REAL_CONFIG / "sidecars", sidecar_dest)
        selection = {
            "created_at": time.time(),
            "models": selected,
            "model_count": len(selected),
            "total_images": 0,
            "full": True,
        }
        _write_json(workdir / "selection.json", selection)
        _log(f"selected {len(selected)} models for full run -> {workdir / 'selection.json'}")
        return

    real_sidecar_root, sidecar_by_hash = _index_sidecars()
    if not db_path.is_file():
        raise FileNotFoundError(f"model cache missing: {db_path}")

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "select model_type, file_path, file_name, model_name, sha256, from_civitai, civitai_deleted from models"
    ).fetchall()
    connection.close()

    model_roots = [] if args.any_root else _configured_model_roots()

    selected: list[dict[str, Any]] = []
    total_images = 0
    outside_roots = 0
    for row in rows:
        if len(selected) >= args.count or total_images >= args.images:
            break
        if row["model_type"] not in {"lora", "checkpoint"}:
            continue
        if not row["from_civitai"] or row["civitai_deleted"]:
            continue
        sha = (row["sha256"] or "").lower()
        if len(sha) != 64:
            continue
        file_path = Path(row["file_path"] or "")
        if not file_path.is_file():
            continue
        if not _is_under_roots(file_path, model_roots):
            # ``extra_folder_paths`` models resolve their sidecar alongside the
            # model file, so the sandbox sidecar copy is not used and the old
            # tree cannot read their media at all. Exclude them from the A/B
            # unless --any-root asks for them.
            outside_roots += 1
            continue
        metadata_path = sidecar_by_hash.get(sha)
        if metadata_path is None or not metadata_path.is_file():
            continue
        try:
            payload = _read_json(metadata_path)
        except (OSError, ValueError):
            continue
        civitai = payload.get("civitai") or {}
        images = civitai.get("images") or []
        urls = [
            image.get("url")
            for image in images
            if isinstance(image, dict)
            and image.get("url")
            and image.get("type") != "video"
        ]
        if not (args.min_images <= len(urls) <= args.max_images):
            continue
        if not all("image.civitai.com" in url for url in urls):
            continue
        try:
            relative = metadata_path.relative_to(real_sidecar_root)
        except ValueError:
            continue
        selected.append(
            {
                "sha256": sha,
                "model_name": row["model_name"],
                "model_type": row["model_type"],
                "file_path": str(file_path),
                "sidecar": str(relative),
                "image_count": len(urls),
            }
        )
        total_images += len(urls)

    if not selected:
        raise RuntimeError("no models matched the benchmark filters")

    sidecar_dest = workdir / "sidecars"
    if sidecar_dest.exists():
        shutil.rmtree(sidecar_dest)
    for model in selected:
        source = real_sidecar_root / model["sidecar"]
        target = sidecar_dest / model["sidecar"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    selection = {
        "created_at": time.time(),
        "models": selected,
        "model_count": len(selected),
        "total_images": total_images,
    }
    _write_json(workdir / "selection.json", selection)
    _log(
        f"selected {len(selected)} models / {total_images} images "
        f"-> {workdir / 'selection.json'}"
    )
    if outside_roots:
        _log(
            f"skipped {outside_roots} models outside folder_paths roots "
            "(their sidecars resolve alongside the model file, which the old "
            "tree cannot read; pass --any-root to include them)"
        )


def _build_settings(
    run_dir: Path,
    examples_path: Path,
    *,
    model_concurrency: int,
    probe_ceiling: int,
    image_width: int = DEFAULT_IMAGE_WIDTH,
) -> dict[str, Any]:
    """Write deterministic sandbox settings for one run.

    The rendition width is pinned here (and used by the cache warm-up) so a
    user's own ``settings.json`` cannot silently change the URL set between
    runs or between the warm-up and the timed run.
    """

    source = REAL_CONFIG / "settings.json"
    settings = _read_json(source)
    settings.update(
        {
            "use_portable_settings": False,
            "example_images_path": str(examples_path),
            "sidecar_storage_mode": "centralized",
            "sidecar_storage_path": str(run_dir / "sidecars"),
            "auto_download_example_images": False,
            "optimize_example_images": True,
            "example_images_download_concurrency": 6,
            "example_images_download_max_concurrency": probe_ceiling,
            "example_images_model_concurrency": model_concurrency,
            "example_images_max_width": image_width,
            "example_images_video_max_width": 450,
        }
    )
    return settings


def _media_stats(root: Path) -> tuple[int, int]:
    files = 0
    size = 0
    if not root.exists():
        return files, size
    for current, _dirs, names in os.walk(root):
        for name in names:
            if (
                name.startswith(".lm-examples-complete")
                or name == ".download_progress.json"
                or name == ".lm-examples-backfill"
            ):
                continue
            path = Path(current) / name
            try:
                size += path.stat().st_size
                files += 1
            except OSError:
                pass
    return files, size


def _count_log_events(log_path: Path) -> dict[str, int]:
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    return {
        "rate_limited": text.count("Rate limited (429)"),
        "not_found": text.count("File not found"),
        "errors": text.count("ERROR"),
        "probe_steps": text.count("Probing media concurrency above base"),
    }


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _run_download_pass(
    tree: Path,
    run_dir: Path,
    port: int,
    payload: dict[str, Any],
    *,
    label: str,
    timeout: float,
) -> tuple[float, dict[str, Any], float, Path]:
    """Start *tree* and time one ``download-example-images`` pass.

    Returns ``(elapsed_seconds, status, startup_seconds, log_path)``. The timer
    starts after the POST is accepted and stops when the manager reports a
    terminal state, so server startup and setting up the sandbox are excluded.
    """

    log_path = run_dir / "server.log"
    log_handle = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env["LORA_MANAGER_SETTINGS_DIR"] = str(run_dir)
    env["PYTHONUNBUFFERED"] = "1"
    command = [
        sys.executable,
        "standalone.py",
        "--port",
        str(port),
        "--settings-path",
        str(run_dir),
    ]
    _log(f"[{label}] starting {tree} on :{port}")
    proc = subprocess.Popen(
        command,
        cwd=str(tree),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
    )
    base_url = f"http://127.0.0.1:{port}"
    started = time.monotonic()
    try:
        _wait_for_server(base_url, proc)
        ready = time.monotonic()
        response = _http_json(base_url + "/api/lm/download-example-images", payload)
        if not response.get("success"):
            raise RuntimeError(f"{label} rejected: {response}")

        pass_start = time.monotonic()
        deadline = pass_start + timeout
        status: dict[str, Any] = {}
        while time.monotonic() < deadline:
            polled = _http_json(base_url + "/api/lm/example-images-status")
            status = polled.get("status") or {}
            state = status.get("status")
            if not polled.get("is_downloading") and state in {
                "completed",
                "stopped",
                "error",
            }:
                break
            time.sleep(0.5)
        else:
            raise TimeoutError(f"{label} did not finish within {timeout}s")
        return time.monotonic() - pass_start, status, ready - started, log_path
    finally:
        _terminate(proc)
        log_handle.close()


def run_once(
    tree: Path,
    workdir: Path,
    selection: dict[str, Any],
    mode: str,
    port: int,
    *,
    image_width: int = DEFAULT_IMAGE_WIDTH,
    warm_cache: bool = True,
    download_timeout: float = 2700.0,
) -> dict[str, Any]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = workdir / "runs" / f"{mode}-{stamp}-{os.getpid()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    _log(f"[{mode}] preparing {run_dir}")

    shutil.copytree(workdir / "cache", run_dir / "cache", dirs_exist_ok=True)
    shutil.copytree(workdir / "sidecars", run_dir / "sidecars", dirs_exist_ok=True)

    examples_path = workdir / "examples"
    if examples_path.exists():
        shutil.rmtree(examples_path)
    examples_path.mkdir(parents=True, exist_ok=True)

    settings = _build_settings(
        run_dir,
        examples_path,
        model_concurrency=MODES[mode]["model_concurrency"],
        probe_ceiling=MODES[mode]["probe_ceiling"],
        image_width=image_width,
    )
    _write_json(run_dir / "settings.json", settings)

    # Warm (or explicitly skip warming) the exact URLs this tree will request.
    # Civitai's edge caches the rendition redirect and the blob, so without this
    # the first mode through a URL set is 2-3x slower than every later mode.
    cache: dict[str, Any] = {"enabled": False, "hit_ratio": None}
    if warm_cache:
        images = _selected_images(workdir, selection)
        urls, builder = _tree_media_urls(tree, images, image_width)
        cache = _warm_cdn_cache(urls)
        cache["builder"] = builder
    else:
        _log(
            f"[{mode}] cache warm-up disabled; the CDN state is unverified and "
            "mode order biases the comparison"
        )

    elapsed, status, startup_seconds, log_path = _run_download_pass(
        tree,
        run_dir,
        port,
        {
            "model_types": ["lora", "checkpoint", "embedding"],
            "model_hashes": [model["sha256"] for model in selection["models"]],
            "delay": 0,
            "optimize": True,
        },
        label=mode,
        timeout=download_timeout,
    )

    files, size = _media_stats(examples_path)
    logs = _count_log_events(log_path)
    return {
        "mode": mode,
        "tree": str(tree),
        "commit": subprocess.check_output(
            ["git", "-C", str(tree), "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip(),
        "dirty": subprocess.run(
            ["git", "-C", str(tree), "diff", "--quiet"], check=False
        ).returncode
        != 0,
        "model_count": selection["model_count"],
        "total_images": selection["total_images"],
        "elapsed_seconds": round(elapsed, 3),
        "startup_seconds": round(startup_seconds, 3),
        "status": status.get("status"),
        "total": status.get("total"),
        "completed": status.get("completed"),
        "failed_count": len(status.get("failed_models") or []),
        "files": files,
        "bytes": size,
        "cache": cache,
        **logs,
        "run_dir": str(run_dir),
    }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _cache_hit_ratio(result: dict[str, Any]) -> float | None:
    """Return the verified edge hit ratio, or None when it was not measured."""

    cache = result.get("cache") or {}
    if not cache.get("enabled"):
        return None
    ratio = cache.get("hit_ratio")
    return None if ratio is None else float(ratio)


def compare(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).resolve()
    selection_path = workdir / "selection.json"
    if not selection_path.is_file():
        prepare(args)
    selection = _read_json(selection_path)

    old_tree = Path(args.old_tree).resolve()
    new_tree = Path(args.new_tree).resolve()
    if not (old_tree / "standalone.py").is_file():
        _log(f"creating old worktree at {old_tree} from {args.old_ref}")
        subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "worktree",
                "add",
                "--detach",
                str(old_tree),
                args.old_ref,
            ],
            check=True,
        )
    if not (old_tree / "standalone.py").is_file():
        raise FileNotFoundError(f"old tree missing standalone.py: {old_tree}")
    if not (new_tree / "standalone.py").is_file():
        raise FileNotFoundError(f"new tree missing standalone.py: {new_tree}")

    plans = [
        ("serial", old_tree),
        ("new-serial", new_tree),
        ("pipeline", new_tree),
        ("aimd", new_tree),
    ]
    results: list[dict[str, Any]] = []
    port = args.port
    for repeat in range(args.repeats):
        order = plans if repeat % 2 == 0 else list(reversed(plans))
        for mode, tree in order:
            _log(f"=== repeat {repeat + 1}/{args.repeats} mode={mode} ===")
            result = run_once(
                tree,
                workdir,
                selection,
                mode,
                port,
                image_width=args.image_width,
                warm_cache=args.warm_cache,
                download_timeout=args.download_timeout,
            )
            result["repeat"] = repeat + 1
            results.append(result)
            port += 1
            cache = result.get("cache") or {}
            _log(
                f"[{mode}] {result['elapsed_seconds']:.1f}s "
                f"{result['files']} files {result['bytes'] / 1_000_000:.1f} MB "
                f"completed={result['completed']}/{result['total']} "
                f"429={result['rate_limited']} "
                f"cache={cache.get('hit_ratio', 1.0):.0%}"
            )

    summary: dict[str, Any] = {"selection": selection, "results": results, "modes": {}}
    for mode in MODES:
        rows = [row for row in results if row["mode"] == mode]
        if not rows:
            continue
        clean = 0
        for row in rows:
            ratio = _cache_hit_ratio(row)
            if ratio is not None and ratio >= 0.999:
                clean += 1
        elapsed = _median([row["elapsed_seconds"] for row in rows])
        files = _median([float(row["files"]) for row in rows])
        size = _median([float(row["bytes"]) for row in rows])
        summary["modes"][mode] = {
            "runs": len(rows),
            "cache_verified_runs": sum(
                1 for row in rows if _cache_hit_ratio(row) is not None
            ),
            "cache_clean_runs": clean if args.warm_cache else None,
            "median_elapsed_seconds": round(elapsed, 3),
            "median_files": int(files),
            "median_bytes": int(size),
            "rate_limited": sum(row["rate_limited"] for row in rows),
            "not_found": sum(row["not_found"] for row in rows),
            "probe_steps": sum(row.get("probe_steps", 0) for row in rows),
        }

    old_baseline = summary["modes"].get("serial", {}).get("median_elapsed_seconds")
    new_baseline = summary["modes"].get("new-serial", {}).get("median_elapsed_seconds")
    for mode, data in summary["modes"].items():
        if old_baseline:
            data["speedup_vs_old_serial"] = round(
                old_baseline / data["median_elapsed_seconds"], 3
            )
        if new_baseline:
            data["speedup_vs_new_serial"] = round(
                new_baseline / data["median_elapsed_seconds"], 3
            )

    output = workdir / "results.json"
    _write_json(output, summary)

    # Per-run table first: with --no-warm-cache the first run through a URL set
    # is cold and the medians are not comparable, so the raw runs must be
    # readable without opening results.json.
    _log("")
    _log("repeat mode       wall_s  files  MB     429  404  probe  cache")
    for row in results:
        ratio = _cache_hit_ratio(row)
        cache_text = "  cold" if ratio is None else f"{ratio:>6.0%}"
        _log(
            f"{row.get('repeat', 0):<6} {row['mode']:<10} "
            f"{row['elapsed_seconds']:>7.1f} "
            f"{row['files']:>6} "
            f"{row['bytes'] / 1_000_000:>6.1f} "
            f"{row['rate_limited']:>5} {row['not_found']:>4} "
            f"{row.get('probe_steps', 0):>6} "
            f"{cache_text}"
        )

    _log("")
    _log("mode       median_s  speedup  files  MB      429  404  probe  clean")
    for mode in MODES:
        data = summary["modes"].get(mode)
        if not data:
            continue
        clean = data["cache_clean_runs"]
        clean_text = "-" if clean is None else f"{clean}/{data['runs']}"
        _log(
            f"{mode:<10} {data['median_elapsed_seconds']:>9.1f} "
            f"{data.get('speedup_vs_new_serial', 0):>7.3f} "
            f"{data['median_files']:>6} "
            f"{data['median_bytes'] / 1_000_000:>7.1f} "
            f"{data['rate_limited']:>5} {data['not_found']:>4} "
            f"{data.get('probe_steps', 0):>6} "
            f"{clean_text:>5}"
        )
    if args.warm_cache and any(
        data["cache_clean_runs"] is not None
        and data["cache_clean_runs"] < data["runs"]
        for data in summary["modes"].values()
    ):
        _log("")
        _log(
            "WARNING: some runs were measured with a cold CDN edge cache. The "
            "medians are not cache-neutral; re-run with --warm-cache (default) "
            "or compare only the 'clean' runs."
        )
    if not args.warm_cache:
        _log("")
        _log(
            "NOTE: --no-warm-cache does not force cold URLs; it measures whatever "
            "state the edge happens to be in, so mode order biases the result "
            "and the medians are not comparable."
        )
    _log(f"results -> {output}")


def _cached_model_hashes(workdir: Path) -> list[str]:
    """Return every model hash in the sandbox cache copy."""

    db_path = workdir / "cache" / "model" / "comfyui.sqlite"
    if not db_path.is_file():
        return []
    connection = sqlite3.connect(str(db_path))
    try:
        rows = connection.execute(
            "select sha256 from models where model_type in ('lora','checkpoint','embedding')"
        ).fetchall()
    finally:
        connection.close()
    return [str(row[0]).lower() for row in rows if row[0]]


def _populate_examples(
    workdir: Path,
    selection: dict[str, Any],
    *,
    with_markers: bool,
    all_cached: bool = False,
) -> dict[str, int]:
    """Create an already-populated examples tree.

    Each media entry gets a placeholder file named the way the download would
    have named it, so the re-verify pass performs its real checks (folder scan,
    per-image existence stat, sidecar read) without making a single request.
    ``with_markers`` writes the completion marker an upgraded library has after
    its first pass; without it the run models a legacy library.

    ``all_cached`` populates every model in the sandbox cache instead of only
    the selected ones. The skip guard only looks at "folder has files" plus the
    marker, so this is what a fully verified library looks like to a
    ``force=False`` pass even when the sandbox has sidecars for a few models
    only.
    """

    index = _sidecar_image_index(workdir / "sidecars")
    examples = workdir / "examples"
    if examples.exists():
        shutil.rmtree(examples)
    examples.mkdir(parents=True)

    if all_cached:
        targets = [
            {"sha256": sha, "media": index.get(sha) or [{"type": None}]}
            for sha in _cached_model_hashes(workdir)
        ]
    else:
        targets = [
            {
                "sha256": str(model["sha256"]).lower(),
                "media": index.get(str(model["sha256"]).lower()) or [],
            }
            for model in selection["models"]
        ]

    models = 0
    files = 0
    markers = 0
    for target in targets:
        sha = target["sha256"]
        media = target["media"]
        if not all_cached and not media:
            continue
        folder = examples / sha
        folder.mkdir(parents=True, exist_ok=True)
        for position, item in enumerate(media):
            extension = ".mp4" if (item.get("type") or "").lower() == "video" else ".jpeg"
            (folder / f"image_{position}{extension}").write_bytes(b"x")
            files += 1
        if with_markers:
            (folder / ".lm-examples-complete").write_text(
                json.dumps({"media_count": len(media)}) + "\n", encoding="utf-8"
            )
            markers += 1
        models += 1

    _log(
        f"populated {models} model folders, {files} placeholder media files, "
        f"{markers} completion markers"
    )
    return {"models": models, "files": files, "markers": markers}


def run_reverify(
    tree: Path,
    workdir: Path,
    *,
    force: bool,
    model_concurrency: int,
    port: int,
    model_hashes: list[str] | None = None,
    image_width: int = DEFAULT_IMAGE_WIDTH,
    download_timeout: float = 2700.0,
) -> dict[str, Any]:
    """Time a re-verify or skip pass over a populated tree.

    This is the workload of a large library whose images are already on disk:
    the download benchmark cannot see it because no media request is made.

    ``force=True`` without ``model_hashes`` mirrors the UI's global
    *Re-process All* entry: the app's force path skips a verified folder unless
    the model is on the failed list. Passing ``model_hashes`` instead models a
    per-model / bulk *Re-process*, where explicit targets always bypass the
    guard. ``reverify --global`` omits the hashes; use it with ``--full`` so
    every cached model is in scope.

    ``force=False`` mirrors *Download Missing* and must not pass hashes (which
    would mark the models as explicit targets and bypass the skip guard). The
    tree is populated for every cached model instead, which is the state the
    skip guard sees in a verified library.
    """

    label = "reverify-force" if force else "reverify-skip"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = workdir / "runs" / f"{label}-{stamp}-{os.getpid()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    _log(f"[{label}] preparing {run_dir}")

    shutil.copytree(workdir / "cache", run_dir / "cache", dirs_exist_ok=True)
    shutil.copytree(workdir / "sidecars", run_dir / "sidecars", dirs_exist_ok=True)

    examples_path = workdir / "examples"
    examples_path.mkdir(parents=True, exist_ok=True)

    settings = _build_settings(
        run_dir,
        examples_path,
        model_concurrency=model_concurrency,
        probe_ceiling=8,
        image_width=image_width,
    )
    _write_json(run_dir / "settings.json", settings)

    request: dict[str, Any] = {
        "force": force,
        "optimize": True,
        "model_types": ["lora", "checkpoint", "embedding"],
    }
    if model_hashes:
        request["model_hashes"] = model_hashes

    elapsed, status, startup_seconds, _log_path = _run_download_pass(
        tree,
        run_dir,
        port,
        request,
        label=label,
        timeout=download_timeout,
    )

    completed = int(status.get("completed") or 0)
    return {
        "mode": label,
        "force": force,
        "explicit_targets": bool(model_hashes),
        "model_concurrency": model_concurrency,
        "tree": str(tree),
        "commit": subprocess.check_output(
            ["git", "-C", str(tree), "rev-parse", "--short", "HEAD"], text=True
        ).strip(),
        "elapsed_seconds": round(elapsed, 3),
        "startup_seconds": round(startup_seconds, 3),
        "status": status.get("status"),
        "total": status.get("total"),
        "completed": completed,
        "failed_count": len(status.get("failed_models") or []),
        "ms_per_model": round(1000.0 * elapsed / completed, 2) if completed else None,
        "models_per_second": round(completed / elapsed, 2) if completed else None,
        "run_dir": str(run_dir),
    }


def reverify(args: argparse.Namespace) -> None:
    """Run the populated-tree re-verify benchmark one or more times."""

    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    if not (workdir / "selection.json").is_file():
        prepare(args)
    selection = _read_json(workdir / "selection.json")

    tree = Path(args.tree).resolve()
    if not (tree / "standalone.py").is_file():
        raise FileNotFoundError(f"tree missing standalone.py: {tree}")

    if not (workdir / "examples").is_dir() or not args.reuse_examples:
        _populate_examples(
            workdir,
            selection,
            with_markers=args.markers,
            all_cached=not args.force,
        )

    hashes = [str(model["sha256"]).lower() for model in selection["models"]]
    results: list[dict[str, Any]] = []
    port = args.port
    for repeat in range(args.repeat):
        _log(f"=== reverify {repeat + 1}/{args.repeat} force={args.force} ===")
        result = run_reverify(
            tree,
            workdir,
            force=args.force,
            model_concurrency=args.model_concurrency,
            port=port,
            model_hashes=hashes if (args.force and not args.global_run) else None,
            image_width=args.image_width,
            download_timeout=args.download_timeout,
        )
        result["repeat"] = repeat + 1
        results.append(result)
        port += 1
        _log(
            f"[{result['mode']}] {result['elapsed_seconds']:.1f}s "
            f"{result['completed']}/{result['total']} models "
            f"{result['ms_per_model']} ms/model "
            f"failed={result['failed_count']}"
        )

    summary = {"selection": selection, "results": results}
    output = workdir / "reverify.json"
    _write_json(output, summary)
    _log(f"results -> {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", default=str(DEFAULT_WORKDIR))
    parser.add_argument("--count", type=int, default=20, help="models to select")
    parser.add_argument("--images", type=int, default=180, help="max selected images")
    parser.add_argument("--min-images", type=int, default=4)
    parser.add_argument("--max-images", type=int, default=10)
    parser.add_argument("--full", action="store_true", help="select all example-capable models")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--port", type=int, default=18200)
    parser.add_argument(
        "--old-tree",
        default=None,
        help="old worktree path (default: <workdir>/old-tree)",
    )
    parser.add_argument("--old-ref", default="9ed75e8f")
    parser.add_argument("--new-tree", default=str(REPO_ROOT))
    parser.add_argument("--tree", default=str(REPO_ROOT))
    parser.add_argument("--mode", choices=sorted(MODES), default="serial")
    parser.add_argument(
        "--any-root",
        action="store_true",
        help=(
            "include models outside folder_paths roots; their sidecars are not "
            "sandboxed and the old tree cannot read them"
        ),
    )
    parser.add_argument(
        "--image-width",
        type=int,
        default=DEFAULT_IMAGE_WIDTH,
        help="example image rendition width pinned for every run",
    )
    parser.add_argument(
        "--warm-cache",
        dest="warm_cache",
        action="store_true",
        default=None,
        help="warm the CDN edge for the run's URLs before timing (default: compare only)",
    )
    parser.add_argument(
        "--no-warm-cache",
        dest="warm_cache",
        action="store_false",
        help=(
            "do not warm or verify the CDN; measures whatever edge state the "
            "URLs happen to be in, so mode order biases the result"
        ),
    )
    parser.add_argument(
        "--download-timeout",
        type=float,
        default=2700.0,
        help="seconds to wait for one download pass",
    )
    parser.add_argument(
        "--force",
        dest="force",
        action="store_true",
        default=True,
        help="reverify only: mirror the UI's Re-process All pass",
    )
    parser.add_argument(
        "--no-force",
        dest="force",
        action="store_false",
        help="reverify only: mirror the UI's Download Missing skip pass",
    )
    parser.add_argument(
        "--markers",
        dest="markers",
        action="store_true",
        default=True,
        help="reverify only: populate completion markers (post-upgrade library)",
    )
    parser.add_argument(
        "--no-markers",
        dest="markers",
        action="store_false",
        help="reverify only: leave folders unmarked (legacy library)",
    )
    parser.add_argument(
        "--model-concurrency",
        type=int,
        default=2,
        help="reverify only: model pipeline width",
    )
    parser.add_argument(
        "--global",
        dest="global_run",
        action="store_true",
        help=(
            "reverify only: omit model_hashes to mirror the UI's global entry; "
            "the pass then covers every model in the sandbox cache (use --full)"
        ),
    )
    parser.add_argument(
        "--reuse-examples",
        action="store_true",
        help=(
            "reverify only: keep the current examples tree instead of rebuilding "
            "it; the tree must match the selected mode (marked/unmarked)"
        ),
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="reverify only: number of passes over the populated tree",
    )
    parser.add_argument(
        "command",
        choices=["prepare", "run", "compare", "reverify"],
        nargs="?",
        default="compare",
    )
    args = parser.parse_args()
    if args.old_tree is None:
        args.old_tree = str(Path(args.workdir).resolve() / "old-tree")
    if args.warm_cache is None:
        # Comparison needs cache-neutral runs; a single `run` (e.g. the
        # full-library validation) should not pay for a second full download
        # unless the caller asks for it.
        args.warm_cache = args.command == "compare"
    if args.command == "prepare":
        prepare(args)
    elif args.command == "run":
        workdir = Path(args.workdir).resolve()
        selection = _read_json(workdir / "selection.json")
        result = run_once(
            Path(args.tree).resolve(),
            workdir,
            selection,
            args.mode,
            args.port,
            image_width=args.image_width,
            warm_cache=args.warm_cache,
            download_timeout=args.download_timeout,
        )
        _write_json(workdir / f"run-{args.mode}.json", result)
        _log(json.dumps(result, indent=2))
    elif args.command == "reverify":
        reverify(args)
    else:
        compare(args)


if __name__ == "__main__":
    main()
