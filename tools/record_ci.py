"""Record task publish artifacts in task.toml and manifest.json."""

import json
import re
import sys
from pathlib import Path

DOCKER_IMAGE_LINE = re.compile(
    rb'(?m)^([ \t]*docker_image[ \t]*=[ \t]*")[^"\r\n]*("[ \t]*(?:\r?\n|\Z))'
)


def update_task_file(path, image):
    content = path.read_bytes()
    updated, count = DOCKER_IMAGE_LINE.subn(
        lambda match: match.group(1) + image.encode() + match.group(2), content
    )
    if count != 1:
        raise ValueError(f"{path}: expected one docker_image line, found {count}")
    path.write_bytes(updated)


def record(folder, root=None):
    folder = Path(folder)
    root = Path.cwd() if root is None else Path(root)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for publish_path in sorted(folder.rglob("*.publish.json")):
        published = json.loads(publish_path.read_text(encoding="utf-8"))
        task = published["task"]
        record = manifest["tasks"][task]
        if record["status"] == "skipped":
            continue

        image = published["image"]
        if image is not None:
            update_task_file(root / task / "task.toml", image)
            record["image"] = image
        record["status"] = "verified-ci" if published["verdict"] == "verified" else "failing"
        run_url = published["run_url"]
        if record["status"] == "verified-ci":
            record["evidence"] = run_url
        else:
            record["evidence"] = {"run": run_url, "reason": published["reason"]}

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: record_ci.py FOLDER")
    record(args[0])


if __name__ == "__main__":
    main()
