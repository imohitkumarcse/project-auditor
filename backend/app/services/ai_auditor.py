import json
import re
import urllib.error
import urllib.request
import zipfile

from pathlib import PurePosixPath
from typing import Any


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

DEFAULT_MODEL = "qwen2.5-coder:7b"

MAX_FILES = 30
MAX_FILE_SIZE = 40_000
MAX_TOTAL_CHARS = 60_000
OLLAMA_TIMEOUT = 240

SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".java", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".go", ".rs",
    ".php", ".rb", ".sql", ".json",
    ".yaml", ".yml", ".toml", ".ini",
    ".md", ".txt",
}

SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "coverage",
    "vendor",
    ".idea",
    ".vscode",
}

SKIP_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "secrets.json",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
}


def _safe_path(name: str) -> bool:
    """Allow only safe project-relative paths."""

    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)

    if path.is_absolute() or ".." in path.parts:
        return False

    if any(part.lower() in SKIP_DIRS for part in path.parts):
        return False

    if path.name.lower() in SKIP_FILES:
        return False

    return True


def _file_priority(path: str) -> int:
    """Prioritize executable application source over documentation."""

    normalized = path.lower().replace("\\", "/")
    filename = PurePosixPath(normalized).name

    priority = 0

    # Documentation should never crowd out implementation files.
    if filename.startswith("readme"):
        priority += 10
    elif filename in {"testing.md", "contributing.md", "changelog.md"}:
        priority += 0

    # Dependency manifests.
    if filename in {
        "package.json", "requirements.txt", "pyproject.toml",
        "pom.xml", "build.gradle", "cargo.toml", "go.mod",
        "composer.json",
    }:
        priority += 65

    # Common application entry points.
    if filename in {
        "main.py", "app.py", "server.py", "index.py",
        "main.ts", "main.tsx", "app.ts", "app.tsx",
        "index.ts", "index.tsx", "server.js", "server.ts",
        "main.js", "index.js", "app.js", "script.js",
        "index.html",
    }:
        priority += 100

    if any(part in normalized for part in (
        "/api/", "/routes/", "/routers/", "/controllers/",
    )):
        priority += 65

    if any(part in normalized for part in (
        "/models/", "/schemas/", "/services/",
        "/src/", "/scripts/",
    )):
        priority += 35

    if any(keyword in filename for keyword in (
        "route", "router", "controller", "model",
        "schema", "config", "database", "session",
        "security", "auth", "service",
    )):
        priority += 30

    if filename.endswith((".js", ".ts", ".jsx", ".tsx", ".py")):
        priority += 20

    if "test" in filename or "spec" in filename:
        priority += 5

    return priority


def _collect_source_files(
    archive_path: str,
) -> list[dict[str, Any]]:
    """Read a limited number of safe source files directly from the ZIP."""

    candidates = []

    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue

            if not _safe_path(info.filename):
                continue

            path = PurePosixPath(
                info.filename.replace("\\", "/")
            )

            if path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue

            if info.file_size == 0 or info.file_size > MAX_FILE_SIZE:
                continue

            candidates.append({
                "path": info.filename,
                "size": info.file_size,
                "priority": _file_priority(info.filename),
                "info": info,
            })

        candidates.sort(
            key=lambda item: (
                item["priority"],
                -item["size"],
            ),
            reverse=True,
        )

        selected = []
        total_chars = 0

        for candidate in candidates:
            if len(selected) >= MAX_FILES:
                break

            try:
                raw = archive.read(candidate["info"])
                content = raw.decode(
                    "utf-8",
                    errors="ignore",
                )

            except (OSError, RuntimeError, zipfile.BadZipFile):
                continue

            remaining = MAX_TOTAL_CHARS - total_chars

            if remaining <= 0:
                break

            if len(content) > remaining:
                content = content[:remaining]

            if not content.strip():
                continue

            selected.append({
                "path": candidate["path"],
                "content": content,
                "line_count": len(content.splitlines()),
            })

            total_chars += len(content)

        return selected


def _build_source_context(
    files: list[dict[str, Any]],
) -> str:
    """Build a readable source context for the model."""

    sections = []

    for file in files:
        numbered_lines = []

        for index, line in enumerate(
            file["content"].splitlines(),
            start=1,
        ):
            numbered_lines.append(
                f"{index:04d}: {line}"
            )

        sections.append(
            f"\n\n===== FILE: {file['path']} =====\n"
            + "\n".join(numbered_lines)
        )

    return "\n".join(sections)

