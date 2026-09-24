from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from . import validate

router = APIRouter(prefix="/document-validator", tags=["Document Pre-Validator"])

MAX_FILE_SIZE_MB = 10
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}


@router.post("/validate")
async def validate_document(
    file: UploadFile = File(...),
    doc_type: str = Form("generic"),
):
    """
    Upload a document (PDF, PNG, or JPG) and a doc_type
    (e.g. "gst_certificate", "pan_card", "food_license", "generic").
    Returns whether it passes basic checks, and why not if it fails.
    """
    # --- Validate file extension up front, before doing any work ---
    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Please upload a PDF, PNG, or JPG.",
        )

    file_bytes = await file.read()

    # --- Validate file size ---
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"File is {size_mb:.1f}MB, which exceeds the {MAX_FILE_SIZE_MB}MB limit.",
        )

    if size_mb == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    # --- Validate doc_type is one we recognise (helps catch typos) ---
    if doc_type not in validate.DOC_TYPE_RULES:
        valid_types = ", ".join(validate.DOC_TYPE_RULES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown doc_type '{doc_type}'. Valid options: {valid_types}",
        )

    # --- Extract text and run checks ---
    try:
        text = validate.extract_text(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not process this file — it may be corrupted, password "
                f"protected, or in an unexpected format. ({e})"
            ),
        )

    return validate.check_document(text, doc_type)
