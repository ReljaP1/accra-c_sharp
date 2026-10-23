from typing import override
from xml.etree import ElementTree

from accra_language import AccraError, Config, Dependency, Manifest, ManifestSpec

from .utils import iter_files, local_tag, read_xml, unconstrained_channels


class Packages_config(Manifest):
    def __init__(self, config: Config):
        spec = ManifestSpec(name="packages.config", version="", config=config)
        super().__init__(spec)
        self._dependencies: set[Dependency] = set()

    @override
    def detect(self) -> bool:
        cwd = self.spec.config.cwd
        if cwd is None:
            return False
        self._dependencies = set()
        found = False
        for path in iter_files(cwd, "packages.config"):
            found = True
            root = read_xml(path)
            if root is None:
                continue
            self._dependencies.update(_packages(root))
        return found

    @override
    def extract_dependencies(self) -> set[Dependency] | None:
        if not self._dependencies:
            return None
        return set(self._dependencies)

    @override
    def get_supported_language_versions(self) -> set[str] | AccraError:
        return unconstrained_channels()


def _packages(root: ElementTree.Element) -> set[Dependency]:
    dependencies: set[Dependency] = set()
    for element in root.iter():
        if local_tag(element.tag) != "package":
            continue
        name = element.attrib.get("id")
        if not name:
            continue
        dependencies.add(
            Dependency(name=name, version=element.attrib.get("version", "").strip())
        )
    return dependencies
