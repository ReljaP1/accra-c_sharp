import json
from pathlib import Path

from accra_language import AccraError, Config, Dependency

from accra_csharp import NuGet

CSPROJ = """
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <AssemblyName>Acme.Core</AssemblyName>
    <RootNamespace>Acme</RootNamespace>
    <PackageId>Acme.Pkg</PackageId>
  </PropertyGroup>
</Project>
"""


def _project(tmp_path: Path, name: str = "app") -> Path:
    (tmp_path / name).mkdir(exist_ok=True)
    (tmp_path / name / f"{name}.csproj").write_text(CSPROJ, encoding="utf-8")
    return tmp_path / name


def _assets(project: Path, libraries: dict) -> None:
    (project / "obj").mkdir(exist_ok=True)
    (project / "obj" / "project.assets.json").write_text(
        json.dumps({"version": 3, "libraries": libraries}), encoding="utf-8"
    )


def _manager(tmp_path: Path) -> NuGet:
    return NuGet(Config(cwd=tmp_path))


def test_project_names(tmp_path: Path):
    _project(tmp_path)
    (tmp_path / "broken.csproj").write_text("<Project", encoding="utf-8")
    assert _manager(tmp_path).project_names() == {
        "app",
        "Acme.Core",
        "Acme",
        "Acme.Pkg",
    }


def test_installed_dependencies_lists_exact_packages(tmp_path: Path):
    project = _project(tmp_path)
    _assets(
        project,
        {
            "Newtonsoft.Json/13.0.3": {"type": "package"},
            "Serilog/3.1.1": {"type": "package"},
            "Other/1.0.0": {"type": "project"},
        },
    )
    assert _manager(tmp_path).installed_dependencies() == {
        Dependency(name="Newtonsoft.Json", version="=13.0.3"),
        Dependency(name="Serilog", version="=3.1.1"),
    }


def test_installed_dependencies_without_assets_file(tmp_path: Path):
    _project(tmp_path)
    assert isinstance(_manager(tmp_path).installed_dependencies(), AccraError)


def test_installed_dependencies_ignores_malformed_json(tmp_path: Path):
    project = _project(tmp_path)
    (project / "obj").mkdir()
    (project / "obj" / "project.assets.json").write_text("{nope", encoding="utf-8")
    assert _manager(tmp_path).installed_dependencies() == set()
    _assets(project, {"bad": {"type": "package"}, "x/1": "oops"})
    assert _manager(tmp_path).installed_dependencies() == set()


def test_installed_dependencies_keeps_the_highest_duplicate(tmp_path: Path):
    _assets(_project(tmp_path, "a"), {"Serilog/3.1.1": {"type": "package"}})
    _assets(
        _project(tmp_path, "b"),
        {"serilog/3.10.0": {"type": "package"}, "Dup/1.0.0-beta": {"type": "package"}},
    )
    _assets(_project(tmp_path, "c"), {"Dup/1.0.0": {"type": "package"}})
    nested = tmp_path / "node_modules" / "x"
    nested.mkdir(parents=True)
    _assets(nested, {"Ignored/9.9.9": {"type": "package"}})
    assert _manager(tmp_path).installed_dependencies() == {
        Dependency(name="serilog", version="=3.10.0"),
        Dependency(name="Dup", version="=1.0.0"),
    }
