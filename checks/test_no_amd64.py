import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def amd64_references(root):
    root = Path(root)
    platform = re.compile(r"--platform(?:=|\s+)linux/(?:amd64|x86_64)", re.IGNORECASE)
    upstream = re.compile(
        r"^\s*(?:FROM\b.*\balexgshaw/|COPY\b.*--from(?:=|\s+)alexgshaw/)",
        re.IGNORECASE,
    )
    references = []
    for task in sorted(root.iterdir()):
        dockerfile = task / "environment" / "Dockerfile"
        if not dockerfile.is_file():
            continue
        for line in dockerfile.read_text(encoding="utf-8").splitlines():
            if platform.search(line) or upstream.search(line):
                references.append((task.name, line))
    return references


def test_repository_has_no_amd64_task_dockerfile_references():
    assert amd64_references(ROOT) == []


def test_mutation_finds_each_forbidden_reference(tmp_path):
    references = [
        "FROM --platform=linux/amd64 alpine:latest",
        "FROM --platform linux/amd64 alpine:latest",
        "FROM --platform=linux/x86_64 alpine:latest",
        "FROM alexgshaw/example:latest",
        "COPY --from=alexgshaw/example:latest /x /x",
    ]
    for index, line in enumerate(references):
        task = tmp_path / f"task-{index}" / "environment"
        task.mkdir(parents=True)
        (task / "Dockerfile").write_text(line + "\n")
    found = amd64_references(tmp_path)
    assert found == [(f"task-{index}", line) for index, line in enumerate(references)]
