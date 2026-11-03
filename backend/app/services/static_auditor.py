import re
import zipfile

from collections import Counter
from pathlib import PurePosixPath


MAX_FILE_SIZE = 1 * 1024 * 1024
MAX_TOTAL_SCAN_SIZE = 20 * 1024 * 1024

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
}

SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".java", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".go", ".rs",
    ".php", ".rb", ".sql",
}

TEXT_EXTENSIONS = SOURCE_EXTENSIONS | {
    ".json", ".md", ".txt", ".yml", ".yaml",
    ".toml", ".ini", ".xml", ".sh", ".bat",
}

SECRET_PATTERNS = {
    "private_key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "api_key": re.compile(
        r"""(?i)(?:api[_-]?key|access[_-]?token)\s*[:=]\s*["'][^"']{12,}["']"""
    ),
"hardcoded_password": re.compile(
    r"""(?i)(?:password|passwd|secret)\s*[:=]\s*["'](?!.*(?:getpass|input)\s*\()[^"']{4,}["']"""
),
}


def safe_path(name: str) -> bool:
    """Reject unsafe paths and files inside dependency/build directories."""
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)

    if path.is_absolute():
        return False

    if ".." in path.parts:
        return False

    if any(part.lower() in SKIP_DIRS for part in path.parts):
        return False

    return True


def _finding(
    finding_type: str,
    severity: str,
    title: str,
    description: str,
    file: str | None = None,
) -> dict:
    result = {
        "type": finding_type,
        "severity": severity,
        "title": title,
        "description": description,
    }

    if file:
        result["file"] = file

    return result


