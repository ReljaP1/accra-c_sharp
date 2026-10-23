from accra_language import Config, EnvironmentManager, Language, LanguageSpec

from .nuget import NuGet


class CSharp(Language):
    def __init__(self, config: Config, env_manager: EnvironmentManager | None = None):
        spec = LanguageSpec(
            name="csharp",
            version="",
            config=config,
            supported_env_managers={NuGet(config)},
        )
        super().__init__(spec, env_manager=env_manager)
