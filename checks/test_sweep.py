import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sweep", ROOT / "tools" / "sweep.py")
sweep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sweep)

MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
SINGLE_ARCH = "regex-log"
MULTI_ARCH = "mteb-retrieve"


def skip_task(monkeypatch, tmp_path, task):
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["tasks"][task]["status"] = "skipped"
    root = tmp_path / "root"
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(sweep, "ROOT", root)


def recorder(returncode=0):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode)

    return calls, run


def fake_test(verdict="verified", reason=None, exit_code=None):
    seen = []

    def test(task, image, **kwargs):
        seen.append((task, image))
        test.jobs_dir = kwargs["jobs_dir"]
        if exit_code is not None:
            raise SystemExit(exit_code)
        return {"verdict": verdict, "reason": reason}

    return seen, test


def test_single_arch_task_is_built_then_tested(tmp_path):
    calls, run = recorder()
    seen, test = fake_test()
    row = sweep.sweep_one(SINGLE_ARCH, MANIFEST, tmp_path, run=run, test=test)
    assert calls[0][-2:] == [SINGLE_ARCH, f"tb21-arm64-local/{SINGLE_ARCH}:sweep"]
    assert calls[0][1].endswith("tools/build.sh")
    assert seen == [(SINGLE_ARCH, f"tb21-arm64-local/{SINGLE_ARCH}:sweep")]
    assert (row["source"], row["verdict"]) == ("build", "verified")
    assert json.loads((tmp_path / f"{SINGLE_ARCH}.sweep.json").read_text())["verdict"] == "verified"


def test_multi_arch_task_pulls_upstream_arm64_by_digest(tmp_path):
    calls, run = recorder()
    seen, test = fake_test()
    upstream = MANIFEST["tasks"][MULTI_ARCH]["upstream"]
    ref = f"{upstream['image'].rsplit(':', 1)[0]}@{upstream['image_digest']}"
    row = sweep.sweep_one(MULTI_ARCH, MANIFEST, tmp_path, run=run, test=test)
    assert calls == [["docker", "pull", "--platform", "linux/arm64", ref]]
    assert seen == [(MULTI_ARCH, ref)]
    assert row["source"] == "upstream"


def test_build_failure_is_failing_and_not_tested(tmp_path):
    _, run = recorder(returncode=1)
    seen, test = fake_test()
    row = sweep.sweep_one(SINGLE_ARCH, MANIFEST, tmp_path, run=run, test=test)
    assert seen == []
    assert (row["verdict"], row["reason"]) == ("failing", "build exit 1")


def test_missing_result_is_failing_with_test_exit(tmp_path):
    _, run = recorder()
    _, test = fake_test(exit_code=2)
    row = sweep.sweep_one(SINGLE_ARCH, MANIFEST, tmp_path, run=run, test=test)
    assert (row["verdict"], row["reason"]) == ("failing", "test exit 2")


def test_prune_removes_only_built_images(tmp_path):
    calls, run = recorder()
    _, test = fake_test()
    sweep.sweep_one(SINGLE_ARCH, MANIFEST, tmp_path, run=run, test=test, prune=True)
    sweep.sweep_one(MULTI_ARCH, MANIFEST, tmp_path, run=run, test=test, prune=True)
    removed = [c for c in calls if c[:3] == ["docker", "image", "rm"]]
    assert removed == [["docker", "image", "rm", f"tb21-arm64-local/{SINGLE_ARCH}:sweep"]]


def test_sweep_skips_tasks_with_a_row(tmp_path):
    (tmp_path / f"{SINGLE_ARCH}.sweep.json").write_text('{"verdict": "verified"}')
    calls, run = recorder()
    seen, test = fake_test()
    sweep.sweep([SINGLE_ARCH, MULTI_ARCH], MANIFEST, tmp_path, jobs=1, run=run, test=test)
    assert [task for task, _ in seen] == [MULTI_ARCH]


def test_jobs_dir_defaults_under_out_and_can_move(tmp_path):
    _, run = recorder()
    _, test = fake_test()
    sweep.sweep_one(SINGLE_ARCH, MANIFEST, tmp_path / "a", run=run, test=test)
    assert test.jobs_dir == tmp_path / "a" / "jobs"
    sweep.sweep_one(
        SINGLE_ARCH, MANIFEST, tmp_path / "b", run=run, test=test, jobs_dir=tmp_path / "j"
    )
    assert test.jobs_dir == tmp_path / "j"


def test_sweep_inspect_call_keeps_capture_output(tmp_path):
    observed = []

    def run(command, **kwargs):
        observed.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="linux/arm64\n", stderr="")

    def test(task, image, **kwargs):
        kwargs["run"](
            ["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", image],
            check=False,
            capture_output=True,
            text=True,
        )
        return {"verdict": "verified", "reason": None}

    sweep.sweep_one(SINGLE_ARCH, MANIFEST, tmp_path, run=run, test=test)
    inspect = next(call for call in observed if call[0][:3] == ["docker", "image", "inspect"])
    assert inspect[1] == {"check": False, "capture_output": True, "text": True}


def test_default_sweep_excludes_skipped_tasks(monkeypatch, tmp_path):
    captured = {}

    def fake_sweep(tasks, manifest, out, **kwargs):
        captured["tasks"] = tasks
        return []

    skip_task(monkeypatch, tmp_path, SINGLE_ARCH)
    monkeypatch.setattr(sweep, "sweep", fake_sweep)
    assert sweep.main(["--out", str(tmp_path)]) == 0
    assert SINGLE_ARCH not in captured["tasks"]
    assert MULTI_ARCH in captured["tasks"]


def test_explicit_skipped_task_is_rejected(monkeypatch, tmp_path):
    import pytest

    skip_task(monkeypatch, tmp_path, SINGLE_ARCH)
    monkeypatch.setattr(sweep, "sweep", lambda *args, **kwargs: [])
    with pytest.raises(SystemExit) as error:
        sweep.main([SINGLE_ARCH, "--out", str(tmp_path)])
    assert error.value.code == 2


def test_host_network_is_passed_to_build_and_test(tmp_path):
    observed = []

    def run(command, **kwargs):
        observed.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    def test(task, image, **kwargs):
        assert kwargs["network"] == "host"
        return {"verdict": "verified", "reason": None}

    sweep.sweep_one(SINGLE_ARCH, MANIFEST, tmp_path, run=run, test=test, network="host")
    build = observed[0]
    assert build[1]["env"]["BUILD_NETWORK"] == "host"
