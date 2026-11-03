import json
import zipfile
from pathlib import Path, PurePosixPath
from collections import Counter

MAX_ENTRIES = 20000
MAX_UNCOMPRESSED_SIZE = 500 * 1024 * 1024
MAX_MANIFEST_SIZE = 256 * 1024

MANIFESTS = {
    "package.json", "requirements.txt", "pyproject.toml",
    "setup.py", "cargo.toml", "go.mod", "pom.xml",
    "build.gradle", "build.gradle.kts", "platformio.ini",
    "composer.json",
}

EXTENSION_LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".html": "HTML",
    ".css": "CSS",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++",
    ".java": "Java",
    ".rs": "Rust",
    ".go": "Go",
    ".php": "PHP",
    ".rb": "Ruby",
    ".cs": "C#",
    ".ino": "Arduino",
    ".sql": "SQL",
    ".ipynb": "Jupyter Notebook",
}

SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv",
    "__pycache__", "dist", "build",
}


def safe_member_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and not normalized.startswith("/")
        and "\x00" not in normalized
    )


def detect_frameworks(manifests: dict) -> set:
    frameworks = set()
    package = manifests.get("package.json", {})
    dependencies = {}

    if isinstance(package, dict):
        dependencies.update(package.get("dependencies", {}))
        dependencies.update(package.get("devDependencies", {}))

    for dependency, framework in {
        "react": "React",
        "next": "Next.js",
        "vite": "Vite",
        "express": "Express",
        "vue": "Vue",
        "@angular/core": "Angular",
    }.items():
        if dependency in dependencies:
            frameworks.add(framework)

    python_text = (
        str(manifests.get("requirements.txt", ""))
        + " "
        + str(manifests.get("pyproject.toml", ""))
        + " "
        + str(manifests.get("setup.py", ""))
    ).lower()

    for package_name, framework in {
        "fastapi": "FastAPI",
        "django": "Django",
        "flask": "Flask",
        "streamlit": "Streamlit",
        "torch": "PyTorch",
        "transformers": "Hugging Face Transformers",
        "langchain": "LangChain",
        "chromadb": "ChromaDB",
    }.items():
        if package_name in python_text:
            frameworks.add(framework)

    return frameworks


def analyze_archive(archive_path: Path) -> dict:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()

            if len(entries) > MAX_ENTRIES:
                return {"status": "rejected", "error": "Too many ZIP entries"}

            total_size = sum(entry.file_size for entry in entries)

            if total_size > MAX_UNCOMPRESSED_SIZE:
                return {
                    "status": "rejected",
                    "error": "Uncompressed size exceeds limit",
                }

            languages = Counter()
            manifest_data = {}
            suspicious_entries = []
            project_roots = set()
            valid_files = 0

            for entry in entries:
                if entry.is_dir():
                    continue

                if not safe_member_name(entry.filename):
                    suspicious_entries.append(entry.filename[:200])
                    continue

                parts = PurePosixPath(entry.filename).parts

                if any(part.lower() in SKIP_DIRS for part in parts):
                    continue

                # Ignore symbolic links.
                mode = entry.external_attr >> 16
                if mode & 0o170000 == 0o120000:
                    suspicious_entries.append(entry.filename[:200])
                    continue

                valid_files += 1
                relative_path = PurePosixPath(entry.filename)
                suffix = relative_path.suffix.lower()

                if suffix in EXTENSION_LANGUAGES:
                    languages[EXTENSION_LANGUAGES[suffix]] += 1

                basename = relative_path.name.lower()

                if basename in MANIFESTS:
                    parent = str(relative_path.parent)
                    project_roots.add("." if parent == "." else parent)

                    if entry.file_size <= MAX_MANIFEST_SIZE:
                        try:
                            content = archive.read(entry).decode(
                                "utf-8", errors="replace"
                            )

                            if basename == "package.json":
                                manifest_data[basename] = json.loads(content)
                            else:
                                manifest_data[basename] = content

                        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
                            manifest_data[basename] = {}

            frameworks = detect_frameworks(manifest_data)

            if frameworks.intersection({
                "PyTorch", "Hugging Face Transformers",
                "LangChain", "ChromaDB",
            }):
                category = "AI / ML"
            elif frameworks.intersection({"React", "Next.js", "Vue", "Angular"}):
                category = "Web Application"
            elif frameworks.intersection({
                "FastAPI", "Django", "Flask", "Express",
            }):
                category = "Backend / API"
            elif "Arduino" in languages:
                category = "IoT / Embedded"
            elif languages:
                category = "Software Development"
            else:
                category = "Unknown"

            return {
                "status": "analyzed",
                "file_count": valid_files,
                "uncompressed_size_bytes": total_size,
                "languages": dict(languages.most_common()),
                "frameworks": sorted(frameworks),
                "manifests": sorted(manifest_data.keys()),
                "project_roots": sorted(project_roots),
                "category": category,
                "suspicious_entries": suspicious_entries,
                "execution_performed": False,
            }

    except (zipfile.BadZipFile, OSError, RuntimeError):
        return {
            "status": "rejected",
            "error": "Invalid, corrupted or unreadable ZIP archive",
        }
