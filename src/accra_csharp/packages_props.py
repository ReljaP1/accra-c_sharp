from typing import override

from accra_language import AccraError, Config, Dependency, Manifest, ManifestSpec

from .csproj import central_versions
from .utils import unconstrained_channels


class Packages_props(Manifest):
    def __init__(self, config: Config):
        spec = ManifestSpec(name="Directory.Packages.props", version="", config=config)
        super().__init__(spec)
        self._dependencies: set[Dependency] = set()

    @override
    def detect(self) -> bool:
        cwd = self.spec.config.cwd
        if cwd is None:
            return False
        versions = central_versions(cwd)
        self._dependencies = {
            Dependency(name=name, version=version) for name, version in versions.items()
        }
        return bool(versions)

    @override
    def extract_dependencies(self) -> set[Dependency] | None:
        if not self._dependencies:
            return None
        return set(self._dependencies)

    @override
    def get_supported_language_versions(self) -> set[str] | AccraError:
        return unconstrained_channels()
