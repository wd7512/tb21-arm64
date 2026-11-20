import json
import re
import tomllib
from pathlib import Path

import pytest

DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
STATUSES = {"untested", "failing", "verified-ci", "verified-isambard"}
FIX_CLASSES = {"port", "drift", "defect"}


def check_manifest(manifest_path, root):
    manifest = json.loads(Path(manifest_path).read_text())
    task_dirs = {
        path.name
        for path in Path(root).iterdir()
        if path.is_dir() and (path / "task.toml").is_file()
    }
    tasks = manifest["tasks"]
    assert set(tasks) == task_dirs, "manifest task names differ from task folders"

    for name, record in tasks.items():
        upstream = record["upstream"]
        assert DIGEST.fullmatch(upstream["package_digest"]), f"{name}: invalid package_digest"
        assert DIGEST.fullmatch(upstream["image_digest"]), f"{name}: invalid image_digest"
        assert record["status"] in STATUSES, f"{name}: invalid status"
        classes = record["fix_classes"]
        assert isinstance(classes, list), f"{name}: invalid fix_classes"
        assert set(classes) <= FIX_CLASSES, f"{name}: invalid fix_classes"
        assert classes == sorted(set(classes)), f"{name}: fix_classes not sorted"
        if record["image"] is None:
            task = tomllib.loads((Path(root) / name / "task.toml").read_text())
            assert task["environment"]["docker_image"] == upstream["image"], (
                f"{name}: task.toml docker_image differs from upstream.image"
            )


def test_manifest_invariants(tmp_path):
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "manifest.json"
    check_manifest(manifest_path, root)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["tasks"].pop(next(iter(data["tasks"]))), "manifest task names differ"),
        (
            lambda data: data["tasks"][next(iter(data["tasks"]))]["upstream"].__setitem__(
                "package_digest", "not-a-digest"
            ),
            "invalid package_digest",
        ),
        (
            lambda data: data["tasks"][next(iter(data["tasks"]))]["upstream"].__setitem__(
                "image_digest", "not-a-digest"
            ),
            "invalid image_digest",
        ),
        (
            lambda data: data["tasks"][next(iter(data["tasks"]))].__setitem__("status", "unknown"),
            "invalid status",
        ),
        (
            lambda data: data["tasks"][next(iter(data["tasks"]))].__setitem__(
                "fix_classes", ["unknown"]
            ),
            "invalid fix_classes",
        ),
        (
            lambda data: data["tasks"][next(iter(data["tasks"]))].__setitem__(
                "fix_classes", ["port", "drift"]
            ),
            "fix_classes not sorted",
        ),
        (
            lambda data: data["tasks"][next(iter(data["tasks"]))].__setitem__(
                "fix_classes", "drift"
            ),
            "invalid fix_classes",
        ),
        (
            lambda data: data["tasks"][next(iter(data["tasks"]))]["upstream"].__setitem__(
                "image", "wrong/image:tag"
            ),
            "docker_image differs from upstream.image",
        ),
    ],
)
def test_manifest_rejects_mutation(tmp_path, mutate, message):
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "manifest.json").read_text())
    mutate(data)
    copy = tmp_path / "manifest.json"
    copy.write_text(json.dumps(data))
    with pytest.raises(AssertionError, match=message):
        check_manifest(copy, root)
