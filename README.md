# PROJECT-AUDITOR

A local-first project auditing tool that inspects ZIP archives, performs static code analysis, and provides AI-assisted code reviews through a locally hosted Ollama model.

PROJECT-AUDITOR is designed for personal use on a Windows laptop. It analyzes source code without executing the uploaded project and is intended to become an independent auditing tool that can later integrate with IRA.

## Features

- **ZIP project upload** — upload a project archive for inspection.
- **Technology detection** — identify supported programming languages, frameworks, and libraries.
- **Static analysis** — inspect source files for potential security and code-quality issues.
- **Secret-pattern detection** — identify patterns such as private keys, AWS access-key identifiers, API-key assignments, and hardcoded password or secret assignments.
- **AI-assisted review** — run an additional code review using a locally hosted Ollama model.
- **Audit reports** — retrieve generated reports using the project's ID.
- **Local-first AI workflow** — use Ollama running on your own machine instead of a hosted AI inference service.

> Static analysis and AI review are assistance tools, not proof that a project is secure. Findings may include false positives or miss issues that require runtime analysis.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| UI | Framer Motion, Lucide |
| Backend | Python 3.12, FastAPI |
| AI review | Ollama |
| Tested AI model | `qwen2.5-coder:7b` |
| Development environment | Windows, PowerShell |

## Requirements

- Windows 10/11
- Python 3.12
- Node.js and npm
- Git
- Ollama installed and running
- A compatible local model available in Ollama

Check your installations:

```powershell
python --version
node --version
npm --version
git --version
ollama --version
```

## Run Locally

Open two PowerShell terminals from the project root.

### 1. Start the Backend

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Backend address:

```text
http://127.0.0.1:8000
```

### 2. Start the Frontend

In a second terminal:

```powershell
cd frontend
npm.cmd run dev
```

Open the local URL printed by Vite. The usual development URL is:

```text
http://localhost:5173
```

### 3. Start Ollama

Make sure Ollama is running and the required model is available:

```powershell
ollama list
ollama run qwen2.5-coder:7b
```

If the model is not installed, Ollama will download it. Keep Ollama running while using the AI audit feature.

## Typical Workflow

1. Start the backend, frontend, and Ollama.
2. Open PROJECT-AUDITOR in your browser.
3. Upload a ZIP archive containing the project.
4. Review the detected project information and static-analysis results.
5. Run the AI-assisted audit for an additional model-based review.
6. Inspect the report and investigate each finding in the original source code.

## API Usage

### Upload a ZIP Archive

You can also test the upload endpoint through PowerShell:

```powershell
$zip = "C:\path\to\your-project.zip"

curl.exe -X POST "http://127.0.0.1:8000/api/projects/upload" `
  -F "files=@$zip"
```

The response includes a project ID.

### Retrieve an Audit Report

Replace the placeholder with the project ID returned by the upload endpoint:

```powershell
$projectId = "YOUR-PROJECT-ID"

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/projects/$projectId/report"
```

## Run Checks

Run backend checks from the project root:

```powershell
.\backend\.venv\Scripts\python.exe -m compileall -q .\backend\app
```

Run backend tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Run frontend checks:

```powershell
cd frontend
npm.cmd run lint
npm.cmd run build
```

### Latest Verified Results

| Check | Result |
|---|---|
| Backend tests | 5 passed |
| Frontend lint | 0 warnings, 0 errors |
| Frontend production build | Passed |
| Python application compilation | Passed |
| Git working tree | Clean after commit and push |

These are the results from the last recorded verification. Rerun the checks after making changes.

## Security and Privacy

- Uploaded project code is inspected as data; the audit workflow does not need to execute the uploaded application.
- AI-assisted review uses a model served locally by Ollama.
- Treat uploaded ZIP archives and their contents as untrusted input.
- Review findings manually before modifying code.
- A detected pattern is not automatically a confirmed vulnerability.
- Do not upload projects containing secrets unless you understand where uploaded files are stored and have removed or protected sensitive information.
- This version is intended for personal, local use. It has not been represented as a production-hardened, multi-user service.

## Current Scope and Limitations

- Results depend on the languages, file types, patterns, and project context supported by the analyzers.
- Static analysis cannot reliably detect every runtime, configuration, dependency, or business-logic vulnerability.
- AI output can be incomplete or incorrect and should be treated as a review suggestion.
- A clean report does not guarantee that a project is free of vulnerabilities.
- Uploaded project code is not executed as part of the audit workflow.

## Repository Hygiene

Runtime upload data is excluded from Git through `.gitignore`.

Do not commit:

- Uploaded ZIP archives
- Extracted project contents
- Credentials or API keys
- Local model files
- Python virtual environments
- Private runtime data

## Future IRA Integration

PROJECT-AUDITOR is intended to remain an independent auditing service. IRA can later communicate with it through its FastAPI interface instead of embedding the analyzer directly into IRA.

Proposed integration:

```text
IRA
 └── Project Auditor Tool Adapter
      └── PROJECT-AUDITOR FastAPI
           ├── ZIP Inspection
           ├── Static Analysis
           ├── Local Ollama Review
           └── Audit Reports
```

Integration principles:

- Keep the auditor's API and analysis engine independent.
- Let IRA request audits and present the returned findings.
- Require user approval before IRA accesses project archives or modifies source files.
- Preserve read-only inspection as the default.
- Never execute untrusted uploaded project code.

## License

No license has been specified yet. Unless a license is added to this repository, all rights remain with the copyright holder and reuse is not automatically granted.
