"""Canonical csopencvcpu configuration.

This file is shipped inside the csopencvcpu release bundle (it is listed in
`additional_files_list`) and imported by consuming projects as
`<dependencies_folder>.csopencvcpu_config`.

IMPORTANT: this file is intentionally SELF-CONTAINED: it may only import
csorchestrator modules and the Python standard library, never project-local
modules such as `utils.*`. The release bundle preserves relative paths, but the
consumer imports this module from its own `dependencies/` folder, so any
project-local import would not resolve there (see csqt6_config.py /
third_party_base_libs_config.py for the same pattern).

Contents:
- `install_csopencvcpu_build_dependencies()`: adds the pipeline steps that
replicate the csopencvcpu build environment (apt packages,
numpy) and downloads the precompiled build dependencies (eigen3) via the
standard provider mechanism. It is called by `csopencvcpu_project.py`
(producer) and by `auto_install_csorchestrator_managed_libraries()`
(consumers pulling the precompiled OpenCV archives);
"""

from copy import deepcopy
from pathlib import Path

from csorchestrator.application.recipes.manifest_github import (
    ManifestGithub,
    create_steps_to_get_libs_from_manifest,
    resolve_libs_deps_and_install_dependencies,
)
from csorchestrator.domain.context.context_compiler_generator import (
    Compiler,
    ContextCompilerGenerator,
    GeneratorWithType,
)
from csorchestrator.domain.context.context_os_architecture import (
    OS,
    UBUNTU_STRING_PREFIX,
    UbuntuVersions,
)
from csorchestrator.domain.context.context_os_architecture_compiler_generator import (
    ContextOsArchitectureCompilerGenerator,
)
from csorchestrator.domain.orchestrator.orchestrator import Orchestrator
from csorchestrator.foundation.core.report import Report
from csorchestrator.frontend.local_execution.step_utils import (
    StepExecuteOnlyOn,
    StepExecuteOnlyOncePerMatrix,
    StepSkipExecutionOnLocal,
)
from csorchestrator.frontend.step.step_custom_command import (
    StepBashScriptCommand,
    StepInstallAptPackages,
    StepWinPSCommand,
)
from csorchestrator.frontend.step.step_get_precompiled_lib_github import (
    MappingFunction,
    StepGetPrecompiledLibGithub,
)
from csorchestrator.portable.release_manifest import ReleaseManifest

# ============================================================================
# External provider of precompiled build dependencies.
#
# eigen3 is a build dependency of the OpenCV configuration (and of consumers
# replicating the build environment): it is downloaded precompiled from the
# third_party_base_libs GitHub releases, through the standard provider
# mechanism (ManifestGithub description + resolve_libs_deps_and_install_dependencies).
# ============================================================================

THIRD_PARTY_BASE_LIBS_PROVIDER = ManifestGithub(
    base_url=StepGetPrecompiledLibGithub.GITHUB_BASE_URL_HTTPS,
    org="cscosine",
    git_repo="third_party_base_libs",
    project_name="third_party_base_libs",
    project_version="0.1.0",
    release_tag="v0.1.0-rc3",
)


# First-party library list (mirrors csfoundation_config.py pattern).
# csopencvcpu builds OpenCV; eigen3 is a precompiled build dependency of
# OpenCV and is downloaded via the standard provider mechanism.
LIBRARY_LIST = ["opencv"]

# project internal dependencies
LIBRARY_DEPENDENCIES: dict[str, list[str]] = {
    "opencv": [],
}

# project additional dependencies for `dev`
LIBRARY_DEPENDENCIES_DEV: dict[str, list[str]] = {}


def third_party_base_libs_mapping(
    context: ContextOsArchitectureCompilerGenerator,
) -> ContextOsArchitectureCompilerGenerator | None:
    """Remap the context when downloading precompiled third-party base libs.

    OpenCV is built with the Ninja single-config generator, while the
    precompiled eigen archives published by third_party_base_libs are built
    with the ninja-multiconfig Linux x64 context: remap on Linux so that the
    published archive is found. Windows contexts are already the published
    (MSVC multi-config) ones and are left unchanged.
    """
    if context.context_os_architecture.os == OS.LINUX:
        new_context = deepcopy(context)
        new_context.context_compiler_generator = ContextCompilerGenerator(
            compiler_family=Compiler.GCC,
            compiler_version=ContextCompilerGenerator.COMPILER_VERSION_DEFAULT,
            build_generator=GeneratorWithType.NINJA_MULTI,
        )
        return new_context
    return deepcopy(context)


