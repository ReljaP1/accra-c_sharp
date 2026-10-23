from dataclasses import dataclass
from pathlib import Path
from typing import override
from xml.etree import ElementTree

from accra_language import AccraError, Config, Dependency, Manifest, ManifestSpec

from .constants import MONO_VERSION, TFM_CHANNELS
from .utils import (
    find_named,
    framework_from_legacy_version,
    iter_files,
    local_tag,
    portable_frameworks,
    read_xml,
)


def _frameworks(root: ElementTree.Element) -> set[str]:
    found: set[str] = set()
    for element in root.iter():
        name = local_tag(element.tag)
        if name in {"TargetFramework", "TargetFrameworks"} and element.text:
            for item in element.text.replace(",", ";").split(";"):
                framework = item.strip()
                if framework:
                    found.add(framework)
        if name == "TargetFrameworkVersion" and element.text:
            found.add(framework_from_legacy_version(element.text))
    return found


def _package_versions(root: ElementTree.Element) -> dict[str, str]:
    versions: dict[str, str] = {}
    for element in root.iter():
        if local_tag(element.tag) != "PackageVersion":
            continue
        name = element.attrib.get("Include")
        if name:
            versions[name] = element.attrib.get("Version", "").strip()
    return versions


def central_versions(project: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for path in find_named(project, "Directory.Packages.props"):
        root = read_xml(path)
        if root is not None:
            versions.update(_package_versions(root))
    return versions


@dataclass(frozen=True)
class CSharpProject:
    path: Path
    frameworks: set[str]
    dependencies: set[Dependency]
    sdk_style: bool


def _dependencies(
    root: ElementTree.Element, versions: dict[str, str]
) -> set[Dependency]:
    dependencies: set[Dependency] = set()
    for element in root.iter():
        if local_tag(element.tag) != "PackageReference":
            continue
        name = element.attrib.get("Include") or element.attrib.get("Update")
        if not name:
            continue
        version = element.attrib.get("Version", "").strip()
        if not version:
            for child in element:
                if local_tag(child.tag) == "Version" and child.text:
                    version = child.text.strip()
        if not version:
            version = versions.get(name, "")
        dependencies.add(Dependency(name=name, version=version))
    return dependencies


class Csproj(Manifest):
    def __init__(self, config: Config):
        spec = ManifestSpec(name="csproj", version="", config=config)
        super().__init__(spec)
        self.projects: list[CSharpProject] = []

    def _root(self) -> Path | None:
        cwd = self.spec.config.cwd
        if cwd is None:
            return None
        return Path(cwd)

    @override
    def detect(self) -> bool:
        root = self._root()
        if root is None:
            return False
        self.projects = []
        versions = central_versions(root)
        for path in iter_files(root, "*.csproj"):
            document = read_xml(path)
            if document is None:
                continue
            frameworks = _frameworks(document)
            self.projects.append(
                CSharpProject(
                    path=path,
                    frameworks=frameworks,
                    dependencies=_dependencies(document, versions),
                    sdk_style="Sdk" in document.attrib,
                )
            )
        return bool(self.projects)

    @override
    def extract_dependencies(self) -> set[Dependency] | None:
        dependencies: set[Dependency] = set()
        for project in self.projects:
            dependencies.update(project.dependencies)
        if not dependencies:
            return None
        return dependencies

    @override
    def get_supported_language_versions(self) -> set[str] | AccraError:
        channels: set[str] = set()
        saw_portable = False
        for project in self.projects:
            portable = portable_frameworks(project.frameworks)
            if not portable:
                continue
            saw_portable = True
            for framework in portable:
                channels.update(TFM_CHANNELS[framework])
        if saw_portable:
            return channels
        if any(
            project.frameworks and not project.sdk_style for project in self.projects
        ):
            return {MONO_VERSION}
        return set()
