from accra_language import (
    Config,
    EnvironmentManager,
    Language,
    LanguageSpec,
    Toolchain,
)

from .constants import SDK_PACKAGES
from .nuget import NuGet

# What the env manager runs on the host: bash and curl for Microsoft's
# dotnet-install script (it installs each project's SDK into the project), and
# the libraries the SDK loads.
_TOOLCHAIN = Toolchain(
    executables=("bash", "curl"),
    packages=SDK_PACKAGES,
    notes="the .NET SDK is installed per project by https://dot.net/v1/dotnet-install.sh",
)


class CSharp(Language):
    def __init__(self, config: Config, env_manager: EnvironmentManager | None = None):
        spec = LanguageSpec(
            name="csharp",
            version="",
            config=config,
            supported_env_managers={NuGet(config)},
            toolchain=_TOOLCHAIN,
        )
        super().__init__(spec, env_manager=env_manager)
