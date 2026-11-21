import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ci_tasks", ROOT / "tools" / "ci_tasks.py")
ci_tasks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci_tasks)


def manifest():
    return {
        "tasks": {
            "task-one": {"status": "untested"},
            "task-skipped": {"status": "skipped"},
            "task-no-status": {},
            "break-filter-js-from-html": {"status": "untested"},
            "mteb-retrieve": {"status": "untested"},
            "regex-log": {"status": "untested"},
        }
    }


def changed(paths):
    def run(command, **kwargs):
        assert command == ["git", "diff", "--name-only", "base...HEAD"]
        return subprocess.CompletedProcess(command, 0, stdout="\n".join(paths) + "\n")

    return run


def test_task_change_selects_manifest_task():
    assert ci_tasks.tasks_for_changed(manifest(), "base", run=changed(["task-one/task.toml"])) == [
        "task-one"
    ]


def test_tools_only_change_uses_canary_set():
    assert ci_tasks.tasks_for_changed(manifest(), "base", run=changed(["tools/build.sh"])) == [
        "break-filter-js-from-html",
        "mteb-retrieve",
        "regex-log",
    ]


def test_docs_only_change_is_empty():
    assert ci_tasks.tasks_for_changed(manifest(), "base", run=changed(["README.md"])) == []


def test_skipped_task_is_excluded():
    assert (
        ci_tasks.tasks_for_changed(manifest(), "base", run=changed(["task-skipped/task.toml"]))
        == []
    )


def test_unknown_folder_is_ignored():
    assert (
        ci_tasks.tasks_for_changed(manifest(), "base", run=changed(["not-a-task/task.toml"])) == []
    )


def test_all_includes_missing_status_but_not_skipped():
    assert ci_tasks.tasks_for_all(manifest()) == [
        "break-filter-js-from-html",
        "mteb-retrieve",
        "regex-log",
        "task-no-status",
        "task-one",
    ]
