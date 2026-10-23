from typing import override

from accra_language import AccraError, Config, Dependency, Manifest, ManifestSpec

from .utils import (
    channel_of,
    find_named,
    read_json,
    sdk_version_from_global_json,
    unconstrained_channels,
)


class Global_json(Manifest):
    def __init__(self, config: Config):
        spec = ManifestSpec(name="global.json", version="", config=config)
        super().__init__(spec)
        self.sdk_version: str | None = None
        self._valid = False

    @override
    def detect(self) -> bool:
        cwd = self.spec.config.cwd
        if cwd is None:
            return False
        self.sdk_version = None
        self._valid = False
        paths = find_named(cwd, "global.json")
        if not paths:
            return False
        document = read_json(paths[0])
        if document is None:
            return True
        self._valid = True
        self.sdk_version = sdk_version_from_global_json(document)
        return True

    @override
    def extract_dependencies(self) -> set[Dependency] | None:
        return None

    @override
    def get_supported_language_versions(self) -> set[str] | AccraError:
        if not self._valid:
            return set()
        if self.sdk_version is None:
            return unconstrained_channels()
        channel = channel_of(self.sdk_version)
        if channel is None:
            return set()
        return {channel}
