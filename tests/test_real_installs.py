import os
import shutil
import subprocess
from pathlib import Path

from accra_language import Config

from accra_csharp import CSharp

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _project(name: str, destination: Path) -> None:
    shutil.copytree(FIXTURES / name, destination, dirs_exist_ok=True)


def _dotnet(project: Path) -> tuple[str, dict[str, str]]:
    local = project / ".dotnet" / "dotnet"
    binary = local if local.is_file() else Path(shutil.which("dotnet") or "")
    env = dict(os.environ)
    if binary.is_file():
        env["DOTNET_ROOT"] = str(binary.parent)
        env["DOTNET_MULTILEVEL_LOOKUP"] = "0"
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    env["DOTNET_NOLOGO"] = "1"
    return str(binary), env


def test_json_package_restores_and_runs(tmp_path: Path):
    _project("json-app", tmp_path)
    result = CSharp(Config(cwd=tmp_path)).build()
    assert result.success, [error.message for error in result.errors]
    dotnet, env = _dotnet(tmp_path)
    ran = subprocess.run(
        [dotnet, "run", "--project", "json-app.csproj", "-c", "Release", "--no-build"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
    )
    assert ran.returncode == 0, ran.stderr
    assert "ACCRa" in ran.stdout


def test_missing_package_stops_the_build(tmp_path: Path):
    _project("bad-package", tmp_path)
    result = CSharp(Config(cwd=tmp_path)).build()
    assert not result.success
    assert any("aaaa_missing_dist_zz" in error.message for error in result.errors)


def test_net48_build_does_not_start(tmp_path: Path):
    _project("net48-only", tmp_path)
    result = CSharp(Config(cwd=tmp_path)).build()
    assert not result.success
    assert result.errors[0].message == "could not decide on a language version"
    assert not (tmp_path / ".dotnet").exists()
    assert not (tmp_path / "bin").exists()
