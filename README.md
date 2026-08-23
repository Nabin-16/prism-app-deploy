# PRISM — Desktop Benchmark for Prompt Reliability

**PRISM** (*Prompt Reliability & Inconsistency Scoring for Models*) is a cross-platform desktop application for benchmarking behavioral consistency and prompt sensitivity in local Large Language Models (LLMs) running via [Ollama](https://ollama.com).

Unlike traditional static benchmarks that measure only accuracy under a single prompt format, PRISM measures how reliably an LLM adheres to its reasoning and outputs across semantically equivalent prompt formulations.

---

## Key Features

- **Local Inference Engine**: Connects directly to local Ollama instances with automated model detection, health checking, and pull status monitoring.
- **Controlled Benchmark Methodology**: Runs deterministic multi-prompt experiments across validated benchmark datasets (ARC-Challenge, SciQ) under standardized temperature and sampling configurations.
- **Consistency & Reliability Scoring**: Computes stability scores, deviation across prompts, and format adherence across 5 standardized prompt variations ($P_0$ through $P_4$).
- **Interactive Analytics Dashboard**: Native desktop interface featuring model performance KPI tiles, consistency comparisons, per-question drill-downs, and side-by-side model comparison views.
- **PDF Report Generation**: Export publication-ready benchmark summary reports with a single click.
- **Offline Resilience & Bundled Baselines**: Includes frozen precomputed results for standard reference models (`llama3.2:3b`, `gemma3:4b`, `phi4-mini:latest`, `mistral:7b`) for instant local exploration without initial inference overhead.
- **Public Results Hub Integration**: Fetches and synchronizes community-verified model benchmarks directly from the public dataset repository:
  👉 **[Nabin-16/Reliability-test-result-model-versions](https://github.com/Nabin-16/Reliability-test-result-model-versions)**

---

## Public Data & Community Results

Maintainer-verified and approved benchmark runs are published and archived in the official public results repository:

> **Public Results Repository:**  
> **https://github.com/Nabin-16/Reliability-test-result-model-versions**

### How It Works:
1. **Local Benchmarks**: When you run benchmarks on your machine, results are stored locally in SQLite (`~/.prism/prism.db`).
2. **Cloud Sync (Optional)**: If configured with Supabase credentials, completed runs sync as unapproved submissions to the central database.
3. **Public Discoverability**: Approved benchmarks are exported to the public results repository, enabling the PRISM desktop app to discover and display verified baselines via CDN without requiring direct database access.

---

## Installation & Quick Start

### Option 1: Download Pre-built Installers

Pre-built standalone packages are available on the [Releases](https://github.com/Nabin-16/prism-app-deploy/releases) page:

- **Windows**: `PRISM-Setup-<version>.exe` (Inno Setup Installer)
- **macOS**: `PRISM-<version>.dmg` (Universal Disk Image)
- **Linux**: `PRISM-x86_64.AppImage` or `prism_<version>_amd64.deb`

### Option 2: Running from Source

#### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com) installed and running locally

```bash
# Clone the repository
git clone https://github.com/Nabin-16/prism-app-deploy.git
cd prism-app-deploy

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Launch PRISM
python main.py
```

---

## Configuration & Environment Variables

Create a `.env` file from the provided `.env.example`:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `PRISM_SUPABASE_URL` | *(Optional)* Supabase project URL for syncing run results. |
| `PRISM_SUPABASE_PUBLISHABLE_KEY` | *(Optional)* Client publishable/anon key (restricted by RLS policies). |
| `OLLAMA_BASE_URL` | Ollama API endpoint (Default: `http://localhost:11434`). |

> 🔒 **Security Note**: Never commit service-role keys or secret tokens. The desktop application only requires public/anon keys with row-level security enabled.

---

## Building & Packaging

PRISM uses **PyInstaller** for standalone executable compilation, combined with native platform installers:

```bash
# Compile onedir build with PyInstaller
pyinstaller prism.spec --clean --noconfirm
```

### Platform Installer Scripts

- **Windows Installer (Inno Setup)**:
  ```powershell
  & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\windows\installer.iss /DMyAppVersion=1.0.0
  ```
- **macOS DMG**:
  ```bash
  ./packaging/macos/build_dmg.sh 1.0.0
  ```
- **Linux AppImage & Debian Package**:
  ```bash
  ./packaging/linux/build_appimage.sh
  ./packaging/linux/build_deb.sh 1.0.0
  ```

---

## Continuous Integration & Release Pipeline

The GitHub Actions workflow in [`.github/workflows/build.yml`](.github/workflows/build.yml) automatically builds all platform binaries and publishes a GitHub Release when a version tag is pushed:

```bash
git tag v1.0.0
git push deploy v1.0.0
```

---

## License

This project is licensed under the MIT License — see the LICENSE file for details.