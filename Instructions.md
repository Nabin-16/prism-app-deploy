# PRISM Desktop Application — Deployment Setup

## Context

The PRISM desktop application is an existing Python/PySide6 application that already works locally.

The next task is to prepare it for **cross-platform distribution** on:

- Windows
- macOS
- Linux

Do **not** redesign or rewrite the application. The deployment work should sit around the existing application and preserve its current behavior.

The desired architecture is broadly:

```text
Existing PySide6 source
        ↓
PyInstaller
        ↓
Platform-specific packaging
        ↓
GitHub Actions
        ↓
Windows / macOS / Linux builds
        ↓
GitHub Release
        ↓
Website download links
```

Use the deployment approach followed by the reference PRISM project as architectural inspiration, but inspect this repository first and adapt the implementation to its actual structure rather than blindly copying files.

---

## 1. Inspect Before Changing Anything

First inspect the repository and identify:

- application entry point
- Python version
- dependency files
- PySide6 structure
- application resources
- icons
- bundled datasets/reference results
- environment variables
- Supabase integration
- Ollama integration
- existing version information
- existing build or packaging configuration
- `.gitignore`
- current GitHub Actions configuration, if any

Then briefly explain the deployment structure you intend to add.

Do not modify application logic until it is clear that a change is actually required for packaging.

---

## 2. Application Packaging

Use **PyInstaller** as the primary packaging mechanism.

Create a suitable PyInstaller specification/configuration if one does not already exist.

The packaged application must contain everything required for PRISM to run independently of a user's Python installation, including relevant:

- Python modules
- PySide6 dependencies
- application resources
- icons
- bundled benchmark data
- bundled/reference results required by the dashboard

Prefer a maintainable **onedir** build unless inspection of the project gives a strong reason otherwise.

Do not package:

- `.git`
- virtual environments
- caches
- development artifacts
- unnecessary raw experiment files
- private research data
- credentials
- secret keys

The packaged application must continue using the existing PRISM architecture.

---

## 3. Platform Packaging

After confirming that the PyInstaller build works, create platform-specific packaging.

### Windows

Use an installer mechanism such as **Inno Setup**.

Conceptually:

```text
PyInstaller
    ↓
PRISM application directory
    ↓
Windows installer
    ↓
PRISM-Setup-<version>.exe
```

The installer should provide a normal user installation experience.

### macOS

Package the application as a `.app` and create a `.dmg`.

Conceptually:

```text
PyInstaller
    ↓
PRISM.app
    ↓
DMG
    ↓
PRISM-<version>.dmg
```

Leave the structure ready for future Apple code signing and notarization, but do not introduce fake signing credentials or unnecessary complexity.

### Linux

Prefer:

```text
AppImage
```

for general distribution.

A `.deb` package may also be produced if it can be done cleanly.

Make the target architecture explicit where necessary.

---

## 4. GitHub Actions

Create or improve a GitHub Actions workflow that builds PRISM independently on:

```text
Windows
macOS
Linux
```

Prefer a matrix-based workflow where appropriate.

The workflow should conceptually perform:

```text
Checkout repository
        ↓
Set up Python
        ↓
Install dependencies
        ↓
Build with PyInstaller
        ↓
Run platform-specific packaging
        ↓
Upload build artifacts
        ↓
Publish release when appropriate
```

Normal pushes should not automatically create public releases.

Use version tags such as:

```text
v0.1.0
v0.2.0
v1.0.0
```

as the normal release mechanism.

Manual workflow dispatch can be included if useful for testing the packaging pipeline.

---

## 5. GitHub Artifacts and Releases

Understand and use the distinction between:

**Artifact**

A file produced by a GitHub Actions workflow for testing/download.

and:

**Release**

A public version of PRISM containing the final installers/packages users should download.

The desired release should eventually look conceptually like:

```text
PRISM v1.0.0

PRISM-Setup-1.0.0.exe
PRISM-1.0.0.dmg
PRISM-x86_64.AppImage
PRISM-x86_64.deb
```

