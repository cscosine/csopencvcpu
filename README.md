# csopencvcpu

OpenCV 5 (CPU) built for every platform

Automated cross-platform build system and CI pipeline recipe for **OpenCV (CPU-only)** (targeting **v5.1.0**), powered by [**csorchestrator**](https://github.com/cscosine/csorchestrator).

---

<!-- cs-template:begin (this block is owned by cs-project-template: do not edit; the rest of the file is the project's) -->
## Getting started

Requires Python 3.11 or newer and Git.

```bash
./setup.sh                    # Windows: .\setup.ps1
source .venv/bin/activate     # Windows: .\.venv\Scripts\Activate.ps1
```

`setup.sh` creates `.venv`, installs the project with its development tools and csorchestrator, and installs the
pre-commit hooks.

csorchestrator: `setup.sh` installs the pinned version (v0.1.0-rc1). Another one:
`./setup.sh --csorchestrator=<tag or branch>`; a local clone, editable: `./setup.sh --csorchestrator=../csorchestrator`
(Windows: `.\setup.ps1 -CsOrchestrator <...>`).

Run the recipe locally, regenerate the GitHub workflow after changing it:

```bash
python csopencvcpu_project.py
python csopencvcpu_project.py generate-github-workflow
```

Generated files, never edited by hand:

| Path | Made by | |
|---|---|---|
| `.github/workflows/csopencvcpu.yml` | `csopencvcpu_project.py generate-github-workflow` | Edit the recipe, then regenerate |
| `csorchestratorsdk/` | csorchestrator, at the same command | The release-manifest helpers the CI runs, without installing csorchestrator |
| `dependencies/` | csorchestrator, at the same command | The manifests and recipes of the releases this project builds on |
| `workspace/` *(git-ignored)* | a local run of `csopencvcpu_project.py` | Sources, builds, installs, deploy archives; delete it to start clean |

Checks and tests:

```bash
pre-commit run --all-files
pytest                        # --run-all: every test, as CI; --run=<marker>: an opt-in group (tests/conftest.py)
```

The shared files (setup, checks, CI, agent rules) come from
[cs-project-template](https://github.com/cscosine/cs-project-template); to bring them to its latest version, on a
branch: `copier update --defaults`.
<!-- cs-template:end -->

## Overview

Building OpenCV from source across multiple platforms is complex and error-prone (image codec dev packages, build toolchain). **csopencvcpu** defines a declarative build and packaging recipe in Python using the `csorchestrator` framework:

- The build pipeline, dependencies, and installation steps are defined in Python code.
- Cross-platform CI workflows (e.g. [`.github/workflows/csopencvcpu.yml`](.github/workflows/csopencvcpu.yml)) are automatically generated.
- Build artifacts, manifests, and release archives (`.tar.gz` bundles) are assembled consistently across environments.

---

## Architecture & Build Pipeline

The core build recipe is defined in [`csopencvcpu_project.py`](csopencvcpu_project.py) and executed across the csorchestrator default execution matrix (`populate_default_matrix=True`).

### Version Alignment

The project version (`5.1.0`, tracking the OpenCV release being built) is defined in [`csopencvcpu_project.py`](csopencvcpu_project.py) (`OPENCV_VERSION`) and mirrored in [`pyproject.toml`](pyproject.toml) — keep the two aligned when bumping the version.

Release tags follow the tag of the OpenCV fork they ship: `v<OpenCV version>-cpu.<n>` (e.g. `v5.1.0-cpu.2`, built
from the forks' `v5.1.0-cpu.2`), release candidates `v5.1.0-cpu.2-rc<n>`. The project version stays the OpenCV
version (`5.1.0`), the one consumers pin (`project_version`). The forks: `cscosine/opencv` and `cscosine/opencv_contrib`,
the same layout and tags, branch `cpu` (opencv's `cscosine/README.md`).

### Execution Phases

1. **Repos Update**:
   - Downloads the csCMake release package pinned in [`csopencvcpu_project.py`](csopencvcpu_project.py) (`cscmake_version`, e.g. `1.0.0-rc8`) and unpacks it into `workspace/csCMake`, where the presets of the OpenCV fork find it (sibling layout).
   - Shallow clones (`depth=1`) of `cscosine/opencv` and `cscosine/opencv_contrib` at the tags configured in [`csopencvcpu_project.py`](csopencvcpu_project.py) (both `v5.1.0-cpu.2`, the CPU variant of the forks).
2. **Install Build Dependencies (csopencvcpu)**:
   - All environment-replication steps: Microsoft fonts EULA pre-accept, libunwind removal (Ubuntu 22.04), apt dev packages, numpy (Windows).
   - Precompiled `eigen3` downloaded from the [third_party_base_libs](https://github.com/cscosine/third_party_base_libs) provider (`ManifestGithub` + `StepGetPrecompiledLibGithub`).
   - Defined in [`csopencvcpu_config.py`](csopencvcpu_config.py) (`install_build_dependencies()`), so that consumers of the precompiled archives can replicate the exact same toolchain and dependencies.
   - **All steps are idempotent**: presence is checked first (e.g. `dpkg -s`), so already-installed components are skipped.
3. **Configure-Build-Test-Install**:
   - Runs the csCMake CMake workflow presets on `workspace/opencv` for config `DEBUG_RELEASE` (single-config generators run debug+release, multi-config run debug-release).
   - On Windows, runs under PowerShell with a PATH sanitization prefix that removes MinGW/Strawberry entries conflicting with MSVC.
4. **Create and Upload Artifacts**:
   - Extracts package versions from the installed CMake config packages, creates `.tar.gz` archives, and uploads them as CI artifacts (released on tags).

### Build Matrix

The csorchestrator default execution matrix (`get_supported_context_os_architecture_list()`):

| OS      | Arch        | Compiler            | Generator                    |
|---------|-------------|---------------------|------------------------------|
| Linux   | x64         | GCC / CLANG         | Ninja Multi-Config (multi)   |
| Linux   | arm64       | GCC / CLANG         | Ninja (single-config)        |
| Windows | x64         | MSVC / MSVC_CLANG   | VS 2022 / VS 2026 (multi)    |
| macOS 15 / 26 | arm64 | Apple Clang       | Ninja Multi-Config, Xcode (multi) |

Ubuntu 22.04 / 24.04 / 26.04 for Linux; 20 variants, the same as every other project: a consumer gets the archive of its own variant, no mapping.

If a restricted matrix is ever needed, reintroduce `utils/build_matrix.py` with a `populate_build_matrix()` function and wire it in `csopencvcpu_project.py` via `populate_default_matrix=False` + `create_default_execution_matrix()`.

---

## Consuming csopencvcpu

[`csopencvcpu_config.py`](csopencvcpu_config.py) is the canonical configuration shipped inside every release bundle (`additional_files_list`). Consuming projects import it from their `dependencies/` folder through the csorchestrator manifest mechanism (same pattern as `csqt6_config.py` / `third_party_base_libs_config.py`).

> [!IMPORTANT]
> `csopencvcpu_config.py` is intentionally **self-contained**: it imports only csorchestrator and the standard library, never project-local modules such as `utils.*`. The release bundle preserves relative paths, but consumers import the module from their own tree, so project-local imports would not resolve there.

When consumed, `auto_install_csorchestrator_managed_libraries()`:

1. adds `install_build_dependencies()` steps to the consumer pipeline (apt environment replication);
2. adds the steps to download the precompiled OpenCV archives, the archive of the consumer variant (every variant is built, no mapping).

---

## Project Layout

```
csopencvcpu/
├── csopencvcpu_project.py     # Core pipeline definition and phases
├── csopencvcpu_config.py      # Canonical config: deps + env install (included in release)
├── tests/
│   └── csopencvcpu/           # Unit tests of the config
└── .github/workflows/
    └── csopencvcpu.yml         # [Autogenerated] GitHub Actions CI workflow (emitted by csopencvcpu_project.py)
```

## Local Execution Policy (Build Guard)

**Do NOT run full local builds** of OpenCV (executing all phases of `./csopencvcpu_project.py`): compiling OpenCV requires significant disk space and long build times. Only run unit tests (`pytest`) or workflow re-generation when checking local configuration logic.

---

## License

This project is licensed under the [MIT License](LICENSE).
