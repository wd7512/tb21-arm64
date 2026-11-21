import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "record_ci.py"
TASK = "regex-log"
IMAGE = "ghcr.io/wd7512/tb21-arm64/regex-log@sha256:" + "a" * 64
RUN_URL = "https://github.com/wd7512/tb21-arm64/actions/runs/123"


def fixture_repo(tmp_path):
    (tmp_path / TASK).mkdir()
    manifest = json.loads((REPO / "manifest.json").read_text())
    entry = manifest["tasks"][TASK]
    upstream = entry["upstream"]["image"]
    task_toml = re.sub(
        r'^docker_image = ".*"$',
        f'docker_image = "{upstream}"',
        (REPO / TASK / "task.toml").read_text(),
        count=1,
        flags=re.MULTILINE,
    )
    (tmp_path / TASK / "task.toml").write_text(task_toml)
    entry.update(image=None, status="untested", evidence=None)
    manifest["tasks"] = {TASK: entry}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    reports = tmp_path / "publish"
    reports.mkdir()
    return reports


def record(tmp_path, reports):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(reports)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def publish(reports, *, verdict="verified", reason=None, image=IMAGE):
    (reports / f"{TASK}.publish.json").write_text(
        json.dumps(
            {
                "task": TASK,
                "image": image,
                "verdict": verdict,
                "reason": reason,
                "run_url": RUN_URL,
            }
        )
    )


def test_verified_task_updates_only_docker_image_line(tmp_path):
    reports = fixture_repo(tmp_path)
    task_path = tmp_path / TASK / "task.toml"
    before = task_path.read_text()
    expected = before.replace(
        'docker_image = "alexgshaw/regex-log:20251031"',
        f'docker_image = "{IMAGE}"',
    )
    publish(reports)

    result = record(tmp_path, reports)

    assert result.returncode == 0, result.stderr
    assert task_path.read_text() == expected
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["tasks"][TASK]["image"] == IMAGE
    assert manifest["tasks"][TASK]["status"] == "verified-ci"
    assert manifest["tasks"][TASK]["evidence"] == RUN_URL


def test_failing_task_records_reason(tmp_path):
    reports = fixture_repo(tmp_path)
    publish(reports, verdict="failing", reason="oracle run 2 reward 0.0")

    result = record(tmp_path, reports)

    assert result.returncode == 0, result.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["tasks"][TASK]["status"] == "failing"
    assert manifest["tasks"][TASK]["evidence"] == {
        "run": RUN_URL,
        "reason": "oracle run 2 reward 0.0",
    }


def test_null_image_keeps_task_file_and_records_verdict(tmp_path):
    reports = fixture_repo(tmp_path)
    task_path = tmp_path / TASK / "task.toml"
    before = task_path.read_bytes()
    publish(reports, verdict="failing", reason="build exit 1", image=None)

    result = record(tmp_path, reports)

    assert result.returncode == 0, result.stderr
    assert task_path.read_bytes() == before
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["tasks"][TASK]["image"] is None
    assert manifest["tasks"][TASK]["status"] == "failing"


def test_skipped_task_is_untouched(tmp_path):
    reports = fixture_repo(tmp_path)
    task_path = tmp_path / TASK / "task.toml"
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tasks"][TASK]["status"] = "skipped"
    manifest["tasks"][TASK]["evidence"] = "QEMU task"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    before_task = task_path.read_bytes()
    before_manifest = manifest_path.read_bytes()
    publish(reports)

    result = record(tmp_path, reports)

    assert result.returncode == 0, result.stderr
    assert task_path.read_bytes() == before_task
    assert manifest_path.read_bytes() == before_manifest