Do not commit generated installers into the source repository.

---

## 6. Versioning

Use a single sensible source for the application version if the project already has one.

Avoid maintaining unrelated hard-coded versions across:

- Python code
- PyInstaller
- Windows installer
- macOS package
- Linux package
- GitHub Release

The release tag and packaged application should remain consistent.

---

## 7. Secrets and Security

This is critical.

PRISM interacts with Supabase and GitHub-related infrastructure.

The packaged desktop application must **never contain**:

- Supabase secret/service-role keys
- GitHub personal access tokens
- backend publishing credentials
- repository write credentials

Only genuinely public/client-side configuration may be included in the application.

Never put secrets inside:

- source code
- `.env` files committed to Git
- PyInstaller configuration
- installer scripts
- GitHub Actions YAML
- bundled resources

If the existing application uses environment variables, preserve that design.

---

## 8. Ollama

PRISM uses Ollama for local model inference.

The deployment process must preserve the existing Ollama integration.

Do not replace Ollama with a cloud inference service.

First determine how the current application handles Ollama:

- detection
- connection
- model availability
- model pulling
- startup

If Ollama is currently expected to be installed separately, do not automatically redesign this behavior as part of deployment.

The packaging task should make the existing behavior work reliably in the packaged application.

---

## 9. Bundled Data

PRISM contains benchmark/reference data that must remain available to the packaged application.

Determine which data is actually required at runtime.

The packaged application should be able to:

- load its bundled benchmark data
- display bundled/preprocessed model results
- run the benchmark
- access the dashboard

Do not blindly bundle the entire repository's `results/` directory.

Only include the runtime data required by the application.

---

## 10. Testing

Before considering deployment complete, test the **packaged application**, not only the development version.

Verify at minimum:

- PRISM launches
- resources load correctly
- icons load
- dashboard opens
- bundled results are available
- Ollama detection works
- model selection works
- benchmark execution works
- cancellation works
- Supabase operations that are intended for the client still work
- application does not depend on development-directory paths
- no secret credentials are embedded

A successful GitHub Actions build alone is not sufficient evidence that the application works correctly.

---

## 11. Keep Deployment Separate From Application Logic

The deployment implementation should preferably be isolated into files/directories such as:

```text
prism.spec

packaging/
├── windows/
├── macos/
└── linux/

.github/
└── workflows/
    └── build.yml
```

The exact structure should follow the repository's existing conventions.

Do not modify working benchmark, parser, scorer, dashboard, or inference logic merely to make the deployment configuration easier.

If a code change is genuinely required for packaging, explain why before making it.

---

## 12. What NOT To Do

Do not:

- rewrite the application
- change benchmark methodology
- change datasets
- change prompt conditions
- change scoring formulas
- remove existing functionality
- introduce cloud inference
- add unnecessary deployment frameworks
- blindly copy the reference project's files
- commit generated installers
- expose secrets
- place private credentials inside the packaged application
- make every Git push generate a release

Keep the deployment system as simple as reasonably possible.

---

## 13. Expected End State

The final system should allow the maintainers to work like this:

```text
Develop locally
      ↓
Test PRISM locally
      ↓
Commit / push source
      ↓
GitHub Actions can test/build it
      ↓
Create version tag
      ↓
GitHub Actions builds:
    Windows
    macOS
    Linux
      ↓
Installers/packages become artifacts
      ↓
GitHub Release is created
      ↓
Website links users to the release
```

The objective is a **reproducible and maintainable release pipeline**, not an unnecessarily complicated DevOps system.

---

## Agent Working Rule

Before implementing anything:

1. Inspect the repository.
2. Identify what already exists.
3. Identify what is missing for deployment.
4. Present a concise proposed deployment structure.
5. Implement only the required deployment components.
6. Test the packaging process.
7. Report exactly what was added or changed.

Do not assume the repository is identical to the reference project.

The existing PRISM application is the source of truth.