"""Compare package, configuration, and work-directory contents of Docker images."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from email.parser import Parser
from pathlib import PurePosixPath

SECTIONS = ("config", "dpkg", "apk", "python", "npm", "files")


def parse_dpkg(text):
    packages = {}
    for stanza in re.split(r"\n\s*\n", text):
        fields = {}
        for line in stanza.splitlines():
            if line and not line[0].isspace() and ":" in line:
                key, value = line.split(":", 1)
                fields[key] = value.strip()
        if fields.get("Status", "").split()[-1:] == ["installed"]:
            if "Package" in fields and "Version" in fields:
                packages[fields["Package"]] = fields["Version"]
    return packages


def parse_apk(text):
    packages = {}
    for stanza in re.split(r"\n\s*\n", text):
        fields = {}
        for line in stanza.splitlines():
            if len(line) > 2 and line[1] == ":":
                fields[line[0]] = line[2:]
        if "P" in fields and "V" in fields:
            packages[fields["P"]] = fields["V"]
    return packages


def parse_metadata(text):
    metadata = Parser().parsestr(text)
    name = metadata.get("Name")
    version = metadata.get("Version")
    if name is None or version is None:
        return None
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    return normalized, version


def _merge_version(inventory, name, version):
    versions = set(inventory.get(name, "").split(",")) - {""}
    versions.add(version)
    inventory[name] = ",".join(sorted(versions))


def _under(path, directory):
    path = PurePosixPath(path.lstrip("/"))
    directory = PurePosixPath(directory.lstrip("/"))
    if str(directory) == ".":
        return path.as_posix()
    try:
        relative = path.relative_to(directory)
    except ValueError:
        return None
    return relative.as_posix() if relative.parts else None


def _is_python_metadata(path):
    parts = PurePosixPath(path).parts
    return (
        len(parts) >= 3
        and parts[-1] == "METADATA"
        and parts[-2].endswith(".dist-info")
        and any(part in ("site-packages", "dist-packages") for part in parts[:-2])
    )


def _npm_package_path(path):
    parts = PurePosixPath(path).parts
    for index, part in enumerate(parts):
        if part != "node_modules":
            continue
        package_parts = parts[index + 1 :]
        if (len(package_parts) == 2 and package_parts[1] == "package.json") or (
            len(package_parts) == 3
            and package_parts[0].startswith("@")
            and package_parts[2] == "package.json"
        ):
            return True
    return False


def build_inventory(tar_stream, workdir):
    inventory = {section: {} for section in SECTIONS}
    inventory["npm_unparsed"] = 0
    dpkg_text = None
    apk_text = None
    with tarfile.open(fileobj=tar_stream, mode="r|") as archive:
        for member in archive:
            relative = _under(member.name, workdir)
            if member.issym():
                if relative is not None:
                    inventory["files"][relative] = f"link:{member.linkname}"
                continue
            if member.islnk():
                if relative is not None:
                    inventory["files"][relative] = f"hardlink:{member.linkname}"
                continue
            if not member.isfile():
                continue
            is_dpkg = member.name == "var/lib/dpkg/status"
            is_apk = member.name == "lib/apk/db/installed"
            is_python = _is_python_metadata(member.name)
            is_npm = _npm_package_path(member.name)
            if not (is_dpkg or is_apk or is_python or is_npm or relative is not None):
                continue
            file_obj = archive.extractfile(member)
            if file_obj is None:
                continue
            if relative is not None and not (is_dpkg or is_apk or is_python or is_npm):
                digest = hashlib.file_digest(file_obj, "sha256")
                inventory["files"][relative] = f"sha256:{digest.hexdigest()}"
                continue
            data = file_obj.read()
            if relative is not None:
                inventory["files"][relative] = f"sha256:{hashlib.sha256(data).hexdigest()}"
            if is_dpkg:
                dpkg_text = data.decode(errors="replace")
            elif is_apk:
                apk_text = data.decode(errors="replace")
            if is_python:
                parsed = parse_metadata(data.decode(errors="replace"))
                if parsed:
                    _merge_version(inventory["python"], *parsed)
            if is_npm:
                try:
                    package = json.loads(data)
                    name = package["name"]
                    version = package["version"]
                    if not isinstance(name, str) or not isinstance(version, (str, int, float)):
                        raise ValueError("missing package name or version")
                    _merge_version(inventory["npm"], name, str(version))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    inventory["npm_unparsed"] += 1
    if dpkg_text is not None:
        inventory["dpkg"] = parse_dpkg(dpkg_text)
    if apk_text is not None:
        inventory["apk"] = parse_apk(apk_text)
    return inventory


def _config_values(config):
    values = dict(config)
    env = values.get("Env")
    if isinstance(env, list):
        values["Env"] = {
            item.split("=", 1)[0]: item.split("=", 1)[1] if "=" in item else "" for item in env
        }
    return values


def diff_inventories(upstream, candidate):
    differences = {}
    for section in SECTIONS:
        left = (
            _config_values(upstream.get(section, {}))
            if section == "config"
            else upstream.get(section, {})
        )
        right = (
            _config_values(candidate.get(section, {}))
            if section == "config"
            else candidate.get(section, {})
        )
        left_keys = set(left)
        right_keys = set(right)
        differences[section] = {
            "added": {key: right[key] for key in sorted(right_keys - left_keys)},
            "removed": {key: left[key] for key in sorted(left_keys - right_keys)},
            "changed": {
                key: [left[key], right[key]]
                for key in sorted(left_keys & right_keys)
                if left[key] != right[key]
            },
        }
    return differences


def _inspect_image(ref, run):
    result = run(["docker", "image", "inspect", ref], check=True, capture_output=True, text=True)
    image = json.loads(result.stdout)[0]
    config = image.get("Config") or {}
    selected = {
        "Architecture": image["Architecture"],
        "Os": image["Os"],
        **{key: config.get(key) for key in ("WorkingDir", "Env", "Entrypoint", "Cmd", "User")},
    }
    if isinstance(selected["Env"], list):
        selected["Env"] = {
            item.split("=", 1)[0]: item.split("=", 1)[1] if "=" in item else ""
            for item in selected["Env"]
        }
    return selected


def _export_inventory(ref, config, workdir, run):
    created = run(
        ["docker", "create", "--platform", f"{config['Os']}/{config['Architecture']}", ref],
        check=True,
        capture_output=True,
        text=True,
    )
    container_id = created.stdout.strip()
    try:
        with tempfile.TemporaryFile() as exported:
            run(["docker", "export", container_id], check=True, stdout=exported)
            exported.seek(0)
            inventory = build_inventory(exported, workdir)
    finally:
        run(["docker", "rm", container_id], check=True, capture_output=True, text=True)
    return inventory


def _counts(inventory, config):
    counts = {
        section: len(inventory[section]) for section in ("dpkg", "apk", "python", "npm", "files")
    }
    counts["config"] = len(config)
    counts["npm_unparsed"] = inventory.get("npm_unparsed", 0)
    return counts


def compare_images(upstream_ref, candidate_ref, out_path, workdir=None, run=subprocess.run):
    upstream_config = _inspect_image(upstream_ref, run)
    candidate_config = _inspect_image(candidate_ref, run)
    chosen_workdir = workdir or upstream_config.get("WorkingDir") or "/app"
    upstream = _export_inventory(upstream_ref, upstream_config, chosen_workdir, run)
    candidate = _export_inventory(candidate_ref, candidate_config, chosen_workdir, run)
    differences = diff_inventories(
        {"config": upstream_config, **upstream}, {"config": candidate_config, **candidate}
    )
    report = {
        "upstream": {
            "ref": upstream_ref,
            "config": upstream_config,
            "counts": _counts(upstream, upstream_config),
        },
        "candidate": {
            "ref": candidate_ref,
            "config": candidate_config,
            "counts": _counts(candidate, candidate_config),
        },
        "differences": differences,
    }
    with open(out_path, "w", encoding="utf-8") as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write("\n")
    return report


def _print_summary(report):
    for section, diff in report["differences"].items():
        print(
            f"{section}: added {len(diff['added'])}, removed {len(diff['removed'])}, "
            f"changed {len(diff['changed'])}"
        )
    for section in ("config", "dpkg", "python", "npm"):
        for key, values in list(report["differences"][section]["changed"].items())[:20]:
            print(f"  {section}.{key}: {values[0]} -> {values[1]}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream_ref")
    parser.add_argument("candidate_ref")
    parser.add_argument("--out", required=True)
    parser.add_argument("--workdir")
    args = parser.parse_args(argv)
    report = compare_images(args.upstream_ref, args.candidate_ref, args.out, args.workdir)
    _print_summary(report)


if __name__ == "__main__":
    main()
