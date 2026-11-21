"""Build and test many tasks, writing OUT/<task>.sweep.json; tasks that have one are skipped."""

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MULTI_ARCH_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}


def _load_test_task():
    spec = importlib.util.spec_from_file_location("test_task", ROOT / "tools" / "test_task.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_test


def image_for(task, manifest):
    upstream = manifest["tasks"][task]["upstream"]
    if upstream["media_type"] in MULTI_ARCH_TYPES:
        return f"{upstream['image'].rsplit(':', 1)[0]}@{upstream['image_digest']}", "upstream"
    return f"tb21-arm64-local/{task}:sweep", "build"


def sweep_one(
    task, manifest, out, *, run=subprocess.run, test=None, runs=3, prune=False, jobs_dir=None
):
    test = test or _load_test_task()
    image, source = image_for(task, manifest)
    started = time.monotonic()
    out.mkdir(parents=True, exist_ok=True)
    with (out / f"{task}.log").open("w", encoding="utf-8") as log:

        def logged(command, check=False, **kwargs):
            if "capture_output" not in kwargs and "stdout" not in kwargs:
                kwargs = {"stdout": log, "stderr": subprocess.STDOUT}
            return run(command, check=check, **kwargs)

        if source == "build":
            prepare = ["bash", str(ROOT / "tools" / "build.sh"), task, image]
        else:
            prepare = ["docker", "pull", "--platform", "linux/arm64", image]
        returncode = logged(prepare).returncode
        if returncode != 0:
            verdict, reason = "failing", f"{source} exit {returncode}"
        else:
            try:
                report = test(
                    task,
                    image,
                    runs=runs,
                    out=out / f"{task}.test.json",
                    jobs_dir=jobs_dir or out / "jobs",
                    run=logged,
                )
                verdict, reason = report["verdict"], report["reason"]
            except SystemExit as error:
                verdict, reason = "failing", f"test exit {error.code}"
        if prune and source == "build":
            logged(["docker", "image", "rm", image])
    row = {
        "task": task,
        "image": image,
        "source": source,
        "verdict": verdict,
        "reason": reason,
        "seconds": round(time.monotonic() - started),
    }
    (out / f"{task}.sweep.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    print(f"{task}\t{source}\t{verdict}\t{reason or ''}\t{row['seconds']}s", flush=True)
    return row


def sweep(tasks, manifest, out, *, jobs=1, **kwargs):
    pending = [task for task in tasks if not (out / f"{task}.sweep.json").exists()]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(lambda task: sweep_one(task, manifest, out, **kwargs), pending))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", nargs="*", help="default: every task in manifest.json")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", default=str(ROOT / "reports" / "local" / "sweep"))
    parser.add_argument("--jobs-dir", help="Harbor job folders (default: OUT/jobs)")
    parser.add_argument(
        "--prune", action="store_true", help="remove each built image after its test"
    )
    args = parser.parse_args(argv)
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    unknown = sorted(set(args.tasks) - set(manifest["tasks"]))
    if unknown:
        parser.error(f"unknown tasks: {' '.join(unknown)}")
    if args.tasks:
        skipped = sorted(
            task for task in args.tasks if manifest["tasks"][task]["status"] == "skipped"
        )
        if skipped:
            parser.error(f"skipped tasks cannot be swept: {' '.join(skipped)}")
        tasks = args.tasks
    else:
        tasks = sorted(
            task for task, record in manifest["tasks"].items() if record["status"] != "skipped"
        )
    rows = sweep(
        tasks,
        manifest,
        Path(args.out).resolve(),
        jobs=args.jobs,
        runs=args.runs,
        prune=args.prune,
        jobs_dir=Path(args.jobs_dir).resolve() if args.jobs_dir else None,
    )
    return 0 if all(row["verdict"] == "verified" for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
