from app.application_schemas import ApplicationSubmission
from app.models import Application, ApplicationStatus, IndustryType


def submission_errors(application: Application, document_count: int) -> list[str]:
    data = {field: getattr(application, field) for field in ApplicationSubmission.model_fields}
    try:
        ApplicationSubmission.model_validate(data)
        errors: list[str] = []
    except ValueError as exc:
        errors = [".".join(str(part) for part in item["loc"]) for item in exc.errors()]
    if document_count == 0:
        errors.append("documents")
    return sorted(set(errors))


def application_progress(application: Application, document_count: int) -> int:
    applicant_complete = all(
        bool(value and str(value).strip())
        for value in (application.applicant_name, application.applicant_email, application.applicant_phone)
    )
    company_complete = bool(application.company_name and application.company_name.strip() and application.pan)
    project_complete = all(
        value is not None and (not isinstance(value, str) or bool(value.strip()))
        for value in (
            application.project_type,
            application.project_description,
            application.investment_amount,
            application.number_of_employees,
            application.built_up_area,
            application.power_requirement,
            application.water_requirement,
        )
    )
    location_complete = bool(
        application.project_location
        and application.project_location.strip()
        and application.land_details
        and application.land_details.strip()
        and application.midc_area is not None
        and (not application.midc_area or bool(application.midc_area_name and application.midc_area_name.strip()))
    )
    industry_complete = bool(
        application.industry_type
        and (application.industry_type != IndustryType.OTHER.value or application.other_industry_name)
        and application.pollution_category
        and application.hazardous_materials is not None
        and (not application.hazardous_materials or application.hazardous_materials_details)
        and application.factory_information
        and application.fire_safety_information
    )
    documents_complete = document_count > 0
    review_complete = not submission_errors(application, document_count)
    submitted = application.status != ApplicationStatus.DRAFT.value
    return round(sum((applicant_complete, company_complete, project_complete, location_complete,
                      industry_complete, documents_complete, review_complete, submitted)) * 100 / 8)
