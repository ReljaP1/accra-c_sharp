import shutil
import subprocess
from pathlib import Path

from accra_language import AccraResult, Config, Dependency

from accra_csharp import (
    CSharp,
    Csproj,
    Global_json,
    NuGet,
    Packages_config,
    Packages_props,
)


def _copy(name: str, destination: Path) -> None:
    source = Path(__file__).resolve().parent / "fixtures" / name
    shutil.copytree(source, destination, dirs_exist_ok=True)


def test_package_reference_attribute_and_element(tmp_path: Path):
    (tmp_path / "app.csproj").write_text(
        """
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup>
            <TargetFramework>net8.0</TargetFramework>
          </PropertyGroup>
          <ItemGroup>
            <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
            <PackageReference Include="Serilog">
              <Version>3.1.1</Version>
            </PackageReference>
          </ItemGroup>
        </Project>
        """,
        encoding="utf-8",
    )
    manifest = Csproj(Config(cwd=tmp_path))
    assert manifest.detect()
    assert manifest.extract_dependencies() == {
        Dependency(name="Newtonsoft.Json", version="13.0.3"),
        Dependency(name="Serilog", version="3.1.1"),
    }
    assert manifest.get_supported_language_versions() == {"8.0"}


def test_central_package_versions(tmp_path: Path):
    (tmp_path / "Directory.Packages.props").write_text(
        """
        <Project>
          <PropertyGroup>
            <ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>
          </PropertyGroup>
          <ItemGroup>
            <PackageVersion Include="Newtonsoft.Json" Version="13.0.3" />
          </ItemGroup>
        </Project>
        """,
        encoding="utf-8",
    )
    (tmp_path / "app.csproj").write_text(
        """
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup>
            <TargetFramework>net8.0</TargetFramework>
          </PropertyGroup>
          <ItemGroup>
            <PackageReference Include="Newtonsoft.Json" />
          </ItemGroup>
        </Project>
        """,
        encoding="utf-8",
    )
    props = Packages_props(Config(cwd=tmp_path))
    assert props.detect()
    project = Csproj(Config(cwd=tmp_path))
    assert project.detect()
    assert project.extract_dependencies() == {
        Dependency(name="Newtonsoft.Json", version="13.0.3")
    }


def test_packages_config(tmp_path: Path):
    (tmp_path / "packages.config").write_text(
        """
        <packages>
          <package id="Newtonsoft.Json" version="13.0.3" targetFramework="net48" />
        </packages>
        """,
        encoding="utf-8",
    )
    manifest = Packages_config(Config(cwd=tmp_path))
    assert manifest.detect()
    assert manifest.extract_dependencies() == {
        Dependency(name="Newtonsoft.Json", version="13.0.3")
    }


def test_global_json_pins_the_channel(tmp_path: Path):
    (tmp_path / "global.json").write_text(
        '{"sdk": {"version": "6.0.428", "rollForward": "latestFeature"}}',
        encoding="utf-8",
    )
    manifest = Global_json(Config(cwd=tmp_path))
    assert manifest.detect()
    assert manifest.sdk_version == "6.0.428"
    assert manifest.get_supported_language_versions() == {"6.0"}


def test_arcade_global_json_uses_tools_dotnet(tmp_path: Path):
    (tmp_path / "global.json").write_text(
        '{"tools": {"dotnet": "8.0.101"}}',
        encoding="utf-8",
    )
    manifest = Global_json(Config(cwd=tmp_path))
    assert manifest.detect()
    assert manifest.get_supported_language_versions() == {"8.0"}


def test_channel_conflict_stops_before_the_sdk_is_installed(tmp_path: Path):
    (tmp_path / "global.json").write_text(
        '{"sdk": {"version": "6.0.100"}}',
        encoding="utf-8",
    )
    (tmp_path / "app.csproj").write_text(
        """
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
        </Project>
        """,
        encoding="utf-8",
    )
    result = CSharp(Config(cwd=tmp_path)).build()
    assert not result.success
    assert result.errors[0].message == "could not decide on a language version"
    assert not (tmp_path / ".dotnet").exists()


def test_net48_is_not_a_linux_target(tmp_path: Path):
    _copy("net48-only", tmp_path)
    manifest = Csproj(Config(cwd=tmp_path))
    assert manifest.detect()
    assert manifest.get_supported_language_versions() == set()
    result = CSharp(Config(cwd=tmp_path)).build()
    assert not result.success
    assert result.errors[0].message == "could not decide on a language version"
    assert not (tmp_path / ".dotnet").exists()


def test_solution_does_not_replace_project_dependencies(tmp_path: Path):
    (tmp_path / "app.sln").write_text("", encoding="utf-8")
    (tmp_path / "app.csproj").write_text(
        """
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup><TargetFramework>net6.0</TargetFramework></PropertyGroup>
          <ItemGroup>
            <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
          </ItemGroup>
        </Project>
        """,
        encoding="utf-8",
    )
    nuget = NuGet(Config(cwd=tmp_path))
    assert nuget._get_dependencies() == {
        Dependency(name="Newtonsoft.Json", version="13.0.3")
    }
    assert nuget.select_language_version() == "6.0"