# ============================================================================
# Ubuntu apt packages required to build OpenCV.
#
# NOTE: entries must be EXPLICIT package names (no shell wildcards): the
# install step (StepInstallAptPackages) checks presence with `dpkg -s` and a
# wildcard would be always reported as missing, forcing an apt install (and an
# `apt update`) at every run.
# ============================================================================

APT_PACKAGES = """
libavcodec-dev
libavformat-dev
libdc1394-dev
libgstreamer-plugins-base1.0-dev
libgstreamer1.0-dev
libgtk-3-dev
libjpeg-dev
libopenexr-dev
libpng-dev
libswscale-dev
libtbb-dev
libtbb12
libtiff-dev
libwebp-dev
pkg-config
python3-dev
python3-numpy
python3-pip
"""


def get_apt_packages_list() -> list[str]:
    return APT_PACKAGES.split()


# ============================================================================
# Linux install scripts (bash).
#
# Every script is IDEMPOTENT: it checks whether the component is already
# installed and skips the install when present.
# ============================================================================

_PREACCEPT_MS_FONTS_SCRIPT_LINUX = r"""
set -euo pipefail

# Pre-accept the Microsoft Core Fonts EULA so installation can run
# non-interactively. No-op when the package is already installed.
if dpkg -s ttf-mscorefonts-installer >/dev/null 2>&1; then
  echo "ttf-mscorefonts-installer already installed, skipping."
  exit 0
fi

sudo apt-get update
echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | sudo debconf-set-selections
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ttf-mscorefonts-installer
"""

_REMOVE_LIBUNWIND_SCRIPT_LINUX = r"""
set -euo pipefail

# Remove libunwind causing errors on ubuntu 22.04. No-op when not installed.
packages=$(dpkg -l 'libunwind*' 2>/dev/null | awk '$1 == "ii" {print $2}' || true)
if [ -z "${packages}" ]; then
  echo "libunwind not installed, nothing to remove."
  exit 0
fi

echo "Removing: ${packages}"
# shellcheck disable=SC2086
sudo apt-get remove -y ${packages}
"""

# ============================================================================
# Windows install scripts (PowerShell).
#
# Same idempotency policy as the Linux scripts: check for presence first and
# skip the download/install when the component is already in place.
# ============================================================================

_INSTALL_NUMPY_SCRIPT_WINDOWS = r"""
$ErrorActionPreference = "Stop"

# Check whether numpy is importable.
$oldErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
python -c "import numpy" 2>$null
$numpyExitCode = $LASTEXITCODE
$ErrorActionPreference = $oldErrorActionPreference

if ($numpyExitCode -eq 0) {
    Write-Host "numpy already installed, skipping."
} else {
    python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip"
    }

    python -m pip install numpy
    if ($LASTEXITCODE -ne 0) {
    throw "Failed to install numpy"
    }
}
"""


