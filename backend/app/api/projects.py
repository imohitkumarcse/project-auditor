
from pydantic import BaseModel, Field
from app.services.ai_auditor import audit_with_ai, DEFAULT_MODEL

import json
import re
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.services.zip_analyzer import analyze_archive
from app.services.static_auditor import audit_archive


router = APIRouter(prefix="/api/projects", tags=["Projects"])

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"

MAX_FILE_SIZE = 100 * 1024 * 1024
MAX_FILES = 10
CHUNK_SIZE = 1024 * 1024
class AIAuditRequest(BaseModel):
    model: str = Field(
        default=DEFAULT_MODEL,
        min_length=1,
        max_length=100
    )


def safe_filename(filename: str) -> str:
    name = Path(filename or "project.zip").name
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:120] or "project.zip"


def read_report(project_dir: Path):
    report_path = project_dir / "report.json"

    if not report_path.exists():
        return None

    try:
        with report_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return None


@router.post("/upload")
async def upload_projects(files: list[UploadFile] = File(...)):

    if not files:
        raise HTTPException(
            status_code=400,
            detail="No files uploaded",
        )

    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 ZIP files per batch",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    for uploaded_file in files:
        filename = safe_filename(uploaded_file.filename)

        if not filename.lower().endswith(".zip"):
            results.append({
                "filename": filename,
                "status": "rejected",
                "error": "Only ZIP files are supported",
            })
            await uploaded_file.close()
            continue

        project_id = str(uuid.uuid4())
        project_dir = UPLOAD_DIR / project_id
        project_dir.mkdir(parents=True, exist_ok=False)

        destination = project_dir / filename
        size = 0

        try:
            # Save uploaded ZIP in chunks with a size limit.
            with destination.open("wb") as output:
                while True:
                    chunk = await uploaded_file.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    size += len(chunk)

                    if size > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{filename} exceeds 100 MB limit",
                        )

                    output.write(chunk)

            # Validate ZIP archive.
            if not zipfile.is_zipfile(destination):
                results.append({
                    "filename": filename,
                    "status": "rejected",
                    "error": "Invalid ZIP archive",
                })
                continue

            # Analyze ZIP structure and technology stack.
            analysis = analyze_archive(destination)

            if analysis.get("status") == "rejected":
                results.append({
                    "filename": filename,
                    **analysis,
                })
                continue

            # Run static code and security audit.
            audit = audit_archive(destination)

            analysis.update(audit)

            # Create persistent project report.
            report = {
                "project_id": project_id,
                "filename": filename,
                "file_size_bytes": size,
                **analysis,
            }

            report_path = project_dir / "report.json"

            with report_path.open("w", encoding="utf-8") as file:
                json.dump(
                    report,
                    file,
                    indent=4,
                    ensure_ascii=False,
                )

            results.append(report)

        except HTTPException:
            # Remove incomplete upload before returning an error.
            if project_dir.exists():
                import shutil
                shutil.rmtree(project_dir, ignore_errors=True)
            raise

        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
            if project_dir.exists():
                import shutil
                shutil.rmtree(project_dir, ignore_errors=True)

            results.append({
                "filename": filename,
                "status": "rejected",
                "error": str(error),
            })

        finally:
            await uploaded_file.close()

    return {
        "total_uploaded": len(files),
        "total_analyzed": sum(
            result.get("status") == "analyzed"
            for result in results
        ),
        "total_rejected": sum(
            result.get("status") == "rejected"
            for result in results
        ),
        "results": results,
    }


@router.get("/")
def list_projects():

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    projects = []

    for project_dir in UPLOAD_DIR.iterdir():

        if not project_dir.is_dir():
            continue

        report = read_report(project_dir)

        if report:
            projects.append({
                "project_id": report.get("project_id"),
                "filename": report.get("filename"),
                "status": report.get("status"),
                "audit_status": report.get("audit_status"),
                "audit_score": report.get("audit_score"),
                "category": report.get("category"),
                "languages": report.get("languages", {}),
                "frameworks": report.get("frameworks", []),
            })

    projects.sort(
        key=lambda item: item.get("filename") or ""
    )

    return {
        "total_projects": len(projects),
        "projects": projects,
    }


@router.get("/{project_id}/report")
def get_project_report(project_id: str):

    if not re.fullmatch(r"[a-fA-F0-9-]{36}", project_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID",
        )

    project_dir = UPLOAD_DIR / project_id

    if not project_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    report = read_report(project_dir)

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Report not found",
        )

    return report


@router.get("/{project_id}")
def get_project(project_id: str):

    if not re.fullmatch(r"[a-fA-F0-9-]{36}", project_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID",
        )

    project_dir = UPLOAD_DIR / project_id

    if not project_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    report = read_report(project_dir)

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Project report not found",
        )

    return {
        "project": report,
        "storage_directory": str(project_dir),
    }

@router.post("/{project_id}/ai-audit")
def run_ai_audit(
    project_id: str,
    request: AIAuditRequest
):
    if not re.fullmatch(r"[a-fA-F0-9-]{36}", project_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID"
        )

    project_dir = UPLOAD_DIR / project_id

    if not project_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    report = read_report(project_dir)

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Project report not found"
        )

    filename = report.get("filename", "")

    # Use the stored report filename, not a user-supplied path.
    archive_path = project_dir / filename

    if not archive_path.is_file() or not zipfile.is_zipfile(archive_path):
        raise HTTPException(
            status_code=404,
            detail="Project ZIP archive not found"
        )

    try:
        ai_result = audit_with_ai(
            archive_path=archive_path,
            static_report=report,
            model=request.model
        )

        report["ai_audit"] = ai_result
        report["ai_audit_status"] = ai_result["status"]

        report_path = project_dir / "report.json"

        with report_path.open("w", encoding="utf-8") as file:
            json.dump(
                report,
                file,
                indent=4,
                ensure_ascii=False
            )

        return {
            "project_id": project_id,
            "filename": filename,
            "ai_audit": ai_result
        }

    except urllib.error.URLError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to local Ollama runtime"
        )

    except (ValueError, RuntimeError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"AI audit failed: {error}"
        )
import urllib.error