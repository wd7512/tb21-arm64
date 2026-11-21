"""Select task folders for the CI matrix."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANARIES = ["break-filter-js-from-html", "mteb-retrieve", "regex-log"]
MATRIX_PATHS = ("tools/", "manifest.json", "pyproject.toml", ".github/")


def tasks_for_all(manifest):
    return sorted(task for task, row in manifest["tasks"].items() if row.get("status") != "skipped")


def tasks_for_changed(manifest, base, *, run=subprocess.run):
    result = run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    paths = [line for line in result.stdout.splitlines() if line]
    manifest_tasks = manifest["tasks"]
    selected = {
        path.split("/", 1)[0]
        for path in paths
        if "/" in path
        and path.split("/", 1)[0] in manifest_tasks
        and manifest_tasks[path.split("/", 1)[0]].get("status") != "skipped"
    }
    if not selected and any(
        path.startswith("tools/") or path in MATRIX_PATHS[1:3] or path.startswith(".github/")
        for path in paths
    ):
        selected.update(task for task in CANARIES if task in manifest_tasks)
    return sorted(selected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="select every non-skipped task")
    selection.add_argument("--changed", metavar="BASE", help="select tasks changed from BASE")
    args = parser.parse_args(argv)
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    tasks = tasks_for_all(manifest) if args.all else tasks_for_changed(manifest, args.changed)
    print(json.dumps(tasks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
