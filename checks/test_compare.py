import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.compare import (
    build_inventory,
    diff_inventories,
    parse_apk,
    parse_dpkg,
    parse_metadata,
)


def _tar(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = data
                archive.addfile(info)
            else:
                body = data.encode()
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
    stream.seek(0)
    return stream


def test_package_parsers():
    dpkg = """Package: kept\nStatus: install ok installed\nVersion: 1.2\n
Package: removed\nStatus: deinstall ok config-files\nVersion: 2.0\n
Package: purged\nStatus: purge ok not-installed\nVersion: 3.0\n"""
    assert parse_dpkg(dpkg) == {"kept": "1.2"}
    assert parse_apk("P:busybox\nV:1.36\n\nP:musl\nV:1.2\n") == {
        "busybox": "1.36",
        "musl": "1.2",
    }
    assert parse_metadata("Name: BeautifulSoup4\nVersion: 4.12\n") == (
        "beautifulsoup4",
        "4.12",
    )


def test_build_inventory_and_diff():
    upstream = _tar(
        [
            (
                "var/lib/dpkg/status",
                "Package: common\nStatus: install ok installed\nVersion: 1\n\n"
                "Package: old\nStatus: deinstall ok config-files\nVersion: 1\n",
                "file",
            ),
            ("lib/apk/db/installed", "P:busybox\nV:1.0\n", "file"),
            (
                "usr/lib/python3/site-packages/bs4.dist-info/METADATA",
                "Name: BeautifulSoup4\nVersion: 1.0\n",
                "file",
            ),
            (
                "app/node_modules/@scope/pkg/package.json",
                json.dumps({"name": "@scope/pkg", "version": "1.0"}),
                "file",
            ),
            ("app/unchanged.txt", "same", "file"),
            ("app/old.txt", "gone", "file"),
            ("app/old-link", "target-old", "symlink"),
        ]
    )
    candidate = _tar(
        [
            (
                "var/lib/dpkg/status",
                "Package: common\nStatus: install ok installed\nVersion: 2\n\n"
                "Package: added\nStatus: install ok installed\nVersion: 3\n",
                "file",
            ),
            ("lib/apk/db/installed", "P:busybox\nV:1.1\n\nP:apk-added\nV:2\n", "file"),
            (
                "usr/lib/python3/site-packages/bs4.dist-info/METADATA",
                "Name: BeautifulSoup4\nVersion: 2.0\n",
                "file",
            ),
            (
                "usr/lib/python3/site-packages/new.dist-info/METADATA",
                "Name: New_Package\nVersion: 1.0\n",
                "file",
            ),
            (
                "app/node_modules/@scope/pkg/package.json",
                json.dumps({"name": "@scope/pkg", "version": "2.0"}),
                "file",
            ),
            ("app/node_modules/bad/package.json", "{not json", "file"),
            ("app/unchanged.txt", "same", "file"),
            ("app/new.txt", "new", "file"),
            ("app/old-link", "target-new", "symlink"),
        ]
    )
    left = build_inventory(upstream, "/app")
    right = build_inventory(candidate, "/app")
    diff = diff_inventories(left, right)

    assert left["dpkg"] == {"common": "1"}
    assert left["python"] == {"beautifulsoup4": "1.0"}
    assert left["npm"] == {"@scope/pkg": "1.0"}
    assert right["npm_unparsed"] == 1
    assert diff["dpkg"] == {
        "added": {"added": "3"},
        "removed": {},
        "changed": {"common": ["1", "2"]},
    }
    assert diff["apk"] == {
        "added": {"apk-added": "2"},
        "removed": {},
        "changed": {"busybox": ["1.0", "1.1"]},
    }
    assert diff["python"] == {
        "added": {"new-package": "1.0"},
        "removed": {},
        "changed": {"beautifulsoup4": ["1.0", "2.0"]},
    }
    assert diff["npm"]["changed"] == {"@scope/pkg": ["1.0", "2.0"]}
    assert diff["files"]["added"]["new.txt"] == "sha256:" + hashlib.sha256(b"new").hexdigest()
    assert diff["files"]["removed"]["old.txt"] == "sha256:" + hashlib.sha256(b"gone").hexdigest()
    assert diff["files"]["changed"]["old-link"] == ["link:target-old", "link:target-new"]


def test_config_env_is_compared_by_key():
    first = {"config": {"Env": ["A=1", "B=2"], "Cmd": ["run"]}}
    second = {"config": {"Env": ["B=2", "A=1"], "Cmd": ["run"]}}
    assert diff_inventories(first, second)["config"] == {
        "added": {},
        "removed": {},
        "changed": {},
    }
