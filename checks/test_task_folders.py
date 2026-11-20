import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NON_TASK_FOLDERS = {"checks", "tools", "fixes", "reports", "jobs"}


def task_folders() -> list[Path]:
    return sorted(
        path
        for path in ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".") and path.name not in NON_TASK_FOLDERS
    )


def test_every_task_folder_names_an_image_and_has_a_dockerfile():
    folders = task_folders()
    assert len(folders) == 89
    for folder in folders:
        task = tomllib.loads((folder / "task.toml").read_text(encoding="utf-8"))
        assert task["environment"]["docker_image"], folder.name
        assert (folder / "environment" / "Dockerfile").is_file(), folder.name
