from .csproj import Csproj
from .global_json import Global_json
from .language import CSharp
from .nuget import NuGet
from .packages_config import Packages_config
from .packages_props import Packages_props
from .solution import Solution

__all__ = [
    "CSharp",
    "Csproj",
    "Global_json",
    "NuGet",
    "Packages_config",
    "Packages_props",
    "Solution",
]


def main() -> None:
    print("csharp")
