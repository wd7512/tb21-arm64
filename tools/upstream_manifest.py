#!/usr/bin/env python3
"""Record the imported Harbor package and upstream Docker image digests."""

import json
import re
import subprocess
import tempfile
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

DATASET = "terminal-bench/terminal-bench-2-1"
HARBOR_VERSION = "0.23.0"
ACCEPT = ", ".join(
    (
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.oci.image.index.v1+json",
    )
)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def task_directories(root):
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and (path / "task.toml").is_file()),
        key=lambda path: path.name,
    )


def same_tree(cached, local):
    cached_files = {path.relative_to(cached) for path in cached.rglob("*") if path.is_file()}
    local_files = {path.relative_to(local) for path in local.rglob("*") if path.is_file()}
    return cached_files == local_files and all(
        (cached / relative).read_bytes() == (local / relative).read_bytes()
        for relative in cached_files
    )


def cached_package(cache_root, task_name):
    task_cache = cache_root / "terminal-bench" / task_name
    if not task_cache.is_dir():
        raise RuntimeError(f"Harbor cache layout differs from expected: missing {task_cache}")
    entries = sorted(path for path in task_cache.iterdir() if path.is_dir())
    if len(entries) != 1:
        raise RuntimeError(
            f"Harbor cache layout differs from expected for {task_name}: "
            f"expected one hash folder in {task_cache}, found {len(entries)}"
        )
    return entries[0]


def package_digests(root, directories):
    with tempfile.TemporaryDirectory(prefix="tb21-harbor-cache-") as temporary:
        subprocess.run(
            [
                "uvx",
                "--from",
                f"harbor=={HARBOR_VERSION}",
                "harbor",
                "download",
                DATASET,
                "--cache",
                "-o",
                temporary,
            ],
            check=True,
            cwd=root,
        )
        cache_root = Path(temporary)
        results = {}
        mismatches = []
        for task_dir in directories:
            cached = cached_package(cache_root, task_dir.name)
            results[task_dir.name] = f"sha256:{cached.name}"
            if not same_tree(cached, task_dir):
                mismatches.append(task_dir.name)
        if mismatches:
            raise RuntimeError(
                "Imported task files differ from Harbor package: " + ", ".join(mismatches)
            )
        return results


def image_digest(image):
    repository, tag = image.rsplit(":", 1)
    scope = urllib.parse.urlencode(
        {"service": "registry.docker.io", "scope": f"repository:{repository}:pull"}
    )
    token_request = urllib.request.Request(f"https://auth.docker.io/token?{scope}")
    with urllib.request.urlopen(token_request) as response:
        token = json.load(response)["token"]

    request = urllib.request.Request(
        f"https://registry-1.docker.io/v2/{repository}/manifests/{tag}",
        method="HEAD",
        headers={"Authorization": f"Bearer {token}", "Accept": ACCEPT},
    )
    with urllib.request.urlopen(request) as response:
        digest = response.headers.get("Docker-Content-Digest", "")
        media_type = response.headers.get("Content-Type", "")
    if not DIGEST.fullmatch(digest):
        raise RuntimeError(f"Docker Hub returned an invalid digest for {image}: {digest!r}")
    if not media_type:
        raise RuntimeError(f"Docker Hub returned no Content-Type for {image}")
    return digest, media_type


def build_manifest(root):
    directories = task_directories(root)
    digests = package_digests(root, directories)
    tasks = {}
    for task_dir in directories:
        task = tomllib.loads((task_dir / "task.toml").read_text())
        image = task["environment"]["docker_image"]
        digest, media_type = image_digest(image)
        tasks[task_dir.name] = {
            "upstream": {
                "package_digest": digests[task_dir.name],
                "image": image,
                "image_digest": digest,
                "media_type": media_type,
            },
            "image": None,
            "status": "untested",
            "fix_class": None,
            "evidence": None,
        }
    return {
        "dataset": DATASET,
        "harbor": HARBOR_VERSION,
        "tasks": tasks,
    }


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = build_manifest(root)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