def _extract_architecture_facts(files: list[dict]) -> dict:
    """Extract architecture facts directly from reviewed source files."""

    facts = {
        "entry_points": [],
        "components": [],
        "dependencies": [],
        "routes": [],
        "database_indicators": [],
        "security_indicators": [],
        "frontend_indicators": [],
        "backend_indicators": [],
    }

    def add(key: str, value: str) -> None:
        if value and value not in facts[key]:
            facts[key].append(value[:240])

    for file in files:
        path = file["path"].replace("\\", "/")
        content = file["content"]
        lower_path = path.lower()
        lower_content = content.lower()
        filename = PurePosixPath(path).name.lower()
        lines = content.splitlines()

        # Actual application entry points, not arbitrary index files.
        if filename in {"main.py", "app.py", "server.py"}:
            if any(term in lower_content for term in (
                "fastapi(", "flask(", "django", "uvicorn.run",
                "if __name__",
            )):
                add("entry_points", path)

        elif filename in {"server.js", "server.ts"}:
            if any(term in lower_content for term in (
                "listen(", "createServer(", "express(",
            )):
                add("entry_points", path)

        elif filename == "index.html":
            if re.search(
                r'<script[^>]+src\s*=',
                content,
                re.IGNORECASE,
            ):
                add("entry_points", path)
                add("frontend_indicators", "HTML application entry point")
        elif filename in {"server.js", "server.ts"}:
            if any(term in lower_content for term in (
                "listen(", "createServer(", "express(",
            )):
                add("entry_points", path)

        # Components and application modules.
        if any(part in lower_path for part in (
            "/api/", "/routes/", "/services/", "/models/",
            "/components/", "/pages/", "/controllers/",
        )):
            add("components", path)

        # React components declared or exported in JSX/TSX.
        if PurePosixPath(path).suffix.lower() in {".jsx", ".tsx"}:
            component_pattern = re.compile(
                r"(?:export\s+default\s+function|"
                r"export\s+function|function|"
                r"const|class)\s+([A-Z][A-Za-z0-9_]*)"
            )

            for match in component_pattern.finditer(content):
                add("components", f"{path}: {match.group(1)}")

            if "export default" in content and filename not in {
                "main.tsx", "main.jsx",
            }:
                add("components", f"{path}: default export")

        # Dependencies from Python and JavaScript manifests.
        if filename == "requirements.txt":
            for line in lines:
                value = line.strip()
                if value and not value.startswith("#"):
                    add("dependencies", f"{path}: {value}")

        elif filename == "package.json":
            try:
                manifest = json.loads(content)

                for section in (
                    "dependencies", "devDependencies",
                ):
                    for name, version in manifest.get(section, {}).items():
                        add(
                            "dependencies",
                            f"{path}: {name} {version}",
                        )
            except (ValueError, AttributeError):
                pass

        elif filename in {
            "pyproject.toml", "pom.xml", "go.mod",
        }:
            for line in lines:
                value = line.strip()
                if value and not value.startswith(("#", "//")):
                    add("dependencies", f"{path}: {value}")

        # API routes and router registration.
        for line in lines:
            stripped = line.strip()

            if re.search(
                r"@\w+\.(get|post|put|patch|delete|options|head)\s*\(",
                stripped,
                re.IGNORECASE,
            ):
                add("routes", f"{path}: {stripped}")

            elif re.search(
                r"\b(?:app|router)\.(get|post|put|patch|delete|"
                r"options|head)\s*\(",
                stripped,
                re.IGNORECASE,
            ):
                add("routes", f"{path}: {stripped}")

            elif "include_router(" in stripped:
                add("routes", f"{path}: {stripped}")

         # Database indicators: implementation files only.
        implementation_file = (
            PurePosixPath(path).suffix.lower()
            in {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".go"}
        )

        if implementation_file:
            database_terms = (
                "sqlalchemy", "sqlite3", "sqlite://",
                "better-sqlite3", "pymongo", "mongodb",
                "create_engine(", "sessionmaker(",
                "db.session", "declarative_base(",
                "mapped_column(", "relationship(",
            )

            for term in database_terms:
                if term in lower_content:
                    add("database_indicators", f"{path}: {term}")

        # Security indicators.
        security_terms = (
            "argon2", "bcrypt", "jwt",
            "password_hash", "verify_password",
            "oauth", "cors", "authenticate",
            "authorization", "middleware",
            "cryptcontext", "hash_password",
        )

        for term in security_terms:
            if term in lower_content:
                add("security_indicators", f"{path}: {term}")

         # Frontend indicators.
        frontend_terms = (
            "react", "createroot", "usestate",
            "useeffect", "reactdom",
        )

        for term in frontend_terms:
            if term in lower_content:
                add("frontend_indicators", f"{path}: {term}")

        # Vanilla JavaScript application indicators.
        if PurePosixPath(path).suffix.lower() in {
            ".js", ".mjs", ".html",
        }:
            vanilla_terms = (
                "document.queryselector",
                "document.getelementbyid",
                "addeventlistener(",
                "window.onload",
                "domcontentloaded",
                "localstorage",
            )

            detected = [
                term for term in vanilla_terms
                if term in lower_content
            ]

            if detected:
                add(
                    "frontend_indicators",
                    f"{path}: Vanilla JavaScript ({', '.join(detected[:4])})",
                )

                if filename in {
                    "app.js", "script.js", "main.js", "index.js",
                }:
                    add("entry_points", path)

        # Backend indicators.
        backend_terms = (
            "fastapi", "flask", "django",
            "apirouter", "uvicorn",
        )

        for term in backend_terms:
            if term in lower_content:
                add("backend_indicators", f"{path}: {term}")

    # Keep the prompt compact.
    for key in facts:
        facts[key] = facts[key][:40]

    return facts


