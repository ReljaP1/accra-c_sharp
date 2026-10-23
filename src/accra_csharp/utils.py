import json
import os
import shlex
from functools import cache
from pathlib import Path
from xml.etree import ElementTree

from accra_language import DockerfileInstruction

from .constants import INSTALLABLE_CHANNELS, TFM_CHANNELS

EXCLUDED_DIRECTORIES = {".git", ".dotnet", "bin", "obj", ".vs", ".idea"}
_SHELL_META = set(" <>|&;$'`\\*?()[]{}")


def channel_of(version: str) -> str | None:
    """The SDK channel of a version string such as 8.0.401."""
    major, separator, minor = version.partition(".")
    if not separator:
        return None
    minor = minor.split(".", 1)[0].split("-", 1)[0]
    if not major.isdigit() or not minor.isdigit():
        return None
    return f"{int(major)}.{int(minor)}"


def channel_key(channel: str) -> tuple[int, int]:
    major, minor = channel.split(".")
    return (int(major), int(minor))


def highest_channel(channels: set[str]) -> str:
    return max(channels, key=channel_key)


def portable_frameworks(frameworks: set[str]) -> set[str]:
    """Target frameworks a Linux SDK can build."""
    return {
        framework
        for framework in frameworks
        if "-" not in framework and framework in TFM_CHANNELS
    }


def framework_rank(framework: str) -> tuple[int, int, int]:
    if framework.startswith("netstandard"):
        family = 0
        rest = framework.removeprefix("netstandard")
    elif framework.startswith("netcoreapp"):
        family = 1
        rest = framework.removeprefix("netcoreapp")
    elif framework.startswith("net"):
        family = 2
        rest = framework.removeprefix("net")
    else:
        return (-1, 0, 0)
    major, _, minor = rest.partition(".")
    return (family, int(major or 0), int(minor or 0))


def buildable_frameworks(frameworks: set[str], channels: set[str]) -> list[str]:
    """Every portable framework one of the installed SDK channels can build."""
    matching = [
        framework
        for framework in portable_frameworks(frameworks)
        if TFM_CHANNELS[framework] & channels
    ]
    return sorted(matching, key=framework_rank)


def framework_from_legacy_version(value: str) -> str:
    digits = value.strip().lstrip("vV").replace(".", "")
    return f"net{digits}"


def git_root(path: Path) -> Path | None:
    current = path.resolve()
    if (current / ".git").exists():
        return current
    for parent in current.parents:
        if (parent / ".git").exists():
            return parent
    return None


def upward_directories(start: Path) -> list[Path]:
    """start and its parents up to the git root. A directory outside a repo stays put."""
    resolved = start.resolve()
    root = git_root(resolved)
    directories = [resolved]
    if root is None or root == resolved:
        return directories
    for parent in resolved.parents:
        directories.append(parent)
        if parent == root:
            break
    return directories


def iter_files(root: Path, name: str) -> list[Path]:
    """Files named name under root. A leading * matches the suffix."""
    matches: list[Path] = []
    if not root.is_dir():
        return matches
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [entry for entry in dirnames if entry not in EXCLUDED_DIRECTORIES]
        for filename in filenames:
            if name.startswith("*"):
                matched = filename.endswith(name[1:])
            else:
                matched = filename == name
            if matched:
                matches.append(Path(directory) / filename)
    return sorted(matches)


def find_named(start: Path, name: str) -> list[Path]:
    found: list[Path] = []
    for directory in upward_directories(start):
        candidate = directory / name
        if candidate.is_file():
            found.append(candidate)
    found.extend(path for path in iter_files(start, name) if path not in found)
    return found


def sdk_version_from_global_json(document: object) -> str | None:
    if not isinstance(document, dict):
        return None
    sdk = document.get("sdk")
    if isinstance(sdk, dict) and isinstance(sdk.get("version"), str):
        return sdk["version"]
    tools = document.get("tools")
    if isinstance(tools, dict) and isinstance(tools.get("dotnet"), str):
        return tools["dotnet"]
    return None


def local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_xml(path: Path) -> ElementTree.Element | None:
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return ElementTree.parse(handle).getroot()
    except (OSError, ElementTree.ParseError):
        return None


def read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def unconstrained_channels() -> set[str]:
    return set(INSTALLABLE_CHANNELS)


def dockerfile_run(args: list[str]) -> DockerfileInstruction:
    rendered: list[str] = []
    for arg in args:
        if any(character in arg for character in _SHELL_META):
            rendered.append(shlex.quote(arg))
        else:
            rendered.append(arg)
    return DockerfileInstruction("RUN " + " ".join(rendered))


@cache
def docker_setup_workdir(repo: str) -> list[DockerfileInstruction]:
    return [
        DockerfileInstruction(f"RUN git clone {repo} /project"),
        DockerfileInstruction("WORKDIR /project"),
    ]


DOCKER_CREATE_USER: list[DockerfileInstruction] = [
    DockerfileInstruction(
        'RUN adduser \
                --disabled-password \
                --gecos "" \
                --home "/home/appuser" \
                --shell "/bin/bash" \
                --uid "10001" \
                appuser'
    )
]


DOCKER_SWITCH_USER: list[DockerfileInstruction] = [
    DockerfileInstruction("RUN chown -R appuser:appuser /project"),
    DockerfileInstruction("USER appuser"),
]
