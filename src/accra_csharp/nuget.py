import os
import shlex
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import override
from urllib.error import URLError

from accra_language import (
    AccraBuildError,
    AccraError,
    AccraInstallError,
    AccraResult,
    Config,
    Dependency,
    Dockerfile,
    DockerfileInstruction,
    EnvironmentManager,
    EnvironmentManagerSpec,
)

from .constants import (
    DOTNET_DIR,
    DOTNET_INSTALL_URL,
    INVARIANT_GLOBALIZATION_CHANNELS,
    MONO_IMAGE,
    MONO_IOMAP,
    MONO_VERSION,
    MSBUILD_PROPERTIES,
    SDK_IMAGE,
    SDK_IMAGE_ROOT,
    TFM_CHANNELS,
)
from .csproj import Csproj
from .global_json import Global_json
from .packages_config import Packages_config
from .packages_props import Packages_props
from .solution import Solution
from .utils import (
    DOCKER_CREATE_USER,
    DOCKER_SWITCH_USER,
    buildable_frameworks,
    channel_key,
    channel_of,
    docker_setup_workdir,
    dockerfile_run,
    highest_channel,
    portable_frameworks,
    read_xml,
    unconstrained_channels,
)


class NuGet(EnvironmentManager):
    def __init__(self, config: Config):
        spec = EnvironmentManagerSpec(
            name="nuget",
            version="",
            supported_manifests={
                Csproj(config),
                Packages_props(config),
                Packages_config(config),
                Global_json(config),
                Solution(config),
            },
            config=config,
        )
        super().__init__(spec)
        self._using_docker = False
        self._mono_docker = False
        self._dotnet = "dotnet"
        self._dotnet_root: Path | None = None

    def _project_dir(self) -> Path | None:
        cwd = self.spec.config.cwd
        if cwd is None:
            return None
        return Path(cwd).resolve()

    def _command_env(self) -> dict[str, str]:
        config_env = self.spec.config.env
        base = dict(os.environ if config_env is None else config_env)
        base["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
        base["MONO_IOMAP"] = MONO_IOMAP
        base["DOTNET_NOLOGO"] = "1"
        base["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1"
        if self.selected_language_version in INVARIANT_GLOBALIZATION_CHANNELS:
            base["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] = "1"
        if self._dotnet_root is not None:
            root = str(self._dotnet_root)
            base["DOTNET_ROOT"] = root
            base["DOTNET_MULTILEVEL_LOOKUP"] = "0"
            base["PATH"] = root + os.pathsep + base.get("PATH", "")
        return base

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        config = self.spec.config
        try:
            return subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                cwd=config.cwd,
                env=self._command_env(),
                shell=config.shell,
                timeout=config.timeout,
            )
        except FileNotFoundError:
            return subprocess.CompletedProcess(
                args,
                127,
                "",
                f"{args[0]}: command not found",
            )

    def _fail(
        self,
        message: str,
        result: subprocess.CompletedProcess[str] | None = None,
        *,
        build: bool = False,
    ) -> AccraResult:
        if result is not None:
            detail = f"{result.stdout}\n{result.stderr}".strip()
            lines = [line.strip() for line in detail.splitlines() if line.strip()]
            diagnostics = [
                line
                for line in lines
                if (": error " in line.lower() or line.lower().startswith("error "))
                and "error(s)" not in line.lower()
            ]
            fatal = [
                line
                for line in lines
                if line.lower().startswith(
                    ("process terminated", "unhandled exception")
                )
            ]
            chosen = (
                fatal[0]
                if fatal
                else diagnostics[-1]
                if diagnostics
                else (lines[-1] if lines else "")
            )
            if chosen:
                message = f"{message}: {chosen}"
        error: AccraError = (
            AccraBuildError(message=message)
            if build
            else AccraInstallError(message=message)
        )
        return AccraResult(errors=[error], success=False)

    def _manifest(self, kind: type) -> EnvironmentManager | None:
        for manifest in self.present_manifests:
            if isinstance(manifest, kind):
                return manifest
        return None

    def _pinned_sdk_version(self) -> str | None:
        manifest = self._manifest(Global_json)
        if isinstance(manifest, Global_json):
            return manifest.sdk_version
        return None

    def _dotnet_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        found = shutil.which("dotnet")
        if found:
            candidates.append(Path(found).resolve())
        project = self._project_dir()
        if project is not None:
            candidates.append(project / DOTNET_DIR / "dotnet")
        candidates.append(Path.home() / ".dotnet" / "dotnet")
        unique: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen or not candidate.is_file():
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    def _sdk_versions(self, dotnet: Path) -> list[str]:
        previous = self._dotnet_root
        self._dotnet_root = dotnet.parent
        try:
            completed = self._run([str(dotnet), "--list-sdks"])
        finally:
            self._dotnet_root = previous
        if completed.returncode != 0:
            return []
        versions: list[str] = []
        for line in completed.stdout.splitlines():
            token = line.split(" ", 1)[0].strip()
            if token:
                versions.append(token)
        return versions

    def _matching_dotnet(self, channel: str, version: str | None) -> Path | None:
        for candidate in self._dotnet_candidates():
            installed = self._sdk_versions(candidate)
            if version is not None and version in installed:
                return candidate
            if version is None and any(
                channel_of(item) == channel for item in installed
            ):
                return candidate
        return None

    def _download_install_script(self, destination: Path) -> bool:
        try:
            urllib.request.urlretrieve(DOTNET_INSTALL_URL, destination)
        except (OSError, URLError):
            return False
        return destination.is_file()

    def _install_sdk(self, channel: str, version: str | None) -> bool:
        project = self._project_dir()
        if project is None:
            return False
        install_dir = project / DOTNET_DIR
        install_dir.mkdir(parents=True, exist_ok=True)
        script = install_dir / "dotnet-install.sh"
        if not self._download_install_script(script):
            return False
        command = ["bash", str(script), "--install-dir", str(install_dir)]
        if version:
            command.extend(["--version", version])
        else:
            command.extend(["--channel", channel])
        completed = self._run(command)
        binary = install_dir / "dotnet"
        if completed.returncode != 0 or not binary.is_file():
            return False
        self._dotnet = str(binary)
        self._dotnet_root = install_dir
        self._using_docker = False
        return True

    def _use_dotnet(self, binary: Path) -> None:
        self._dotnet = str(binary)
        self._dotnet_root = binary.parent
        self._using_docker = False

    def _docker_available(self) -> bool:
        return self._run(["docker", "info"]).returncode == 0

    def _ensure_sdk(self, channel: str) -> AccraResult:
        pin = self._pinned_sdk_version()
        if pin is not None and channel_of(pin) != channel:
            pin = None
        existing = self._matching_dotnet(channel, pin)
        if existing is not None:
            self._use_dotnet(existing)
            return AccraResult()
        if self._install_sdk(channel, pin):
            return AccraResult()
        if not self._docker_available():
            return self._fail(f"could not install the .NET SDK {channel}")
        self._using_docker = True
        self._dotnet = "dotnet"
        self._dotnet_root = None
        return AccraResult()

    def _dotnet_with_channels(self, channels: list[str]) -> Path | None:
        pin = self._pinned_sdk_version()
        pin_channel = channel_of(pin) if pin else None
        for candidate in self._dotnet_candidates():
            installed = self._sdk_versions(candidate)
            present = {channel_of(item) for item in installed if channel_of(item)}
            if not set(channels) <= present:
                continue
            if pin and pin_channel in channels and pin not in installed:
                continue
            return candidate
        return None

    def _ensure_sdks(self, channels: list[str]) -> AccraResult:
        if len(channels) <= 1:
            if not channels:
                return self._fail("could not install the .NET SDK")
            return self._ensure_sdk(channels[0])
        complete = self._dotnet_with_channels(channels)
        if complete is not None:
            self._use_dotnet(complete)
            return AccraResult()
        pin = self._pinned_sdk_version()
        for channel in channels:
            version = pin if pin and channel_of(pin) == channel else None
            if self._install_sdk(channel, version):
                continue
            if not self._docker_available():
                return self._fail(f"could not install the .NET SDK {channel}")
            self._using_docker = True
            self._dotnet = "dotnet"
            self._dotnet_root = None
            return AccraResult()
        return AccraResult()

    def _ensure_mono(self) -> AccraResult:
        if shutil.which("msbuild"):
            self._mono_docker = False
            return AccraResult()
        if self._docker_available():
            self._mono_docker = True
            return AccraResult()
        return self._fail("could not find Mono. Install msbuild or Docker.")

    def _workdir(self) -> list[DockerfileInstruction]:
        repo = self.spec.config.repo
        if repo:
            return list(docker_setup_workdir(repo))
        return [DockerfileInstruction("WORKDIR /project")]

    def _image_pre(
        self, channel: str, extra_channels: list[str]
    ) -> list[DockerfileInstruction]:
        instructions = [DockerfileInstruction(f"FROM {SDK_IMAGE}:{channel}")]
        instructions.extend(self._workdir())
        for extra in extra_channels:
            instructions.append(
                DockerfileInstruction(
                    "RUN curl -fsSL "
                    f"{DOTNET_INSTALL_URL} -o /tmp/dotnet-install.sh"
                    " && bash /tmp/dotnet-install.sh"
                    f" --channel {extra} --install-dir {SDK_IMAGE_ROOT}"
                )
            )
        instructions.extend(DOCKER_CREATE_USER)
        return instructions

    def _mono_image_pre(self) -> list[DockerfileInstruction]:
        instructions = [
            DockerfileInstruction(f"FROM {MONO_IMAGE}"),
            DockerfileInstruction(f"ENV MONO_IOMAP={MONO_IOMAP}"),
        ]
        instructions.extend(self._workdir())
        instructions.extend(DOCKER_CREATE_USER)
        return instructions

    def _projects(self) -> list:
        projects = self._manifest(Csproj)
        if not isinstance(projects, Csproj):
            return []
        return list(projects.projects)

    def _portable_projects(self) -> list:
        return [
            project
            for project in self._projects()
            if portable_frameworks(project.frameworks)
        ]

    def _framework_projects(self) -> list:
        return [
            project
            for project in self._projects()
            if project.frameworks
            and not project.sdk_style
            and not portable_frameworks(project.frameworks)
        ]

    def _required_channels(self) -> list[str]:
        pin = self._pinned_sdk_version()
        pin_channel = channel_of(pin) if pin else None
        concrete: set[str] = set()
        uses_standard = False
        for project in self._portable_projects():
            for framework in portable_frameworks(project.frameworks):
                channels = TFM_CHANNELS[framework]
                if pin_channel is not None:
                    if pin_channel in channels:
                        concrete.add(pin_channel)
                    continue
                if len(channels) == 1:
                    concrete.update(channels)
                else:
                    uses_standard = True
        if concrete:
            return sorted(concrete, key=channel_key)
        if uses_standard and self.selected_language_version:
            return [self.selected_language_version]
        if pin_channel is not None:
            return [pin_channel]
        return []

    def _relative(self, path: Path) -> str:
        project = self._project_dir()
        if project is None:
            return path.as_posix()
        try:
            return path.resolve().relative_to(project).as_posix()
        except ValueError:
            return path.as_posix()

    def _frameworks_for(self, project) -> list[str]:
        return buildable_frameworks(project.frameworks, set(self._required_channels()))

    def _has_packages_config(self, project_dir: Path) -> bool:
        return (project_dir / "packages.config").is_file()

    def _link_included_files(self, project_path: Path) -> None:
        document = read_xml(project_path)
        if document is None:
            return
        for element in document.iter():
            include = element.attrib.get("Include", "")
            if not include or "$" in include or "*" in include:
                continue
            self._link_case(project_path.parent, include.replace("\\", "/"))

    def _link_case(self, root: Path, relative: str) -> None:
        current = root
        for part in relative.split("/"):
            if not part or part == ".":
                continue
            exact = current / part
            if exact.exists():
                current = exact
                continue
            if not current.is_dir():
                return
            match = next(
                (
                    child
                    for child in current.iterdir()
                    if child.name.lower() == part.lower()
                ),
                None,
            )
            if match is None:
                return
            exact.symlink_to(match.name)
            current = exact

    def _prepare_framework_projects(self) -> None:
        for project in self._framework_projects():
            self._link_included_files(project.path)

    def _docker(
        self, commands: list[list[str]], image: str
    ) -> subprocess.CompletedProcess[str]:
        project = self._project_dir()
        if project is None:
            return subprocess.CompletedProcess(
                commands, 1, "", "the project directory is not set"
            )
        script = " && ".join(shlex.join(command) for command in commands)
        return self._run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-e",
                "HOME=/tmp",
                "-e",
                "DOTNET_CLI_HOME=/tmp",
                "-e",
                "NUGET_PACKAGES=/project/.nuget",
                "-e",
                f"MONO_IOMAP={MONO_IOMAP}",
                "-v",
                f"{project}:/project",
                "-w",
                "/project",
                image,
                "bash",
                "-c",
                script,
            ]
        )

    def _invoke(
        self, command: list[str], message: str, *, build: bool = False
    ) -> AccraResult | None:
        if self._using_docker:
            completed = self._docker(
                [command], f"{SDK_IMAGE}:{self.selected_language_version}"
            )
        else:
            host = list(command)
            if host and host[0] == "dotnet":
                host[0] = self._dotnet
            completed = self._run(host)
        if completed.returncode != 0:
            return self._fail(message, completed, build=build)
        return None

    @override
    def select_language_version(self) -> str | AccraError:
        if self.selected_language_version:
            return self.selected_language_version

        collected: list[set[str]] = []
        for manifest in self.present_manifests:
            result = manifest.get_supported_language_versions()
            if isinstance(result, AccraError):
                return result
            collected.append(result)

        if not collected:
            return AccraInstallError(message="could not decide on a language version")

        constrained = [
            versions for versions in collected if versions != unconstrained_channels()
        ]
        common = set.intersection(*(constrained or collected))
        if not common:
            return AccraInstallError(message="could not decide on a language version")

        numeric = {version for version in common if version != MONO_VERSION}
        if not numeric:
            self.selected_language_version = MONO_VERSION
        else:
            self.selected_language_version = highest_channel(numeric)
        return self.selected_language_version

    @override
    def pre_dependencies_installation(self) -> AccraResult:
        result = AccraResult()
        language_version = self.select_language_version()
        if isinstance(language_version, AccraError):
            return AccraResult(errors=[language_version], success=False)

        if language_version == MONO_VERSION:
            ensured = self._ensure_mono()
            if not ensured.success:
                return ensured
            self._prepare_framework_projects()
            result.dockerfile.pre_dependencies_installation.extend(
                self._mono_image_pre()
            )
            return result

        channels = self._required_channels()
        ensured = self._ensure_sdks(channels)
        if not ensured.success:
            return ensured
        if self._framework_projects():
            mono = self._ensure_mono()
            if not mono.success:
                return mono
            self._prepare_framework_projects()

        result.dockerfile.pre_dependencies_installation.extend(
            self._image_pre(
                language_version,
                [channel for channel in channels if channel != language_version],
            )
        )
        return result

    @override
    def _install_dependency(self, dependency: Dependency) -> AccraResult:
        return AccraResult()

    def _invoke_mono(
        self, command: list[str], message: str, *, build: bool = False
    ) -> AccraResult | None:
        if self._mono_docker:
            completed = self._docker([command], MONO_IMAGE)
        else:
            completed = self._run(command)
        if completed.returncode != 0:
            return self._fail(message, completed, build=build)
        return None

    def _restore_framework_project(self, project) -> AccraResult | None:
        if not self._has_packages_config(project.path.parent):
            return None
        relative = self._relative(project.path)
        command = ["nuget", "restore", relative]
        failed = self._invoke_mono(command, f"could not restore {relative}")
        if failed is not None:
            return failed
        if self.selected_language_version != MONO_VERSION:
            return AccraResult()
        return AccraResult(
            dockerfile=Dockerfile(dependencies_installation=[dockerfile_run(command)]),
        )

    def _build_framework_project(self, project) -> AccraResult | None:
        relative = self._relative(project.path)
        command = ["msbuild", relative, *MSBUILD_PROPERTIES]
        failed = self._invoke_mono(command, f"could not build {relative}", build=True)
        if failed is not None:
            return failed
        if self.selected_language_version != MONO_VERSION:
            return AccraResult()
        return AccraResult(
            dockerfile=Dockerfile(
                post_dependencies_installation=[dockerfile_run(command)]
            ),
        )

    @override
    def dependencies_installation(self) -> AccraResult:
        result = AccraResult()
        if self.selected_language_version != MONO_VERSION:
            for project in self._portable_projects():
                relative = self._relative(project.path)
                command = ["dotnet", "restore", relative]
                failed = self._invoke(command, f"could not restore {relative}")
                if failed is not None:
                    return failed
                result.dockerfile.dependencies_installation.append(
                    dockerfile_run(command)
                )
        for project in self._framework_projects():
            restored = self._restore_framework_project(project)
            if restored is None:
                continue
            if not restored.success:
                return restored
            result.extend(restored)
        return result

    @override
    def post_dependencies_installation(self) -> AccraResult:
        result = AccraResult()
        if self.selected_language_version != MONO_VERSION:
            for project in self._portable_projects():
                relative = self._relative(project.path)
                for framework in self._frameworks_for(project):
                    command = [
                        "dotnet",
                        "build",
                        relative,
                        "-c",
                        "Release",
                        "--no-restore",
                        "--framework",
                        framework,
                    ]
                    failed = self._invoke(
                        command, f"could not build {relative}", build=True
                    )
                    if failed is not None:
                        return failed
                    result.dockerfile.post_dependencies_installation.append(
                        dockerfile_run(command)
                    )
        for project in self._framework_projects():
            built = self._build_framework_project(project)
            if built is None:
                continue
            if not built.success:
                return built
            result.extend(built)
        if (
            result.dockerfile.dependencies_installation
            or result.dockerfile.post_dependencies_installation
            or result.dockerfile.pre_dependencies_installation
        ):
            result.dockerfile.post_dependencies_installation.extend(DOCKER_SWITCH_USER)
        return result