def _build_static_context(
    static_report: dict[str, Any],
) -> str:
    """Extract relevant static audit information."""

    return json.dumps(
        {
            "category": static_report.get("category"),
            "languages": static_report.get("languages"),
            "frameworks": static_report.get("frameworks"),
            "manifests": static_report.get("manifests"),
            "metrics": static_report.get("metrics"),
            "finding_summary": static_report.get("finding_summary"),
            "static_findings": static_report.get("findings", [])[:30],
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _call_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Send a non-streaming request to the local Ollama API."""

    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        "options": {
            "temperature": 0.1,
            "num_predict": 3000,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=OLLAMA_TIMEOUT,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as exc:
        details = exc.read().decode(
            "utf-8",
            errors="ignore",
        )

        raise RuntimeError(
            f"Ollama returned HTTP {exc.code}: {details[:500]}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not connect to Ollama: {exc.reason}"
        ) from exc

    except TimeoutError as exc:
        raise RuntimeError(
            "Ollama request timed out."
        ) from exc

    message = result.get("message", {})
    content = message.get("content", "")

    if not content:
        raise RuntimeError(
            "Ollama returned an empty response."
        )

    return content


def _parse_json(content: str) -> dict:
    """Parse JSON returned by the model."""

    content = content.strip()

    # Remove Markdown code fences if present.
    content = re.sub(
        r"^```(?:json)?\s*",
        "",
        content,
        flags=re.IGNORECASE,
    )

    content = re.sub(
        r"\s*```$",
        "",
        content,
    )

    try:
        parsed = json.loads(content)

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "The AI model returned invalid JSON."
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(
            "The AI model response must be a JSON object."
        )

    return parsed


def _normalize_quote(value: str) -> str:
    """Normalize whitespace and quotation marks for evidence comparison."""

    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = value.replace("'", '"')

    return value


def _verify_evidence(
    finding: dict,
    reviewed_files: dict[str, dict[str, Any]],
) -> dict | None:
    """Accept a finding only when its quoted evidence exists in the source."""

    evidence = finding.get("evidence")

    if not isinstance(evidence, dict):
        return None

    path = evidence.get("file")
    quote = evidence.get("quote")
    start_line = evidence.get("start_line")
    end_line = evidence.get("end_line")

    if not isinstance(path, str) or path not in reviewed_files:
        return None

    if not isinstance(quote, str) or len(quote.strip()) < 8:
        return None

    if (
        not isinstance(start_line, int)
        or not isinstance(end_line, int)
        or start_line < 1
        or end_line < start_line
    ):
        return None

    source_lines = reviewed_files[path]["content"].splitlines()

    if end_line > len(source_lines):
        return None

    actual_text = "\n".join(
        source_lines[start_line - 1:end_line]
    )

    normalized_quote = _normalize_quote(quote)
    normalized_source = _normalize_quote(actual_text)

    if normalized_quote not in normalized_source:
        return None

    return {
        "file": path,
        "start_line": start_line,
        "end_line": end_line,
        "quote": quote.strip(),
    }


def _normalize_findings(
    raw_findings: Any,
    reviewed_files: dict[str, dict[str, Any]],
) -> list[dict]:
    """Validate and normalize AI findings."""

    if not isinstance(raw_findings, list):
        return []

    findings = []

    allowed_severities = {
        "critical",
        "high",
        "medium",
        "low",
        "info",
    }

    for item in raw_findings:
        if not isinstance(item, dict):
            continue

        verified_evidence = _verify_evidence(
            item,
            reviewed_files,
        )

        # No evidence, no finding.
        if verified_evidence is None:
            continue

        severity = str(
            item.get("severity", "medium")
        ).lower()

        if severity not in allowed_severities:
            severity = "medium"

        findings.append({
            "title": str(
                item.get("title", "Unspecified issue")
            )[:200],
            "category": str(
                item.get("category", "General")
            )[:100],
            "severity": severity,
            "description": str(
                item.get("description", "")
            )[:1500],
            "recommendation": str(
                item.get("recommendation", "")
            )[:1500],
            "evidence": verified_evidence,
            "verification": "verified",
        })

    return findings


def _normalize_text_list(
    value: Any,
    limit: int = 10,
) -> list[str]:
    if not isinstance(value, list):
        return []

    result = []

    for item in value[:limit]:
        if isinstance(item, str) and item.strip():
            result.append(item.strip()[:1000])

    return result


def _architecture_fallback(facts: dict) -> dict:
    """Build architecture descriptions from extracted source facts."""

    def describe(label: str, key: str) -> str:
        items = facts.get(key, [])

        if not isinstance(items, list) or not items:
            return "Not verified from the reviewed source files."

        return label + ":\n" + "\n".join(
            f"- {item}" for item in items[:20]
        )

    frontend = facts.get("frontend_indicators", [])
    backend = facts.get("backend_indicators", [])

    overview_parts = []

    if frontend:
        overview_parts.append(
            "Frontend indicators detected: " + ", ".join(frontend[:10])
        )

    if backend:
        overview_parts.append(
            "Backend indicators detected: " + ", ".join(backend[:10])
        )

    overview = (
        "\n".join(overview_parts)
        if overview_parts
        else "Not verified from the reviewed source files."
    )

    routes = facts.get("routes", [])
    database = facts.get("database_indicators", [])

    if routes or database:
        data_flow = (
            "Observed API route declarations:\n"
            + (
                "\n".join(f"- {item}" for item in routes[:20])
                if routes else "- No route declarations detected."
            )
            + "\n\nDatabase indicators:\n"
            + (
                "\n".join(f"- {item}" for item in database[:20])
                if database else "- No database indicators detected."
            )
            + "\n\nThe end-to-end runtime data flow was not independently verified."
        )
    else:
        data_flow = "Not verified from the reviewed source files."

    return {
        "overview": overview,
        "entry_points": describe("Detected entry points", "entry_points"),
        "components": describe("Detected components", "components"),
        "data_flow": data_flow,
        "dependencies": describe("Detected dependencies", "dependencies"),
        "security": describe(
            "Detected security-related indicators",
            "security_indicators",
        ),
    }


def _normalize_architecture(
    value: Any,
    architecture_facts: dict | None = None,
) -> dict:
    """Normalize architecture review fields with fact-based fallbacks."""

    fields = [
        "overview",
        "entry_points",
        "components",
        "data_flow",
        "dependencies",
        "security",
    ]

    if not isinstance(value, dict):
        value = {}

    fallback = _architecture_fallback(
        architecture_facts or {}
    )

    result = {}

    for field in fields:
        content = value.get(field)

        if isinstance(content, list):
            content = "\n".join(str(item) for item in content)

        if (
            not isinstance(content, str)
            or not content.strip()
            or "Not verified from the reviewed source files." in content
        ):
            content = fallback[field]

        result[field] = content.strip()[:3000]

    return result


def _normalize_result(
    raw: dict,
    files: list[dict[str, Any]],
    architecture_facts: dict | None = None,
) -> dict:
    """Convert model output into the frontend's expected structure."""

    reviewed_files = {
        file["path"]: file
        for file in files
    }

    findings = _normalize_findings(
        raw.get("findings", []),
        reviewed_files,
    )

    return {
        "status": "completed",
        "summary": str(
            raw.get(
                "summary",
                "AI review completed. See the architecture review and verified findings.",
            )
        )[:3000],
"architecture_review": _normalize_architecture(
    raw.get("architecture_review"),
    architecture_facts,
),
        "strengths": _normalize_text_list(
            raw.get("strengths")
        ),
        "limitations": _normalize_text_list(
            raw.get("limitations")
        ),
        "findings": findings,
        "files_reviewed": [
            {
                "path": file["path"],
                "line_count": file["line_count"],
            }
            for file in files
        ],
        "files_reviewed_count": len(files),
        "evidence_policy": (
            "AI findings are included only when their quoted source evidence "
            "matches the reviewed file and line range."
        ),
    }


def audit_with_ai(
    archive_path: str,
    static_report: dict,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Run a local Ollama-based AI review of selected ZIP source files."""

    if not model or not isinstance(model, str):
        model = DEFAULT_MODEL

    files = _collect_source_files(archive_path)

    if not files:
        raise ValueError(
            "No eligible source files were found for AI review."
        )

    source_context = _build_source_context(files)
    static_context = _build_static_context(static_report)

    architecture_facts = _extract_architecture_facts(files)

    architecture_context = json.dumps(
        architecture_facts,
        indent=2,
        ensure_ascii=False,
    )

    system_prompt = """
You are a senior software architect and security-focused code reviewer.

You are reviewing a software project using ONLY the source files and static
audit information supplied by the user.

STRICT RULES:

1. Never claim that a feature exists unless the supplied source supports it.
2. Never invent APIs, database systems, authentication mechanisms,
   integrations, frameworks, or deployment configurations.
3. Do not assume that a project uses a technology simply because it is
   common for that type of application.
4. If information cannot be verified, explicitly say:
   "Not verified from the reviewed source files."
5. Distinguish observed implementation from recommendations.
6. Do not treat missing evidence as proof that a feature does not exist.
7. Do not claim that the entire project has been reviewed. Only selected
   files are available.
8. Report actionable issues, not generic advice.
9. Do not fabricate file paths, line numbers, or source quotations.
10. AI findings MUST contain exact evidence copied from the supplied files.
11. If you cannot provide exact evidence, do not report the finding.
12. Do not include secrets or reproduce credentials in your response.

ARCHITECTURE REVIEW:

Explain only what can be established from the supplied source.

For each architecture field, provide a concise explanation. If evidence is
insufficient, use:
"Not verified from the reviewed source files."
Use the VERIFIED ARCHITECTURE FACTS as evidence when explaining the
project architecture. Do not replace observed facts with assumptions.
Explain what each detected component does only when the source supports it.
If a section has no supporting evidence, say it is not verified.
FINDINGS:

Each finding must have:
- title
- category
- severity
- description
- recommendation
- evidence

The evidence object must contain:
- file: exact supplied file path
- start_line: exact 1-based source line number
- end_line: exact 1-based source line number
- quote: exact source text from that line range

Use only these severity values:
critical, high, medium, low, info.

Return ONLY valid JSON. Do not use Markdown fences.

Required JSON structure:

{
  "summary": "Executive summary",
  "architecture_review": {
    "overview": "Verified project overview",
    "entry_points": "Verified entry points",
    "components": "Verified components",
    "data_flow": "Verified data flow",
    "dependencies": "Verified dependencies",
    "security": "Verified security observations"
  },
  "strengths": [
    "Evidence-supported strength"
  ],
  "limitations": [
    "Evidence-supported limitation or review limitation"
  ],
  "findings": [
    {
      "title": "Issue title",
      "category": "Security, Architecture, Code Quality, Performance, or Reliability",
      "severity": "medium",
      "description": "Explain the issue",
      "recommendation": "Explain how to fix it",
      "evidence": {
        "file": "exact/file/path",
        "start_line": 1,
        "end_line": 2,
        "quote": "Exact source text"
      }
    }
  ]
}
"""

    user_prompt = f"""
Review this software project.

STATIC AUDIT INFORMATION:
{static_context}
VERIFIED ARCHITECTURE FACTS EXTRACTED FROM SOURCE:

{architecture_context}

REVIEWED SOURCE FILES:

{source_context}

TASKS:

1. Write a concise executive summary.
2. Explain the architecture using only verifiable evidence.
3. Identify genuine strengths visible in the source.
4. Identify limitations that can be established from the source.
5. Find actionable security, architecture, code-quality, performance,
   and reliability issues.
6. Every finding must include exact source evidence with correct line numbers.
7. Do not create findings based on assumptions.
8. If no issue can be verified, return an empty findings array.
9. Clearly distinguish limitations of this review from confirmed project defects.

Return the required JSON object only.
"""

    response = _call_ollama(
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    parsed = _parse_json(response)

    return _normalize_result(
        raw=parsed,
        files=files,
        architecture_facts=architecture_facts,
    )