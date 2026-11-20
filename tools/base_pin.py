"""Pin each task Dockerfile's base image to what the upstream image was built from.

Usage: uv run python tools/base_pin.py [--write] [TASK...]

Reads Docker Hub's public API (cached in $TB21_HUB_CACHE, default ~/.cache/tb21-base-pin) and
never pulls from a registry. Prints a markdown table; with --write rewrites the FROM lines.
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

HUB = "https://hub.docker.com/v2/repositories"
ROOT = Path(__file__).resolve().parents[1]
WINDOW = 40
FROM_LINE = re.compile(r"^(FROM[ \t]+)(\S+)(.*)$", re.MULTILINE)
PLAIN_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?$")
ADD_FILE = re.compile(r"ADD file:([0-9a-f]{64}) in /")
DEBIAN_SH = re.compile(r"debian\.sh --arch '[^']*' out/ '([a-z]+)' '@(\d+)'")
PYTHON_VERSION = re.compile(r"ENV PYTHON_VERSION=(\S+)")
PYTHON_TAG = re.compile(r"^\d+(\.\d+)*(-slim)?(-(bookworm|trixie|bullseye))?$")
DEBIAN_CODENAMES = {"11": "bullseye", "12": "bookworm", "13": "trixie"}

log = logging.getLogger("base_pin")


class Unresolved(Exception):
    pass


@dataclass
class Resolution:
    old: str
    new: str
    match: str
    evidence: str


def parse_from(token):
    """Return (repo, tag) for a plain `image[:tag]` token, else None."""
    if "@" in token or "$" in token or not PLAIN_IMAGE.match(token):
        return None
    repo, _, tag = token.partition(":")
    return repo, tag or "latest"


def rewrite_from(text, resolve):
    """Replace the image token of each FROM line with resolve(token), if it returns one."""

    def sub(m):
        new = resolve(m.group(2))
        return m.group(1) + (new or m.group(2)) + m.group(3)

    return FROM_LINE.sub(sub, text)


def amd64_layers(images):
    for image in images:
        if image.get("architecture") == "amd64":
            return image.get("layers", [])
    raise Unresolved("no amd64 image")


def layer_markers(layers):
    """Facts about the base and Python read from a layer list."""
    marks = {"root": None, "debian_sh": None, "python": None}
    for layer in layers:
        text = layer.get("instruction", "").strip()
        if marks["root"] is None and (m := ADD_FILE.search(text)):
            marks["root"] = f"ADD file:{m.group(1)}"
        if marks["debian_sh"] is None and (m := DEBIAN_SH.search(text)):
            marks["debian_sh"] = (m.group(1), m.group(2))
            if marks["root"] is None and layer.get("digest"):
                marks["root"] = f"layer {layer['digest']}"
        if marks["python"] is None and (m := PYTHON_VERSION.search(text)):
            marks["python"] = m.group(1)
    return marks


def debian_sh_date(epoch):
    return datetime.fromtimestamp(int(epoch), UTC).strftime("%Y%m%d")


def dated_candidates(results, pattern, not_after):
    """Dated tags `{name,digest}` from a tag listing, newest first, not after `not_after`."""
    rx = re.compile(pattern)
    found = []
    for tag in results:
        m = rx.fullmatch(tag["name"])
        if m and m.group(1) <= not_after:
            found.append((m.group(1), tag["name"], tag["digest"]))
    found.sort(reverse=True)
    return [{"name": name, "digest": digest} for _, name, digest in found]


def pick_base(candidates, upstream_root, layers_of, window=WINDOW):
    """Return (candidate, 'exact') for the tag whose rootfs equals upstream's, else the newest."""
    if not candidates:
        raise Unresolved("no dated tag on or before the upstream date")
    for candidate in candidates[:window]:
        if layer_markers(layers_of(candidate["name"]))["root"] == upstream_root:
            return candidate, "exact"
    return candidates[0], "nearest"


