# Channels this plugin can install, and the target frameworks each one can build
# without a Windows targeting pack. A concrete framework needs its own SDK.
# netstandard is buildable by every channel below.

SDK_IMAGE = "mcr.microsoft.com/dotnet/sdk"
SDK_IMAGE_ROOT = "/usr/share/dotnet"
DOTNET_INSTALL_URL = "https://dot.net/v1/dotnet-install.sh"
DOTNET_DIR = ".dotnet"
LTS_CHANNEL = "10.0"
MONO_VERSION = "mono"
MONO_IMAGE = "mono:6.12"
MONO_IOMAP = "all"
# Mono has no Client profile, so the profile from an old csproj is cleared.
MSBUILD_PROPERTIES = ("/p:Configuration=Release", "/p:TargetFrameworkProfile=")

INSTALLABLE_CHANNELS = ("3.1", "5.0", "6.0", "7.0", "8.0", "9.0", "10.0")

# These SDK channels need libicu versions that current Linux distributions no longer ship.
INVARIANT_GLOBALIZATION_CHANNELS = {"2.1", "2.2", "3.0", "3.1", "5.0"}

TFM_CHANNELS: dict[str, set[str]] = {
    "netcoreapp2.1": {"2.1"},
    "netcoreapp2.2": {"2.2"},
    "netcoreapp3.0": {"3.0"},
    "netcoreapp3.1": {"3.1"},
    "net5.0": {"5.0"},
    "net6.0": {"6.0"},
    "net7.0": {"7.0"},
    "net8.0": {"8.0"},
    "net9.0": {"9.0"},
    "net10.0": {"10.0"},
    "netstandard2.0": set(INSTALLABLE_CHANNELS),
    "netstandard2.1": set(INSTALLABLE_CHANNELS),
}
