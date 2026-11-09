#!/usr/bin/env python3
"""Reproducible A/B benchmark for example-image downloads.

The benchmark keeps real model files read-only and runs every candidate in a
pinned settings directory whose cache, sidecars and example folder are copies
under ``--workdir``. It selects one model subset from the user's cache/sidecars,
then runs the same subset against:

* ``serial``: the pre-pipeline tree (or any tree), model concurrency forced to 1
* ``pipeline``: the current tree, model concurrency 2, AIMD ceiling = base 6
* ``aimd``: the current tree, model concurrency 2, AIMD ceiling 8

Each run starts from an empty examples directory and a fresh cache/sidecar
copy. The script never writes to the real settings directory or model library.
"""

from __future__ import annotations

import argparse
import json
import os
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

    selected: list[dict[str, Any]] = []
    total_images = 0
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


def _build_settings(
    run_dir: Path,
    mode: str,
    examples_path: Path,
) -> dict[str, Any]:
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
            "example_images_download_max_concurrency": MODES[mode]["probe_ceiling"],
            "example_images_model_concurrency": MODES[mode]["model_concurrency"],
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
            if name.startswith(".lm-examples-complete") or name == ".download_progress.json":
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


def run_once(
    tree: Path,
    workdir: Path,
    selection: dict[str, Any],
    mode: str,
    port: int,
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

    settings = _build_settings(run_dir, mode, examples_path)
    _write_json(run_dir / "settings.json", settings)

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
    _log(f"[{mode}] starting {tree} on :{port}")
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
        model_hashes = [model["sha256"] for model in selection["models"]]
        response = _http_json(
            base_url + "/api/lm/download-example-images",
            {
                "model_types": ["lora", "checkpoint", "embedding"],
                "model_hashes": model_hashes,
                "delay": 0,
                "optimize": True,
            },
        )
        if not response.get("success"):
            raise RuntimeError(f"download rejected: {response}")

        download_start = time.monotonic()
        deadline = download_start + 2700
        status: dict[str, Any] = {}
        while time.monotonic() < deadline:
            payload = _http_json(base_url + "/api/lm/example-images-status")
            status = payload.get("status") or {}
            state = status.get("status")
            if not payload.get("is_downloading") and state in {
                "completed",
                "stopped",
                "error",
            }:
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("download did not finish within 2700s")
        elapsed = time.monotonic() - download_start
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
            "startup_seconds": round(ready - started, 3),
            "status": status.get("status"),
            "total": status.get("total"),
            "completed": status.get("completed"),
            "failed_count": len(status.get("failed_models") or []),
            "files": files,
            "bytes": size,
            **logs,
            "run_dir": str(run_dir),
        }
    finally:
        _terminate(proc)
        log_handle.close()


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


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
            result = run_once(tree, workdir, selection, mode, port)
            results.append(result)
            port += 1
            _log(
                f"[{mode}] {result['elapsed_seconds']:.1f}s "
                f"{result['files']} files {result['bytes'] / 1_000_000:.1f} MB "
                f"completed={result['completed']}/{result['total']} "
                f"429={result['rate_limited']}"
            )

    summary: dict[str, Any] = {"selection": selection, "results": results, "modes": {}}
    for mode in MODES:
        rows = [row for row in results if row["mode"] == mode]
        if not rows:
            continue
        elapsed = _median([row["elapsed_seconds"] for row in rows])
        files = _median([float(row["files"]) for row in rows])
        size = _median([float(row["bytes"]) for row in rows])
        summary["modes"][mode] = {
            "runs": len(rows),
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
    _log("")
    _log("mode       median_s  speedup  files  MB      429  404  probe")
    for mode in MODES:
        data = summary["modes"].get(mode)
        if not data:
            continue
        _log(
            f"{mode:<10} {data['median_elapsed_seconds']:>9.1f} "
            f"{data.get('speedup_vs_new_serial', 0):>7.3f} "
            f"{data['median_files']:>6} "
            f"{data['median_bytes'] / 1_000_000:>7.1f} "
            f"{data['rate_limited']:>5} {data['not_found']:>4} "
            f"{data.get('probe_steps', 0):>6}"
        )
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
    parser.add_argument("--old-tree", default=str(DEFAULT_WORKDIR / "old-tree"))
    parser.add_argument("--old-ref", default="9ed75e8f")
    parser.add_argument("--new-tree", default=str(REPO_ROOT))
    parser.add_argument("--tree", default=str(REPO_ROOT))
    parser.add_argument("--mode", choices=sorted(MODES), default="serial")
    parser.add_argument(
        "command",
        choices=["prepare", "run", "compare"],
        nargs="?",
        default="compare",
    )
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    elif args.command == "run":
        workdir = Path(args.workdir).resolve()
        selection = _read_json(workdir / "selection.json")
        result = run_once(
            Path(args.tree).resolve(), workdir, selection, args.mode, args.port
        )
        _write_json(workdir / f"run-{args.mode}.json", result)
        _log(json.dumps(result, indent=2))
    else:
        compare(args)


if __name__ == "__main__":
    main()
