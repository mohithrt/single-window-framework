from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from . import validate

router = APIRouter(prefix="/document-validator", tags=["Document Pre-Validator"])


@router.post("/validate")
async def validate_document(
    file: UploadFile = File(...),
    doc_type: str = Form("generic"),
):
    
    file_bytes = await file.read()

    try:
        text = validate.extract_text(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not process file: {e}")

    return validate.check_document(text, doc_type)
