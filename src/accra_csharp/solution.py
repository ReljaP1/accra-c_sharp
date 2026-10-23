from pathlib import Path
from typing import override

from accra_language import AccraError, Config, Dependency, Manifest, ManifestSpec

from .utils import iter_files, unconstrained_channels


class Solution(Manifest):
    def __init__(self, config: Config):
        spec = ManifestSpec(name="sln", version="", config=config)
        super().__init__(spec)
        self.solutions: list[Path] = []

    @override
    def detect(self) -> bool:
        cwd = self.spec.config.cwd
        if cwd is None:
            return False
        self.solutions = iter_files(cwd, "*.sln")
        return bool(self.solutions)

    @override
    def extract_dependencies(self) -> set[Dependency] | None:
        return None

    @override
    def get_supported_language_versions(self) -> set[str] | AccraError:
        return unconstrained_channels()
