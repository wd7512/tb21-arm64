import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_build_network_host_is_passed_to_buildx(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    args_file = tmp_path / "docker-args"
    docker = bin_dir / "docker"
    docker.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" >"$DOCKER_ARGS_FILE"\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["DOCKER_ARGS_FILE"] = str(args_file)
    env["BUILD_NETWORK"] = "host"

    subprocess.run(
        ["bash", str(ROOT / "tools" / "build.sh"), "fix-git"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    args = args_file.read_text(encoding="utf-8").splitlines()
    assert args[:2] == ["buildx", "build"]
    assert args[args.index("--network") + 1] == "host"