def audit_archive(archive_path: str) -> dict:
    """Perform a read-only static audit of a ZIP archive."""

    findings = []

    metrics = {
        "total_files": 0,
        "source_files": 0,
        "text_files_scanned": 0,
        "empty_files": 0,
        "large_files": 0,
        "todo_count": 0,
        "fixme_count": 0,
        "files_skipped": 0,
        "scanned_size_bytes": 0,
    }

    extensions = Counter()

    has_readme = False
    has_manifest = False
    has_lockfile = False
    has_tests = False

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            entries = archive.infolist()

            if len(entries) > 20_000:
                findings.append(
                    _finding(
                        "archive_limit",
                        "medium",
                        "Archive entry limit exceeded",
                        "The archive contains more than 20,000 entries. "
                        "Only the first 20,000 entries were inspected.",
                    )
                )
                entries = entries[:20_000]

            metrics["total_files"] = len(entries)

            for info in entries:
                if info.is_dir():
                    continue

                if not safe_path(info.filename):
                    metrics["files_skipped"] += 1
                    continue

                path = PurePosixPath(
                    info.filename.replace("\\", "/")
                )

                filename = path.name.lower()
                extension = path.suffix.lower()

                extensions[extension or "[no extension]"] += 1

                # Detect project documentation.
                if filename in {"readme", "readme.md", "readme.txt"}:
                    has_readme = True

                # Detect common dependency manifests.
                if filename in {
                    "package.json",
                    "requirements.txt",
                    "pyproject.toml",
                    "pom.xml",
                    "build.gradle",
                    "cargo.toml",
                    "composer.json",
                    "go.mod",
                    "gemfile",
                }:
                    has_manifest = True

                # Detect dependency lockfiles.
                if filename in {
                    "package-lock.json",
                    "pnpm-lock.yaml",
                    "yarn.lock",
                    "poetry.lock",
                    "pipfile.lock",
                    "cargo.lock",
                    "composer.lock",
                    "gemfile.lock",
                }:
                    has_lockfile = True

                # Detect likely test files.
                if (
                    filename.startswith("test_")
                    or filename.endswith("_test.py")
                    or ".test." in filename
                    or ".spec." in filename
                    or "tests" in [part.lower() for part in path.parts]
                ):
                    has_tests = True

                # Environment files can contain credentials.
                if filename in {".env", ".env.local", ".env.production"}:
                    findings.append(
                        _finding(
                            "environment_file",
                            "high",
                            "Environment file included",
                            "An environment file is present in the archive. "
                            "Check it for passwords, tokens, and other secrets.",
                            info.filename,
                        )
                    )

                # Empty-file handling.
                if info.file_size == 0:
                    # Common intentional placeholders.
                    if filename in {".gitkeep", "__init__.py"}:
                        continue

                    metrics["empty_files"] += 1

                    findings.append(
                        _finding(
                            "empty_file",
                            "info",
                            "Empty file detected",
                            "This file contains no content. Confirm that it is intentional.",
                            info.filename,
                        )
                    )
                    continue

                # Large files are not read.
                if info.file_size > MAX_FILE_SIZE:
                    metrics["large_files"] += 1
                    metrics["files_skipped"] += 1

                    findings.append(
                        _finding(
                            "large_file",
                            "info",
                            "Large file skipped",
                            f"The file is larger than the {MAX_FILE_SIZE // 1024} KB "
                            "per-file scanning limit.",
                            info.filename,
                        )
                    )
                    continue

                if extension not in TEXT_EXTENSIONS:
                    continue

                # Total content scanning limit.
                if (
                    metrics["scanned_size_bytes"] + info.file_size
                    > MAX_TOTAL_SCAN_SIZE
                ):
                    metrics["files_skipped"] += 1
                    continue

                try:
                    raw_content = archive.read(info)
                    content = raw_content.decode(
                        "utf-8",
                        errors="ignore",
                    )

                except (OSError, RuntimeError, zipfile.BadZipFile):
                    metrics["files_skipped"] += 1
                    continue

                metrics["scanned_size_bytes"] += len(raw_content)
                metrics["text_files_scanned"] += 1

                if extension in SOURCE_EXTENSIONS:
                    metrics["source_files"] += 1

                # TODO/FIXME analysis.
                todo_matches = re.findall(
                    r"\bTODO\b",
                    content,
                    flags=re.IGNORECASE,
                )

                fixme_matches = re.findall(
                    r"\bFIXME\b",
                    content,
                    flags=re.IGNORECASE,
                )

                metrics["todo_count"] += len(todo_matches)
                metrics["fixme_count"] += len(fixme_matches)

                # Secret pattern checks.
                for secret_type, pattern in SECRET_PATTERNS.items():
                    matches = pattern.finditer(content)

                    for match in matches:
                        findings.append(
                            _finding(
                                "possible_secret",
                                "high",
                                "Possible hardcoded secret",
                                f"A pattern resembling {secret_type.replace('_', ' ')} "
                                "was detected. Verify it manually and rotate it if genuine.",
                                info.filename,
                            )
                        )

            # Project completeness checks.
            if not has_readme:
                findings.append(
                    _finding(
                        "missing_readme",
                        "medium",
                        "README file missing",
                        "No README file was detected. Add documentation describing "
                        "the project, setup instructions, and usage.",
                    )
                )

            if metrics["source_files"] > 0 and not has_tests:
                findings.append(
                    _finding(
                        "missing_tests",
                        "medium",
                        "Test files not detected",
                        "No recognizable test files or test directory were detected.",
                    )
                )

            if has_manifest and not has_lockfile:
                findings.append(
                    _finding(
                        "missing_lockfile",
                        "low",
                        "Dependency lockfile missing",
                        "A dependency manifest was detected, but no recognized "
                        "lockfile was found.",
                    )
                )

        # Count findings by severity.
        severity_counts = Counter(
            item["severity"] for item in findings
        )

        # Security score only considers security-related findings.
        security_findings = [
            item
            for item in findings
            if item["type"] in {
                "possible_secret",
                "environment_file",
            }
        ]

        security_counts = Counter(
            item["severity"] for item in security_findings
        )

        security_penalty = (
            security_counts["high"] * 15
            + security_counts["medium"] * 5
        )

        # Code-quality score.
        quality_penalty = (
            metrics["todo_count"] * 1
            + metrics["fixme_count"] * 2
            + metrics["empty_files"] * 1
            + metrics["large_files"] * 1
        )

        # Completeness score.
        completeness_penalty = (
            (15 if not has_readme else 0)
            + (
                10
                if metrics["source_files"] > 0 and not has_tests
                else 0
            )
            + (5 if has_manifest and not has_lockfile else 0)
        )

        scores = {
            "security": max(0, 100 - security_penalty),
            "code_quality": max(0, 100 - quality_penalty),
            "completeness": max(0, 100 - completeness_penalty),
        }

        overall_score = round(
            scores["security"] * 0.4
            + scores["code_quality"] * 0.3
            + scores["completeness"] * 0.3
        )

        return {
            "audit_status": "completed",
            "audit_score": overall_score,
            "scores": scores,
            "metrics": metrics,
            "file_extensions": dict(extensions.most_common()),
            "finding_summary": {
                "total": len(findings),
                "critical": severity_counts["critical"],
                "high": severity_counts["high"],
                "medium": severity_counts["medium"],
                "low": severity_counts["low"],
                "info": severity_counts["info"],
            },
            "findings": findings,
            "scan_limits": {
                "max_file_size_bytes": MAX_FILE_SIZE,
                "max_total_scan_size_bytes": MAX_TOTAL_SCAN_SIZE,
                "max_archive_entries": 20_000,
            },
            "execution_performed": False,
        }

    except zipfile.BadZipFile:
        return {
            "audit_status": "failed",
            "error": "Invalid or corrupted ZIP archive.",
            "execution_performed": False,
        }

    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "audit_status": "failed",
            "error": str(exc),
            "execution_performed": False,
        }