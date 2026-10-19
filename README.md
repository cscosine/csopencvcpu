# csopencvcpu

Automated cross-platform build system and CI pipeline recipe for **OpenCV (CPU-only)** (targeting **v5.0.0**), powered by [**csorchestrator**](https://github.com/cscosine/csorchestrator).

---

## Getting Started

### Prerequisites

* Python `>= 3.11`
* Git
* [csorchestrator](https://github.com/cscosine/csorchestrator) cloned as a peer directory (`../csorchestrator`)

### Environment Setup

Bootstrap the local virtual environment, install dev dependencies, link `csorchestrator` in editable mode, and install git hooks:

**Linux / macOS:**
```bash
./setup.sh
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
```

### Running the Orchestrator Locally

Execute the orchestrator script to run pipeline steps locally:

```bash
./csopencvcpu_project.py
# or
python csopencvcpu_project.py
```

### Re-generating the GitHub Workflow

To re-generate the GitHub Actions CI workflow (`.github/workflows/csopencvcpu.yml`) from the definition in [`csopencvcpu_project.py`](csopencvcpu_project.py):

```bash
./csopencvcpu_project.py generate-github-workflow
# or
python csopencvcpu_project.py generate-github-workflow
```

### Development & Quality Checks

```bash
# Code formatting and linting
ruff check .
ruff format .

# Strict type checking
python -m mypy . --config-file=pyproject.toml

# Unit tests
pytest

# Run all pre-commit hooks
pre-commit run --all-files
```

---

## Overview

Building OpenCV from source across multiple platforms is complex and error-prone (image codec dev packages, build toolchain). **csopencvcpu** defines a declarative build and packaging recipe in Python using the `csorchestrator` framework:

- The build pipeline, dependencies, and installation steps are defined in Python code.
- Cross-platform CI workflows (e.g. [`.github/workflows/csopencvcpu.yml`](.github/workflows/csopencvcpu.yml)) are automatically generated.
- Build artifacts, manifests, and release archives (`.tar.gz` bundles) are assembled consistently across environments.

---

## Architecture & Build Pipeline

The core build recipe is defined in [`csopencvcpu_project.py`](csopencvcpu_project.py) and executed across the csorchestrator default execution matrix (`populate_default_matrix=True`).

### Version Alignment

The project version (`5.0.0`, tracking the OpenCV release being built) is defined in [`csopencvcpu_project.py`](csopencvcpu_project.py) (`OPENCV_VERSION`) and mirrored in [`pyproject.toml`](pyproject.toml) — keep the two aligned when bumping the version.

### Execution Phases

1. **Repos Update**:
   - Shallow clones (`depth=1`) of `cscosine/csCMake`, `cscosine/opencv` and `cscosine/opencv_contrib` (branch `dev-cpu`).
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

If a restricted matrix is ever needed, reintroduce `utils/build_matrix.py` with a `populate_build_matrix()` function and wire it in `csopencvcpu_project.py` via `populate_default_matrix=False` + `create_default_execution_matrix()`.

---

## Consuming csopencvcpu

[`csopencvcpu_config.py`](csopencvcpu_config.py) is the canonical configuration shipped inside every release bundle (`additional_files_list`). Consuming projects import it from their `dependencies/` folder through the csorchestrator manifest mechanism (same pattern as `csqt6_config.py` / `third_party_base_libs_config.py`).

> [!IMPORTANT]
> `csopencvcpu_config.py` is intentionally **self-contained**: it imports only csorchestrator and the standard library, never project-local modules such as `utils.*`. The release bundle preserves relative paths, but consumers import the module from their own tree, so project-local imports would not resolve there.

When consumed, `auto_install_csorchestrator_managed_libraries()`:

1. adds `install_build_dependencies()` steps to the consumer pipeline (apt environment replication);
2. adds the steps to download the precompiled OpenCV archives, using `opencv_mapping()` to resolve the archive matching the consumer context.

---

## Project Layout

```
csopencvcpu/
├── csopencvcpu_project.py     # Core pipeline definition and phases
├── csopencvcpu_config.py      # Canonical config: deps + env install + mapping (included in release)
├── tests/
│   └── csopencvcpu/           # Unit tests for config mappings
└── .github/workflows/
    └── csopencvcpu.yml         # [Autogenerated] GitHub Actions CI workflow (emitted by csopencvcpu_project.py)
```

### Autogenerated Files Lifecycle

| Path | Origin / Trigger | Maintenance Policy |
|---|---|---|
| [`.github/workflows/csopencvcpu.yml`](.github/workflows/csopencvcpu.yml) | Autogenerated by running `./csopencvcpu_project.py generate-github-workflow`. | **Never edit manually.** Edit `csopencvcpu_project.py`, then re-run the generator command. |
| `workspace/` *(gitignored)* | Created at runtime when running `./csopencvcpu_project.py` locally. | Holds cloned sources, temporary build directories, and install outputs. Can be safely deleted to reset local state. |

---

## Local Execution Policy (Build Guard)

**Do NOT run full local builds** of OpenCV (executing all phases of `./csopencvcpu_project.py`): compiling OpenCV requires significant disk space and long build times. Only run unit tests (`pytest`) or workflow re-generation when checking local configuration logic.

---

## License

This project is licensed under the [MIT License](LICENSE).