def test_multi_target_keeps_every_framework_the_sdk_can_build():
    from accra_csharp.utils import buildable_frameworks

    chosen = buildable_frameworks(
        {"net6.0", "net5.0", "net48", "netstandard2.0"},
        {"6.0"},
    )
    assert chosen == ["netstandard2.0", "net6.0"]


def test_dockerfile_records_restore_and_build(monkeypatch, tmp_path: Path):
    (tmp_path / "app.csproj").write_text(
        """
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
          <ItemGroup>
            <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
          </ItemGroup>
        </Project>
        """,
        encoding="utf-8",
    )

    def ensure(self, channel: str):
        self._dotnet = "dotnet"
        self._using_docker = False
        return AccraResult()

    def run(self, args: list[str]):
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(NuGet, "_ensure_sdk", ensure)
    monkeypatch.setattr(NuGet, "_run", run)
    result = CSharp(Config(cwd=tmp_path, repo="https://example.test/app.git")).build()
    assert result.success, [error.message for error in result.errors]
    assert (
        result.dockerfile.pre_dependencies_installation[0]
        == "FROM mcr.microsoft.com/dotnet/sdk:8.0"
    )
    assert (
        "RUN dotnet restore app.csproj" in result.dockerfile.dependencies_installation
    )
    assert (
        "RUN dotnet build app.csproj -c Release --no-restore --framework net8.0"
        in result.dockerfile.post_dependencies_installation
    )


def test_docker_is_used_when_the_sdk_script_is_unavailable(monkeypatch, tmp_path: Path):
    (tmp_path / "app.csproj").write_text(
        """
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
        </Project>
        """,
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def no_dotnet(self, channel: str, version: str | None):
        return None

    def no_script(self, destination: Path):
        return False

    def run(self, args: list[str]):
        calls.append(args)
        if args[:2] == ["docker", "info"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "", "dotnet: command not found")

    monkeypatch.setattr(NuGet, "_matching_dotnet", no_dotnet)
    monkeypatch.setattr(NuGet, "_download_install_script", no_script)
    monkeypatch.setattr(NuGet, "_run", run)
    result = CSharp(Config(cwd=tmp_path)).build()
    assert result.success, [error.message for error in result.errors]
    docker_runs = [call for call in calls if call[:2] == ["docker", "run"]]
    assert docker_runs
    assert "mcr.microsoft.com/dotnet/sdk:8.0" in docker_runs[0]
    joined = " ".join(" ".join(call) for call in docker_runs)
    assert "dotnet restore app.csproj" in joined
    assert (
        "dotnet build app.csproj -c Release --no-restore --framework net8.0" in joined
    )


def test_multi_target_build_uses_every_portable_framework(monkeypatch, tmp_path: Path):
    (tmp_path / "app.sln").write_text("", encoding="utf-8")
    (tmp_path / "app.csproj").write_text(
        """
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup>
            <TargetFrameworks>net6.0;net8.0</TargetFrameworks>
          </PropertyGroup>
        </Project>
        """,
        encoding="utf-8",
    )

    def ensure(self, channels: list[str]):
        self._dotnet = "dotnet"
        self._using_docker = False
        return AccraResult()

    monkeypatch.setattr(NuGet, "_ensure_sdks", ensure)
    monkeypatch.setattr(
        NuGet,
        "_run",
        lambda self, args: subprocess.CompletedProcess(args, 0, "", ""),
    )
    result = CSharp(Config(cwd=tmp_path)).build()
    assert result.success, [error.message for error in result.errors]
    text = str(result.dockerfile)
    assert "--framework net6.0" in text
    assert "--framework net8.0" in text
    assert "app.sln" not in text
    assert "FROM mcr.microsoft.com/dotnet/sdk:8.0" in text
    assert "--channel 6.0" in text


def test_old_framework_project_does_not_cancel_the_sdk_channel(tmp_path: Path):
    (tmp_path / "modern.csproj").write_text(
        """
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
        </Project>
        """,
        encoding="utf-8",
    )
    (tmp_path / "legacy.csproj").write_text(
        """
        <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
          <PropertyGroup>
            <TargetFrameworkVersion>v4.0</TargetFrameworkVersion>
          </PropertyGroup>
        </Project>
        """,
        encoding="utf-8",
    )
    nuget = NuGet(Config(cwd=tmp_path))
    assert nuget.select_language_version() == "8.0"


def test_old_framework_project_selects_mono(tmp_path: Path):
    (tmp_path / "legacy.csproj").write_text(
        """
        <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
          <PropertyGroup>
            <TargetFrameworkVersion>v4.0</TargetFrameworkVersion>
          </PropertyGroup>
        </Project>
        """,
        encoding="utf-8",
    )
    nuget = NuGet(Config(cwd=tmp_path))
    assert nuget.select_language_version() == "mono"