def install_csopencvcpu_build_dependencies(
    orchestrator: Orchestrator,
    base_libs_dir: Path,
    dependencies_config_path: Path,
    dev: bool,
    download_dependencies_manifest_and_bundle: bool,
    mapping_function: MappingFunction,
    phase_name_suffix: str,
    required_libs: list[str] | None = None,
) -> Report:
    """Add the steps that replicate the csopencvcpu build environment.

    Called by:
    - `csopencvcpu_project.py` when building OpenCV (producer);
    - `auto_install_csorchestrator_managed_libraries()` when the precompiled
      OpenCV archives are consumed and the environment must be replicated.

    Includes the download of precompiled build dependencies (eigen3 from the
    third_party_base_libs provider) via the standard provider mechanism, which
    downloads the manifest and bundle into ``dependencies_config_path``.

    All steps are idempotent: already-installed components are detected and
    skipped.
    """
    report = Report()

    p = orchestrator.create_phase("Install Build Dependencies (csopencvcpu)")

    # ------------------------------ LINUX ------------------------------
    p.add_step(
        StepBashScriptCommand(
            name="Pre-accept MS fonts EULA (Linux)",
            description="pre-accept the Microsoft Core Fonts EULA for non-interactive installs",
            cmd=_PREACCEPT_MS_FONTS_SCRIPT_LINUX.strip().splitlines(),
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.LINUX, version_starts_with=UBUNTU_STRING_PREFIX))
    )

    p.add_step(
        StepBashScriptCommand(
            name="Remove libunwind (Ubuntu 22.04)",
            description="remove libunwind -dev packages causing errors on ubuntu 22.04 GitHub runners",
            cmd=_REMOVE_LIBUNWIND_SCRIPT_LINUX.strip().splitlines(),
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(
            StepExecuteOnlyOn(
                os=OS.LINUX,
                version_starts_with=UbuntuVersions.UBUNTU_22_04.value,
            )
        )
        # GitHub-runners-only: NEVER run on a dev machine. Removing
        # packages with apt on a persistent host can cascade into removing
        # ubuntu-desktop/xserver/NVIDIA drivers.
        .add_extra(StepSkipExecutionOnLocal())
    )

    p.add_step(
        StepInstallAptPackages(
            name="Install apt packages (Linux)",
            description="install apt packages if not already installed in the system",
            packages=get_apt_packages_list(),
            dry_run=False,
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.LINUX, version_starts_with=UBUNTU_STRING_PREFIX))
    )

    # ------------------------------ WINDOWS -----------------------------
    p.add_step(
        StepWinPSCommand(
            name="Install numpy (Windows)",
            description="install numpy if not already installed",
            cmd=_INSTALL_NUMPY_SCRIPT_WINDOWS.strip().splitlines(),
            dry_run=False,
        )
        .add_extra(StepExecuteOnlyOncePerMatrix())
        .add_extra(StepExecuteOnlyOn(os=OS.WINDOWS))
    )

    # ------------------- PRECOMPILED THIRD-PARTY BASE LIBS -------------------
    # eigen3: precompiled build dependency, downloaded via the standard
    # provider mechanism (resolve_libs_deps_and_install_dependencies) which
    # downloads the manifest+bundle into dependencies_config_path and triggers
    # the provider's auto_install step.
    report.append_report(
        resolve_libs_deps_and_install_dependencies(
            orchestrator=orchestrator,
            base_libs_dir=base_libs_dir,
            dependencies_config_path=dependencies_config_path,
            dev=dev,
            download_dependencies_manifest_and_bundle=download_dependencies_manifest_and_bundle,
            mapping_function=mapping_function,
            required_libs=required_libs,
            full_library_list=LIBRARY_LIST,
            library_dependencies=LIBRARY_DEPENDENCIES,
            library_dependencies_dev=LIBRARY_DEPENDENCIES_DEV,
            external_library_dependencies={
                THIRD_PARTY_BASE_LIBS_PROVIDER.project_name: {
                    "opencv": ["eigen3"],
                },
            },
            external_library_dependencies_dev={
                THIRD_PARTY_BASE_LIBS_PROVIDER.project_name: {},
            },
            external_provides_description=[THIRD_PARTY_BASE_LIBS_PROVIDER],
            provider_mapping_function={},
            phase_name_suffix=phase_name_suffix,
        )
    )

    return report


def auto_install_csorchestrator_managed_libraries(
    orchestrator: Orchestrator,
    base_libs_dir: Path,
    manifest_description: ManifestGithub,
    manifest_loaded: ReleaseManifest,
    dependencies_config_path: Path,
    mapping_function: MappingFunction,
    download_dependencies_manifest_and_bundle: bool,
    phase_name_suffix: str,
    required_libs: list[str] | None = None,
) -> Report:
    report = Report()

    # replicate the csopencvcpu build environment (apt packages)
    # and precompiled build dependencies (eigen3) in the consumer pipeline:
    # customers need the same toolchain to use the precompiled OpenCV archives
    report.append_report(
        install_csopencvcpu_build_dependencies(
            orchestrator=orchestrator,
            base_libs_dir=base_libs_dir,
            dependencies_config_path=dependencies_config_path,
            dev=False,
            download_dependencies_manifest_and_bundle=download_dependencies_manifest_and_bundle,
            mapping_function=mapping_function,
            phase_name_suffix=phase_name_suffix,
            required_libs=required_libs,
        )
    )

    report.append_report(
        create_steps_to_get_libs_from_manifest(
            orchestrator=orchestrator,
            manifest_description=manifest_description,
            manifest_loaded=manifest_loaded,
            base_libs_dir=base_libs_dir,
            lib_name_list=required_libs,
            mapping_function=mapping_function,
            phase_name=phase_name_suffix,
            dev=False,
        )
    )

    return report