class Hub:
    def __init__(self, cache_dir, opener=None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.opener = opener or self._open

    @staticmethod
    def _open(url):
        request = urllib.request.Request(url, headers={"User-Agent": "tb21-base-pin"})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.load(response)
            except urllib.error.HTTPError as err:
                if err.code == 404:
                    return None
                if err.code != 429 and err.code < 500:
                    raise
                time.sleep(2**attempt)
        raise Unresolved(f"Docker Hub kept failing for {url}")

    def get(self, url):
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if path.exists():
            return json.loads(path.read_text())
        data = self.opener(url)
        path.write_text(json.dumps(data))
        return data

    def images(self, namespace, repo, tag):
        data = self.get(f"{HUB}/{namespace}/{repo}/tags/{tag}/images")
        if data is None:
            raise Unresolved(f"{namespace}/{repo}:{tag} not found")
        return data

    def tag(self, namespace, repo, tag):
        return self.get(f"{HUB}/{namespace}/{repo}/tags/{tag}")

    def tag_listing(self, repo, prefix, oldest):
        """Tags named `prefix*`, newest first, paging until a page reaches before `oldest`."""
        url = f"{HUB}/library/{repo}/tags?name={prefix}&page_size=100"
        results = []
        while url:
            page = self.get(url)
            results += page["results"]
            dates = [r["last_updated"][:10].replace("-", "") for r in page["results"]]
            if not dates or min(dates) < oldest:
                break
            url = page.get("next")
        return results


def base_family(repo, tag):
    """Return (codename, slim) for a ubuntu or debian base tag."""
    if repo == "ubuntu" and tag == "24.04":
        return "noble", False
    if repo == "debian":
        slim = tag.endswith("-slim")
        name = tag.removesuffix("-slim")
        if name in DEBIAN_CODENAMES.values():
            return name, slim
        if name.split(".")[0] in DEBIAN_CODENAMES:
            return DEBIAN_CODENAMES[name.split(".")[0]], slim
    raise Unresolved(f"unsupported base {repo}:{tag}")


def resolve_os_base(hub, repo, tag, marks, upstream_date):
    codename, slim = base_family(repo, tag)
    if not marks["root"]:
        raise Unresolved("upstream layers have no readable rootfs layer")
    if repo == "ubuntu" and marks["debian_sh"]:
        raise Unresolved("upstream base is Debian, not ubuntu")
    if repo == "debian" and marks["debian_sh"] and marks["debian_sh"][0] != codename:
        raise Unresolved(f"upstream base is Debian {marks['debian_sh'][0]}, not {codename}")
    suffix = "-slim" if slim else ""
    pattern = rf"{codename}-(\d{{8}}){re.escape(suffix)}"
    oldest = f"{int(upstream_date[:4]) - 1}{upstream_date[4:]}"
    listing = hub.tag_listing(repo, f"{codename}-20", oldest)
    if marks["debian_sh"]:
        upstream_date = min(upstream_date, debian_sh_date(marks["debian_sh"][1]))
    candidates = dated_candidates(listing, pattern, upstream_date)
    candidate, kind = pick_base(
        candidates, marks["root"], lambda name: amd64_layers(hub.images("library", repo, name))
    )
    new = f"{repo}:{candidate['name']}@{candidate['digest']}"
    if kind == "exact":
        evidence = marks["root"]
    else:
        evidence = f"no rootfs match in {min(len(candidates), WINDOW)} tags; newest on or before"
        evidence += f" {upstream_date}"
    return new, kind, evidence


def resolve_python_base(hub, tag, marks, upstream_date):
    version = marks["python"]
    if not version:
        raise Unresolved("upstream layers have no PYTHON_VERSION")
    if not marks["debian_sh"]:
        raise Unresolved("upstream layers do not name the Debian codename")
    codename, epoch = marks["debian_sh"]
    slim = "-slim" if "slim" in tag else ""
    new_tag = f"{version}{slim}-{codename}"
    data = hub.tag("library", "python", new_tag)
    if data is None:
        raise Unresolved(f"python:{new_tag} not found")
    evidence = f"PYTHON_VERSION={version}; debian.sh {codename} @{debian_sh_date(epoch)}"
    return f"python:{new_tag}@{data['digest']}", "python-exact", evidence


def upstream_facts(hub, task, image):
    namespace, rest = image.split("/", 1)
    repo, _, tag = rest.partition(":")
    marks = layer_markers(amd64_layers(hub.images(namespace, repo, tag)))
    meta = hub.tag(namespace, repo, tag)
    date = meta["last_updated"][:10].replace("-", "")
    return marks, date


def resolve_token(hub, token, marks, upstream_date):
    parsed = parse_from(token)
    if parsed is None:
        raise Unresolved("FROM is not a plain image[:tag]")
    repo, tag = parsed
    if repo in ("ubuntu", "debian"):
        return resolve_os_base(hub, repo, tag, marks, upstream_date)
    if repo == "python" and PYTHON_TAG.match(tag):
        return resolve_python_base(hub, tag, marks, upstream_date)
    raise Unresolved(f"unsupported base {token}")


def process_task(hub, root, task, manifest, write):
    dockerfile = root / task / "environment" / "Dockerfile"
    text = dockerfile.read_bytes().decode()
    tokens = [m.group(2) for m in FROM_LINE.finditer(text)]
    rows, mapping = [], {}
    try:
        marks, date = upstream_facts(hub, task, manifest["tasks"][task]["upstream"]["image"])
    except Unresolved as err:
        return [(task, t, t, "unchanged", f"upstream unreadable: {err}") for t in tokens], False
    for token in dict.fromkeys(tokens):
        if "@" in token:
            rows.append((task, token, token, "unchanged", "already pinned by digest"))
            continue
        try:
            new, kind, evidence = resolve_token(hub, token, marks, date)
        except Unresolved as err:
            rows.append((task, token, token, "unchanged", str(err)))
            continue
        mapping[token] = new
        rows.append((task, token, new, kind, evidence))
    changed = False
    if mapping:
        new_text = rewrite_from(text, mapping.get)
        changed = new_text != text
        if write and changed:
            dockerfile.write_bytes(new_text.encode())
    return rows, changed


def format_table(rows):
    lines = ["| task | old FROM | new FROM | match | evidence |", "| --- | --- | --- | --- | --- |"]
    for task, old, new, kind, evidence in rows:
        lines.append(f"| {task} | `{old}` | `{new}` | {kind} | {evidence} |")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="rewrite the FROM lines in place")
    parser.add_argument("tasks", nargs="*", metavar="TASK")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    manifest = json.loads((ROOT / "manifest.json").read_text())
    tasks = args.tasks or sorted(manifest["tasks"])
    cache = os.environ.get("TB21_HUB_CACHE") or Path.home() / ".cache" / "tb21-base-pin"
    hub = Hub(cache)
    rows, changed = [], []
    for task in tasks:
        log.info("resolving %s", task)
        task_rows, did_change = process_task(hub, ROOT, task, manifest, args.write)
        rows += task_rows
        if did_change:
            changed.append(task)
    sys.stdout.write(format_table(rows) + "\n")
    counts = {}
    for row in rows:
        counts[row[3]] = counts.get(row[3], 0) + 1
    log.info("rows by match: %s; Dockerfiles that change: %d", counts, len(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
