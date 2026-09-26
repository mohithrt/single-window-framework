"""Canonical document categories shared by pre-validation and requirements."""

DOCUMENT_LABELS = {
    "PAN": "PAN",
    "GST_CERTIFICATE": "GST certificate",
    "UDYAM_CERTIFICATE": "Udyam certificate",
    "INCORPORATION_CERTIFICATE": "Incorporation certificate",
    "LAND_OWNERSHIP_LEASE": "Land ownership / lease documents",
    "BUILDING_PLAN": "Building plan",
    "PROJECT_REPORT": "Project report",
    "ENVIRONMENTAL_DOCUMENTS": "Environmental documents",
    "FIRE_SAFETY_DOCUMENTS": "Fire safety documents",
    "FACTORY_DOCUMENTS": "Factory documents",
    "IDENTITY_DOCUMENT": "Identity documents",
    "OTHER_SUPPORTING": "Other supporting documents",
}

# These are the existing prototype's general submission documents, with
# department-specific environmental/fire/factory documents resolved from the
# configured approval catalog instead of being universally required.
BASE_MANDATORY_DOCUMENTS = {
    "PAN", "LAND_OWNERSHIP_LEASE", "BUILDING_PLAN", "PROJECT_REPORT", "IDENTITY_DOCUMENT",
}
