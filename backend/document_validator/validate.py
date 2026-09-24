import io
import re

import fitz  # PyMuPDF
import pytesseract
from PIL import Image


# --- Text extraction ---------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> str:
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text.strip()


def extract_text_from_image(file_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image).strip()


def ocr_scanned_pdf(file_bytes: bytes) -> str:
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            text += pytesseract.image_to_string(image)
    return text.strip()


def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]

    if ext == "pdf":
        text = extract_text_from_pdf(file_bytes)
        if len(text) < 20:
            text = ocr_scanned_pdf(file_bytes)
        return text

    elif ext in ("png", "jpg", "jpeg"):
        return extract_text_from_image(file_bytes)

    else:
        raise ValueError(f"Unsupported file type: .{ext}")


# --- Rule checks ---------------------------------------------------------

GST_PATTERN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1}\b")
PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]{1}\b")
UDYAM_PATTERN = re.compile(r"\bUDYAM-[A-Z]{2}-\d{2}-\d{7}\b")
CIN_PATTERN = re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b")
FSSAI_PATTERN = re.compile(r"\b\d{14}\b")

DOC_TYPE_RULES = {
    "gst_certificate": {
        "patterns": [("GSTIN", GST_PATTERN)],
        "keywords": [],
    },
    "pan_card": {
        "patterns": [("PAN number", PAN_PATTERN)],
        "keywords": [],
    },
    "udyam_registration": {
        "patterns": [("Udyam Registration Number", UDYAM_PATTERN)],
        "keywords": ["udyam"],
    },
    "mca21_incorporation": {
        "patterns": [("CIN (Corporate Identification Number)", CIN_PATTERN)],
        "keywords": [],
    },
    "food_license": {
        "patterns": [("14-digit FSSAI license number", FSSAI_PATTERN)],
        "keywords": ["food safety and standards authority", "fssai"],
    },
    "mpcb_consent": {
        "patterns": [],
        "keywords": [
            "maharashtra pollution control board",
            "consent to operate",
            "consent to establish",
        ],
    },
    "midc_allotment": {
        "patterns": [],
        "keywords": [
            "maharashtra industrial development corporation",
            "midc",
        ],
    },
    "dish_factory_license": {
        "patterns": [],
        "keywords": [
            "directorate of industrial safety and health",
            "factory license",
            "factories act",
        ],
    },
    "fire_noc": {
        "patterns": [],
        "keywords": [
            "no objection certificate",
            "directorate of maharashtra fire services",
            "fire noc",
        ],
    },
    "generic": {
        "patterns": [],
        "keywords": [],
    },
}


def check_document(text: str, doc_type: str) -> dict:
    
    issues = []
    lower_text = text.lower()

    if len(text) < 20:
        issues.append("Document appears blank or unreadable")

    rules = DOC_TYPE_RULES.get(doc_type, {"patterns": [], "keywords": []})

    for label, pattern in rules["patterns"]:
        if not pattern.search(text):
            issues.append(f"No valid {label} found in document")

    keywords = rules["keywords"]
    if keywords and not any(kw in lower_text for kw in keywords):
        readable_type = doc_type.replace("_", " ")
        issues.append(
            f"Document does not appear to be a valid {readable_type} "
            f"(none of the expected phrases were found)"
        )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "extracted_text_preview": text[:300],
    }