# PRISM Desktop App — Windows Optimization & Ollama Setup Implementation Plan

This implementation plan provides detailed architectural analysis, root causes, and actionable solutions for the issues encountered on the PRISM Desktop Application when running on Windows devices.

---

## 1. Overview of Identified Issues

| # | Issue Area | Observed Symptom | Impact |
|---|---|---|---|
| **1** | **Windows Security / SmartScreen** | Windows Defender / SmartScreen blocks or warns on installer download/execution. | Low-to-Medium (User trust barrier; easily bypassed with "More info" -> "Run anyway"). |
| **2** | **Rendering Performance & Asset Loading** | App feels slow/stuttery on Windows compared to Linux; app logo disappears/fails to render on Windows. | High (User experience & visual branding degradation). |
| **3** | **Ollama Automated Setup & Unwanted Sign-in** | Terminal window pops up during Ollama installation; Ollama GUI launches asking for user sign-in. | Critical (Disruptive UX; Ollama should run locally & headlessly without account login). |

---

## 2. Deep-Dive Analysis & Solution Architecture

---

### Issue 1: Windows SmartScreen & Code Signing

#### Root Cause
Windows SmartScreen flags newly compiled `.exe` installers that lack a trusted digital code-signing certificate (EV or standard OV certificate) or lack sufficient download reputation in Microsoft's telemetry database.

#### Solution Path
1. **Code Signing Pipeline (CI/CD)**:
   - If a code-signing certificate is available: Configure `electron-builder` or `signtool.exe` in the GitHub Actions release workflow.
   - Use SignPath, Azure Trusted Signing, or a DigiCert/Sectigo EV certificate stored in GitHub Secrets.
2. **Open-Source Alternative**:
   - Publish releases with SHA-256 checksums (`latest.yml` / `SHA256SUMS.txt`).
   - Add a brief documentation note on the website docs on how to bypass SmartScreen (*"Click More Info → Run Anyway"* until reputation builds).

---

### Issue 2: Rendering Performance & Logo Missing on Windows

#### Root Cause Analysis

