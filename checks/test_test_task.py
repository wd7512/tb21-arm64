import importlib.util
import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = "fix-git"
IMAGE = "tb21-arm64-local/fix-git:dev"
SPEC = importlib.util.spec_from_file_location("test_task", ROOT / "tools" / "test_task.py")
test_task = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(test_task)


def fake_run(rewards, missing=()):
    calls = iter(rewards)

    def run(command, check=False, **kwargs):
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, stdout="linux/arm64\n", stderr="")
        reward = next(calls)
        job_name = command[command.index("--job-name") + 1]
        jobs_dir = Path(command[command.index("-o") + 1])
        if job_name in missing:
            return None
        task_name = f"terminal-bench/{TASK}"
        exception_type = None
        payload = {
            "task_name": task_name,
            "verifier_result": None if exception_type else {"rewards": {"reward": reward}},
            "exception_info": (
                {"exception_type": exception_type, "exception_message": "fake failure"}
                if exception_type
                else None
            ),
        }
        result_dir = jobs_dir / job_name / f"{TASK}__fake"
        result_dir.mkdir(parents=True)
        (result_dir / "result.json").write_text(json.dumps(payload))
        (jobs_dir / job_name / "result.json").write_text(json.dumps({"n_total_trials": 1}))
        return None

    return run


def test_all_pass_and_rewrite_only_temporary_copy(tmp_path):
    original = (ROOT / TASK / "task.toml").read_text()
    result = test_task.run_test(
        TASK,
        IMAGE,
        jobs_dir=tmp_path / "jobs",
        out=tmp_path / "report.json",
        run=fake_run([1.0, 1.0, 1.0, 0.0]),
    )
    assert result["verdict"] == "verified"
    assert result["reason"] is None
    assert len(result["oracle"]) == 3
    assert result["nop"]["reward"] == 0.0
    assert json.loads((tmp_path / "report.json").read_text()) == result
    assert (ROOT / TASK / "task.toml").read_text() == original
    assert tomllib.loads(original)["environment"]["docker_image"] != IMAGE


def test_oracle_zero_is_failing(tmp_path):
    result = test_task.run_test(
        TASK,
        IMAGE,
        jobs_dir=tmp_path / "jobs",
        out=tmp_path / "report.json",
        run=fake_run([1.0, 0.0, 1.0, 0.0]),
    )
    assert result["verdict"] == "failing"
    assert result["reason"] == "oracle run 2 reward 0.0"


def test_oracle_exception_is_failing(tmp_path):
    def run(command, check=False, **kwargs):
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, stdout="linux/arm64\n", stderr="")
        job_name = command[command.index("--job-name") + 1]
        jobs_dir = Path(command[command.index("-o") + 1])
        task_name = f"terminal-bench/{TASK}"
        exception_type = "EnvironmentStartTimeoutError" if "oracle-1-" in job_name else None
        payload = {
            "task_name": task_name,
            "verifier_result": None if exception_type else {"rewards": {"reward": 1.0}},
            "exception_info": (
                {"exception_type": exception_type, "exception_message": "fake failure"}
                if exception_type
                else None
            ),
        }
        result_dir = jobs_dir / job_name / f"{TASK}__fake"
        result_dir.mkdir(parents=True)
        (result_dir / "result.json").write_text(json.dumps(payload))
        (jobs_dir / job_name / "result.json").write_text(json.dumps({"n_total_trials": 1}))

    result = test_task.run_test(
        TASK, IMAGE, jobs_dir=tmp_path / "jobs", out=tmp_path / "report.json", run=run
    )
    assert result["verdict"] == "failing"
    assert result["oracle"][0]["exception_type"] == "EnvironmentStartTimeoutError"
    assert result["reason"] == "oracle run 1 exception EnvironmentStartTimeoutError"


def test_nop_one_is_failing(tmp_path):
    result = test_task.run_test(
        TASK,
        IMAGE,
        jobs_dir=tmp_path / "jobs",
        out=tmp_path / "report.json",
        run=fake_run([1.0, 1.0, 1.0, 1.0]),
    )
    assert result["verdict"] == "failing"
    assert result["reason"] == "nop reward 1.0"


def test_missing_result_exits_two(tmp_path):
    def run(command, check=False, **kwargs):
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, stdout="linux/arm64\n", stderr="")
        return subprocess.CompletedProcess(command, 1)

    try:
        test_task.run_test(
            TASK, IMAGE, jobs_dir=tmp_path / "jobs", out=tmp_path / "report.json", run=run
        )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("missing result.json must exit 2")


def test_rejects_non_arm64_before_harbor(tmp_path):
    calls = []

    def run(command, check=False, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="linux/amd64\n", stderr="")

    try:
        test_task.run_test(
            TASK, IMAGE, jobs_dir=tmp_path / "jobs", out=tmp_path / "report.json", run=run
        )
    except ValueError as error:
        assert str(error) == f"image is not linux/arm64: {IMAGE} (linux/amd64)"
    else:
        raise AssertionError("non-arm64 image must be rejected")
    assert len(calls) == 1
    assert calls[0][:3] == ["docker", "image", "inspect"]
    assert "harbor" not in calls[0]


def test_host_network_adds_compose_overlay(tmp_path):
    harbor_calls = []

    def run(command, check=False, **kwargs):
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, stdout="linux/arm64\n", stderr="")
        harbor_calls.append(command)
        compose = Path(command[command.index("--extra-docker-compose") + 1])
        assert compose.read_text(encoding="utf-8") == "services:\n  main:\n    network_mode: host\n"
        return fake_run([1.0, 1.0, 1.0, 0.0])(command, check=check, **kwargs)

    test_task.run_test(
        TASK,
        IMAGE,
        runs=1,
        network="host",
        jobs_dir=tmp_path / "jobs",
        out=tmp_path / "report.json",
        run=run,
    )
    assert len(harbor_calls) == 2


def test_default_network_keeps_harbor_command_unchanged(tmp_path):
    calls = []

    def run(command, check=False, **kwargs):
        calls.append(command)
        jobs_dir = Path(command[command.index("-o") + 1])
        job_name = command[command.index("--job-name") + 1]
        result_dir = jobs_dir / job_name / f"{TASK}__fake"
        result_dir.mkdir(parents=True)
        (result_dir / "result.json").write_text(json.dumps({"verifier_result": None}))
        return None

    test_task._run_harbor(Path("task"), "oracle", tmp_path, "job", run)
    assert calls == [
        [
            "uvx",
            "--from",
            "harbor==0.23.0",
            "harbor",
            "run",
            "-p",
            "task",
            "-a",
            "oracle",
            "-e",
            "docker",
            "-o",
            str(tmp_path),
            "--job-name",
            "job",
            "-y",
            "-q",
        ]
    ]
