#!/usr/bin/env python3
import sys
from collections.abc import Sequence
from pathlib import Path

from csorchestrator.application.cli.cli import orchestrator_main_with_default_run
from csorchestrator.application.factory.factory import OptionalOrchestratorWithReport
from csorchestrator.application.recipes.checkout_build import checkout_repos, create_and_upload_artifacts
from csorchestrator.application.recipes.create_orchestrator import (
    create_default_orchestrator,
)
from csorchestrator.application.recipes.cscmake_release import create_cscmake_release_archive
from csorchestrator.domain.context.context_os_architecture import OS, UBUNTU_STRING_PREFIX
from csorchestrator.domain.orchestrator.workflow_config import Cron, DayOfWeek
from csorchestrator.foundation.core.report import Report
from csorchestrator.frontend.cscmake_presets.supported_variants import (
    BuildConfig,
    get_context_list_linux,
    get_context_list_macos,
)
from csorchestrator.frontend.local_execution.step_utils import StepExecuteOnlyOn
from csorchestrator.frontend.step.step_cmake_command import (
    StepCMakeWorkflow,
    StepCMakeWorkflowGithubExtraCommandsPrefix,
    StepCMakeWorkflowGithubPowershell,
)
from csorchestrator.frontend.step.step_get_precompiled_lib_github import identity_mapping_function
from csorchestrator.portable.package_version import PackageVersion

from csopencvcpu_config import install_csopencvcpu_build_dependencies

# version of the OpenCV being built (also used as the csopencvcpu project
# version: keep pyproject.toml in sync when bumping)
OPENCV_VERSION = "5.1.0"

# prefix commands (PowerShell) applied before the CMake workflow on Windows:
# remove MinGW and Strawberry from PATH to avoid conflicts with MSVC
WINDOWS_CMAKE_PREFIX_CLEANUP_CMD = [
    "# Remove MinGW and Strawberry from path to avoid conflicts with MSVC",
    "$env:PATH = ($env:PATH -split ';' |",
    "  Where-Object {",
    "    $p = $_.TrimEnd('\\\\').ToLower()",
    "    $p -notmatch 'mingw|msys|strawberry'",
    "  }) -join ';'",
    "",
    '"PATH=$env:PATH" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append',
    'Write-Host ""',
    'Write-Host "PATH:"',
    "$env:PATH -split ';'",
    "",
]


def create_orchestrator() -> OptionalOrchestratorWithReport:
    report = Report()

    base_target_dir = Path("workspace")
    base_install_dir = base_target_dir / Path("install")
    base_libs_dir = base_target_dir / Path("libs")
    cscmake_version = "1.0.0"

    o = create_default_orchestrator(
        name="csopencvcpu",
        # staggered weekly run (UTC), one project at a time in the build-train order (no shared runners)
        schedule=Cron.weekly(DayOfWeek.MON, hour=1, minute=0),
        version=OPENCV_VERSION,
        base_install_dir=base_install_dir,
        populate_default_matrix=True,
        additional_files_list=[Path("csopencvcpu_config.py")],
        # opt-in variants: Ubuntu 26.04 (as 22.04/24.04) and macOS 15/26 (Ninja Multi-Config, Xcode)
        additional_matrix_list=(
            get_context_list_linux("ubuntu26.04")
            + get_context_list_macos("macos15")
            + get_context_list_macos("macos26")
        ),
    )

    # ----------------------------------------------------------------
    checkout_repos(
        orchestrator=o,
        base_target_dir=base_target_dir,
        checkout_phase_name="Repos Update",
        repo_ref_dict={
            "opencv": f"v{OPENCV_VERSION}-cpu.3",
            "opencv_contrib": f"v{OPENCV_VERSION}-cpu.3",
        },
        release_archive_list=[create_cscmake_release_archive(cscmake_version)],
    )

    # ----------------------------------------------------------------
    # apt packages and precompiled build
    # dependencies (eigen3): the whole environment replication logic lives in
    # csopencvcpu_config.py so that it can be shared with consumers of the
    # precompiled archives.
    report.append_report(
        install_csopencvcpu_build_dependencies(
            orchestrator=o,
            base_libs_dir=base_libs_dir,
            dependencies_config_path=Path("dependencies"),
            dev=True,
            download_dependencies_manifest_and_bundle=True,
            mapping_function=identity_mapping_function,
            phase_name_suffix="csopencvcpu dependencies",
        )
    )

    # ----------------------------------------------------------------
    p = o.create_phase("Configure-Build-Test-Install")

    p.add_step(
        StepCMakeWorkflow(
            name="opencv CMake Workflow (Linux)",
            description="CMake workflow for opencv with config: DEBUG_RELEASE",
            source_dir=(base_target_dir / "opencv").as_posix(),
            config=BuildConfig.DEBUG_RELEASE,
        ).add_extra(StepExecuteOnlyOn(os=OS.LINUX, version_starts_with=UBUNTU_STRING_PREFIX))
    )

    p.add_step(
        StepCMakeWorkflow(
            name="opencv CMake Workflow (macOS)",
            description="CMake workflow for opencv with config: DEBUG_RELEASE",
            source_dir=(base_target_dir / "opencv").as_posix(),
            config=BuildConfig.DEBUG_RELEASE,
        ).add_extra(StepExecuteOnlyOn(os=OS.MACOS))
    )

    # NOTE: we need to use powershell for windows because of the path manipulation
    # needed to remove MinGW and Strawberry from the path to avoid conflicts with MSVC
    p.add_step(
        StepCMakeWorkflow(
            name="opencv CMake Workflow (Windows on powershell)",
            description="CMake workflow for opencv with config: DEBUG_RELEASE",
            source_dir=(base_target_dir / "opencv").as_posix(),
            config=BuildConfig.DEBUG_RELEASE,
        )
        .add_extra(StepExecuteOnlyOn(os=OS.WINDOWS))
        .add_extra(StepCMakeWorkflowGithubPowershell())
        .add_extra(StepCMakeWorkflowGithubExtraCommandsPrefix(cmd=WINDOWS_CMAKE_PREFIX_CLEANUP_CMD))
    )

    # ----------------------------------------------------------------
    create_and_upload_artifacts(
        orchestrator=o,
        base_install_dir=base_install_dir,
        repos_version_list=[PackageVersion("opencv", OPENCV_VERSION)],
    )

    # single return point
    if report.has_errors():
        return OptionalOrchestratorWithReport.create_report(report)
    return OptionalOrchestratorWithReport.create_result_and_report(o, report)


def main(argv: Sequence[str] | None = None) -> int:
    script_path = str(Path(__file__).resolve())
    return orchestrator_main_with_default_run(script_path, argv)


if __name__ == "__main__":
    sys.exit(main())