1. **Missing Logo on Windows (Path Resolution)**:
   - **Cross-Platform Path Separators**: Windows uses backslashes (`\`) whereas POSIX/Linux uses forward slashes (`/`). Hardcoded string paths or naive regex splits break on Windows.
   - **Electron Packaging (ASAR vs. Resources)**: In production builds, assets packaged inside the `.asar` archive or unpacked into `process.resourcesPath` must be referenced using `path.join(__dirname, ...)` or `path.resolve(process.resourcesPath, ...)`.
   - **Custom Protocols / `file://` URL schemes**: On Windows, `file:///C:/...` vs `file://C:\...` can fail to load if not properly converted using Node's `url.pathToFileURL()`.

2. **UI Sluggishness & Rendering Lag**:
   - **Hardware Acceleration & GPU Flag Incompatibilities**: Electron on some Windows graphics drivers stutters with hardware acceleration or angle backends.
   - **IPC Overload / Frequent Polling**: Heavy polling or unthrottled IPC events (e.g. streaming logs, benchmark metrics) from the main process or background Python/Node engine to the React renderer thread.
   - **Window Transparency / Vibrancy Overhead**: Using heavy acrylic/vibrancy effects or `transparent: true` on Windows `BrowserWindow` causes frame drops.

#### Proposed Solution Path

##### A. Fix Asset/Logo Path Resolution
- In the main process and preload script, standardize path resolution using Node's `path` module:
  ```typescript
  import path from 'node:path';
  import { app } from 'electron';

  // Determine correct base directory (development vs. packaged production)
  const isPackaged = app.isPackaged;
  const assetPath = isPackaged
    ? path.join(process.resourcesPath, 'assets')
    : path.join(__dirname, '../../assets');

  // In BrowserWindow config:
  const win = new BrowserWindow({
    icon: path.join(assetPath, 'logo.ico'), // .ico is preferred for Windows taskbar/window
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      sandbox: false,
    },
  });
  ```
- Ensure window icons on Windows provide a `.ico` format (or high-res multi-layer 256x256 `.png`).

##### B. Rendering & Performance Tuning
- **Optimize Electron Launch Flags**:
  ```typescript
  // Enable smooth rendering & rasterization
  app.commandLine.appendSwitch('enable-gpu-rasterization');
  app.commandLine.appendSwitch('enable-zero-copy');
  ```
- **Throttle IPC / State Updates**:
  - Implement batching/debouncing on real-time log outputs or progress indicators sent over IPC (limit updates to max 30-60 FPS instead of per-chunk re-renders).
- **React Profiling & Virtualization**:
  - Wrap large results tables or terminal log outputs with virtualized lists (`react-window` or `@tanstack/react-virtual`).

---

### Issue 3: Silent Ollama Installation & Headless Execution (No Sign-In)

#### Root Cause Analysis
1. **Interactive Terminal Popup**:
   - The installer/app executes `child_process.exec()` or PowerShell without hidden window flags (`windowsHide: true`, `CreateNoWindow = true`), causing a flash of `cmd.exe` or `powershell.exe`.
2. **Ollama GUI / Sign-in Prompt**:
   - The default `OllamaSetup.exe` on Windows installs Ollama and immediately launches the Ollama Desktop system tray application.
   - The desktop tray application opens the browser/GUI prompting users to create an account or sign into Ollama.com.
   - **Crucial Fact**: Local LLM inference via Ollama does **not** require any account or sign-in. Ollama can run purely as a headless background daemon (`ollama serve` listening on `http://127.0.0.1:11434`).

#### Proposed Solution Path

##### A. Silent / Headless Ollama Installation on Windows
- When downloading and running `OllamaSetup.exe`, invoke it with silent flags:
  ```powershell
  # Download Ollama Windows Installer
  Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile "$env:TEMP\OllamaSetup.exe"

  # Execute silent install without launching the UI
  Start-Process -FilePath "$env:TEMP\OllamaSetup.exe" -ArgumentList "/SILENT", "/VERYSILENT", "/NORESTART" -Wait -WindowStyle Hidden
  ```

##### B. Prevent GUI Launch & Run Headless Background Server
- Kill any auto-started tray UI if spawned by the installer:
  ```powershell
  Stop-Process -Name "ollama app" -Force -ErrorAction SilentlyContinue
  ```
- Run the Ollama server as a detached, silent background service or via Node's `spawn`:
  ```typescript
  import { spawn } from 'node:child_process';

  export function startOllamaDaemon() {
    const ollamaProcess = spawn('ollama', ['serve'], {
      detached: true,
      windowsHide: true, // Hides terminal window on Windows
      stdio: 'ignore',
      env: {
        ...process.env,
        OLLAMA_HOST: '127.0.0.1:11434',
        OLLAMA_ORIGINS: '*',
        OLLAMA_NOPRUNE: '1',
      },
    });

    ollamaProcess.unref();
    return ollamaProcess;
  }
  ```

##### C. Health Check & Ready State Verification
- Implement a polling health-check against `http://127.0.0.1:11434/api/tags` or `http://127.0.0.1:11434/` to confirm the daemon is responsive before issuing model pull commands (`ollama pull <model>`).

---

## 3. Step-by-Step Execution Plan for Implementation Agent

### Phase 1: Windows Ollama Management Overhaul
- [ ] Locate the setup/dependency management module in the desktop app (e.g. `src/main/services/ollama.ts` or `scripts/install-ollama.bat` / `.ps1`).
- [ ] Add `/SILENT` / `/VERYSILENT` and `-WindowStyle Hidden` / `windowsHide: true` to all installation subroutines.
- [ ] Ensure process initiation directly targets `ollama serve` and bypasses the Ollama desktop tray application.
- [ ] Add health-check polling to verify `http://127.0.0.1:11434` is active before triggering model downloads.

### Phase 2: Logo and Asset Path Resolution
- [ ] Audit all image/icon references across `main/`, `preload/`, and `renderer/`.
- [ ] Replace hardcoded relative paths with `path.join()` leveraging `app.isPackaged ? process.resourcesPath : __dirname`.
- [ ] Provide dedicated `logo.ico` for Windows window titlebars, taskbars, and notifications.

### Phase 3: Performance & Rendering Optimization
- [ ] Verify GPU rasterization flags in Electron's `app.whenReady()`.
- [ ] Throttle IPC message frequencies from background processes to the React UI.
- [ ] Ensure heavy data tables and log viewer components use list virtualization.

### Phase 4: Verification & Testing
- [ ] Test fresh installation on a clean Windows sandbox/VM without pre-existing Ollama.
- [ ] Verify no command prompt / PowerShell window flickers during startup.
- [ ] Confirm no Ollama sign-in screen appears, and models pull/run seamlessly.
- [ ] Confirm logo renders consistently across Windows taskbar, window frame, and in-app headers.
