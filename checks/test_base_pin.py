import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.base_pin import (
    Hub,
    Unresolved,
    amd64_layers,
    dated_candidates,
    layer_markers,
    pick_base,
    resolve_python_base,
    rewrite_from,
)

UBUNTU_ROOT = "249778a1782b02a1c2bcf9f292f5778d81442a53c3de1958d712f10baf7e0b60"
OTHER_ROOT = "ddf1aa62235de6657123492b19d27d937c25668011b5ebf923a3f019200f8540"


def ubuntu_images(root):
    return [
        {
            "architecture": "amd64",
            "digest": "sha256:90101b2e",
            "layers": [
                {"size": 0, "instruction": " ARG RELEASE"},
                {"size": 0, "instruction": " LABEL org.opencontainers.image.version=24.04"},
                {
                    "digest": "sha256:4b3ffd8c",
                    "size": 29723147,
                    "instruction": f"ADD file:{root} in / ",
                },
                {"size": 0, "instruction": ' CMD ["/bin/bash"]'},
            ],
        },
        {"architecture": "unknown", "digest": "sha256:attestation", "layers": []},
    ]


PYTHON_IMAGES = [
    {
        "architecture": "amd64",
        "layers": [
            {
                "digest": "sha256:b1badc6e",
                "size": 28230255,
                "instruction": "# debian.sh --arch 'amd64' out/ 'bookworm' '@1754870400'",
            },
            {"size": 0, "instruction": "ENV PYTHON_VERSION=3.13.7"},
        ],
    }
]


def test_ubuntu_exact_match_picks_the_tag_with_the_upstream_rootfs():
    markers = layer_markers(amd64_layers(ubuntu_images(UBUNTU_ROOT)))
    assert markers["root"] == f"ADD file:{UBUNTU_ROOT}"
    listing = [
        {"name": "noble-20251013", "digest": "sha256:aaa"},
        {"name": "noble-20251001", "digest": "sha256:bbb"},
        {"name": "noble-20250925", "digest": "sha256:ccc"},
    ]
    roots = {"noble-20251013": OTHER_ROOT, "noble-20251001": UBUNTU_ROOT, "noble-20250925": "0"}
    candidate, kind = pick_base(
        listing, markers["root"], lambda name: amd64_layers(ubuntu_images(roots[name]))
    )
    assert (candidate["name"], candidate["digest"], kind) == (
        "noble-20251001",
        "sha256:bbb",
        "exact",
    )


def test_python_version_and_codename_come_from_upstream_layers(tmp_path):
    markers = layer_markers(amd64_layers(PYTHON_IMAGES))
    assert markers["python"] == "3.13.7"
    assert markers["debian_sh"] == ("bookworm", "1754870400")
    url = "https://hub.docker.com/v2/repositories/library/python/tags/3.13.7-slim-bookworm"
    hub = Hub(tmp_path, opener=lambda u: {"digest": "sha256:idx"} if u == url else None)
    new, kind, evidence = resolve_python_base(hub, "3.13-slim-bookworm", markers, "20251031")
    assert (new, kind) == ("python:3.13.7-slim-bookworm@sha256:idx", "python-exact")
    assert "bookworm @20250811" in evidence


def test_python_without_debian_sh_is_left_unresolved(tmp_path):
    markers = layer_markers([{"instruction": "ENV PYTHON_VERSION=3.13.7"}])
    with pytest.raises(Unresolved, match="Debian codename"):
        resolve_python_base(Hub(tmp_path, opener=lambda u: None), "3.13", markers, "20251031")


def test_no_rootfs_match_falls_back_to_the_newest_tag_on_or_before_the_date():
    results = [
        {"name": "noble-20251101", "digest": "sha256:late"},
        {"name": "noble-20251013", "digest": "sha256:new"},
        {"name": "noble-20250925", "digest": "sha256:old"},
        {"name": "noble-20250925-extra", "digest": "sha256:x"},
    ]
    candidates = dated_candidates(results, r"noble-(\d{8})", "20251031")
    assert [c["name"] for c in candidates] == ["noble-20251013", "noble-20250925"]
    candidate, kind = pick_base(
        candidates, f"ADD file:{UBUNTU_ROOT}", lambda name: amd64_layers(ubuntu_images(OTHER_ROOT))
    )
    assert (candidate["name"], kind) == ("noble-20251013", "nearest")


def test_rewrite_keeps_stage_names_and_every_other_line():
    text = (
        "# canary\r\nFROM ubuntu:24.04 as build\nRUN echo hi \\\n  && true\n"
        "FROM ubuntu:24.04 AS target \nCOPY --from=build /a /b\n"
    )
    out = rewrite_from(text, {"ubuntu:24.04": "ubuntu:noble-20251001@sha256:bbb"}.get)
    assert out == (
        "# canary\r\nFROM ubuntu:noble-20251001@sha256:bbb as build\nRUN echo hi \\\n  && true\n"
        "FROM ubuntu:noble-20251001@sha256:bbb AS target \nCOPY --from=build /a /b\n"
    )
