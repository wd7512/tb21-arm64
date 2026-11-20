"""Build-independent Harbor oracle and nop verification for a local task image."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARBOR_VERSION = "0.23.0"


def _task_folder(task):
    if Path(task).name != task or Path(task).is_absolute():
        raise ValueError(f"task must be a root folder containing task.toml: {task}")
    folder = ROOT / task
    if not folder.is_dir() or not (folder / "task.toml").is_file():
        raise ValueError(f"task must be a root folder containing task.toml: {task}")
    return folder


def _copy_with_image(task_folder, image, temp_root):
    copied_task = temp_root / task_folder.name
    shutil.copytree(task_folder, copied_task)
    config = copied_task / "task.toml"
    content = config.read_text(encoding="utf-8")
    rewritten, count = re.subn(
        r'(?m)^(\s*docker_image\s*=\s*)"[^"\n]*"(\s*(?:#.*)?)$',
        lambda match: f"{match.group(1)}{json.dumps(image)}{match.group(2)}",
        content,
    )
    if count != 1:
        raise ValueError(f"expected one docker_image setting in {config}, found {count}")
    config.write_text(rewritten, encoding="utf-8")
    parsed = tomllib.loads(rewritten)
    if parsed["environment"]["docker_image"] != image:
        raise ValueError("rewritten docker_image does not match requested image")
    return copied_task


def _run_harbor(task_folder, agent, jobs_dir, job_name, run):
    command = [
        "uvx",
        "--from",
        f"harbor=={HARBOR_VERSION}",
        "harbor",
        "run",
        "-p",
        str(task_folder),
        "-a",
        agent,
        "-e",
        "docker",
        "-o",
        str(jobs_dir),
        "--job-name",
        job_name,
        "-y",
        "-q",
    ]
    run(command, check=False)
    results = list((jobs_dir / job_name).rglob("result.json"))
    if len(results) != 1:
        raise SystemExit(2)
    result = json.loads(results[0].read_text(encoding="utf-8"))
    exception_info = result.get("exception_info")
    exception_type = exception_info.get("exception_type") if exception_info else None
    verifier_result = result.get("verifier_result")
    reward = None
    if verifier_result is not None:
        reward = verifier_result.get("rewards", {}).get("reward")
    return {"reward": reward, "exception_type": exception_type, "job": job_name}


def run_test(task, image, runs=3, out=None, jobs_dir=None, run=subprocess.run):
    task_folder = _task_folder(task)
    if runs < 1:
        raise ValueError("runs must be at least 1")
    jobs_dir = Path(jobs_dir) if jobs_dir is not None else ROOT / "jobs"
    out = Path(out) if out is not None else ROOT / "reports" / "local" / f"{task}.test.json"
    jobs_dir = jobs_dir.resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    oracle = []
    with tempfile.TemporaryDirectory(prefix="tb21-test-task-") as temporary:
        copied_task = _copy_with_image(task_folder, image, Path(temporary))
        for index in range(1, runs + 1):
            job_name = f"{task}-oracle-{index}-{stamp}"
            oracle.append(_run_harbor(copied_task, "oracle", jobs_dir, job_name, run))
        nop_name = f"{task}-nop-{stamp}"
        nop = _run_harbor(copied_task, "nop", jobs_dir, nop_name, run)

    reason = None
    for index, result in enumerate(oracle, start=1):
        if result["exception_type"]:
            reason = f"oracle run {index} exception {result['exception_type']}"
            break
        if result["reward"] != 1.0:
            reason = f"oracle run {index} reward {result['reward']}"
            break
    if reason is None:
        if nop["exception_type"]:
            reason = f"nop exception {nop['exception_type']}"
        elif nop["reward"] != 0.0:
            reason = f"nop reward {nop['reward']}"

    report = {
        "task": task,
        "image": image,
        "harbor": HARBOR_VERSION,
        "oracle": oracle,
        "nop": nop,
        "verdict": "verified" if reason is None else "failing",
        "reason": reason,
        "finished_at": datetime.now(UTC).isoformat(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{task}: {report['verdict']}" + (f" ({reason})" if reason else ""))
    return report


def main(argv=None, *, run=subprocess.run):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task")
    parser.add_argument("image")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out")
    parser.add_argument("--jobs-dir")
    args = parser.parse_args(argv)
    try:
        report = run_test(
            args.task,
            args.image,
            runs=args.runs,
            out=args.out,
            jobs_dir=args.jobs_dir,
            run=run,
        )
    except ValueError as error:
        parser.error(str(error))
    return 0 if report["verdict"] == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())
