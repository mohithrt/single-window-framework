export const APPLICATION_STEPS = [
  'Applicant',
  'Company',
  'Project',
  'Location',
  'Industry',
  'Documents',
  'Review',
  'Submit',
] as const

export const INDUSTRIES = [
  'IT / Software',
  'Manufacturing',
  'Food Processing',
  'Textile',
  'Chemical',
  'Pharmaceutical',
  'Automobile',
  'Electronics',
  'Logistics',
  'Other',
] as const

export const POLLUTION_CATEGORIES = ['White', 'Green', 'Orange', 'Red', 'Not sure'] as const

export const DOCUMENT_TYPES = [
  ['PAN', 'PAN'],
  ['GST_CERTIFICATE', 'GST certificate'],
  ['UDYAM_CERTIFICATE', 'Udyam certificate'],
  ['INCORPORATION_CERTIFICATE', 'Incorporation certificate'],
  ['LAND_OWNERSHIP_LEASE', 'Land ownership / lease documents'],
  ['BUILDING_PLAN', 'Building plan'],
  ['PROJECT_REPORT', 'Project report'],
  ['ENVIRONMENTAL_DOCUMENTS', 'Environmental documents'],
  ['FIRE_SAFETY_DOCUMENTS', 'Fire safety documents'],
  ['FACTORY_DOCUMENTS', 'Factory documents'],
  ['IDENTITY_DOCUMENT', 'Identity documents'],
  ['OTHER_SUPPORTING', 'Other supporting documents'],
] as const

export type ApplicationDocument = {
  id: number
  document_type: string
  file_name: string
  media_type: string
  size_bytes: number
  status: 'PROCESSING' | 'VALID' | 'WARNING' | 'INVALID' | 'MISSING'
  processed_at: string | null
  uploaded_at: string
}

export type ValidationIssue = {
  id: number
  document_id: number | null
  document_type: string
  document_label: string
  code: string
  status: 'VALID' | 'WARNING' | 'INVALID' | 'MISSING'
  message: string
  detected_value: string | null
  expected_value: string | null
}

export type PrevalidationResult = {
  application_id: number
  application_number: string
  overall_status: 'VALID' | 'WARNING' | 'INVALID' | 'MISSING'
  counts: Record<'VALID' | 'WARNING' | 'INVALID' | 'MISSING', number>
  can_submit: boolean
  documents: Array<{
    document_type: string
    document_label: string
    status: 'VALID' | 'WARNING' | 'INVALID' | 'MISSING'
    required: boolean
    documents: Array<{ id: number; file_name: string; status: string }>
    issues: ValidationIssue[]
  }>
  issues: ValidationIssue[]
  checked_at: string
}

export type RiskFactor = {
  key: string
  label: string
  value: string
  points: number
  explanation: string
  signals: string[]
}

export type RiskAssessment = {
  id: number
  application_id: number
  risk_score: number
  raw_score: number
  risk_tier: 'LOW' | 'MEDIUM' | 'HIGH'
  rules_version: string
  positive_factors: RiskFactor[]
  low_risk_factors: RiskFactor[]
  factor_breakdown: RiskFactor[]
  explanation: string[]
  created_at: string
  is_stale: boolean
}

export type RiskResponse = {
  assessment: RiskAssessment | null
  is_stale: boolean
}

export type ApplicationRecord = {
  id: number
  application_number: string
  company_id: number | null
  applicant_name: string | null
  applicant_email: string | null
  applicant_phone: string | null
  company_name: string | null
  pan: string | null
  gstin: string | null
  cin: string | null
  udyam_number: string | null
  industry_type: string | null
  other_industry_name: string | null
  project_type: string | null
  project_description: string | null
  investment_amount: number | string | null
  number_of_employees: number | null
  built_up_area: number | string | null
  power_requirement: number | string | null
  water_requirement: number | string | null
  project_location: string | null
  land_details: string | null
  midc_area: boolean | null
  midc_area_name: string | null
  pollution_category: string | null
  hazardous_materials: boolean | null
  hazardous_materials_details: string | null
  factory_information: string | null
  fire_safety_information: string | null
  risk_tier: string | null
  status: 'DRAFT' | 'SUBMITTED' | 'IN_REVIEW' | 'ACTION_REQUIRED' | 'APPROVED' | 'REJECTED'
  progress_percent: number
  expected_completion_at: string | null
  current_department_name: string | null
  created_at: string
  updated_at: string
  submitted_at: string | null
  documents: ApplicationDocument[]
}

export type ApplicationsResponse = {
  summary: {
    total_applications: number
    pending: number
    approved: number
    rejected: number
    action_required: number
  }
  applications: ApplicationRecord[]
}

export type ApplicationFormValues = {
  applicant_name: string
  applicant_email: string
  applicant_phone: string
  company_name: string
  pan: string
  gstin: string
  cin: string
  udyam_number: string
  industry_type: string
  other_industry_name: string
  project_type: string
  project_description: string
  investment_amount: string
  number_of_employees: string
  built_up_area: string
  power_requirement: string
  water_requirement: string
  project_location: string
  land_details: string
  midc_area: boolean | null
  midc_area_name: string
  pollution_category: string
  hazardous_materials: boolean | null
  hazardous_materials_details: string
  factory_information: string
  fire_safety_information: string
}

export const blankApplication: ApplicationFormValues = {
  applicant_name: '', applicant_email: '', applicant_phone: '',
  company_name: '', pan: '', gstin: '', cin: '', udyam_number: '',
  industry_type: '', other_industry_name: '', project_type: '', project_description: '',
  investment_amount: '', number_of_employees: '', built_up_area: '',
  power_requirement: '', water_requirement: '', project_location: '', land_details: '',
  midc_area: null, midc_area_name: '', pollution_category: '', hazardous_materials: null,
  hazardous_materials_details: '', factory_information: '', fire_safety_information: '',
}

const numericFields = new Set([
  'investment_amount', 'number_of_employees', 'built_up_area', 'power_requirement', 'water_requirement',
])
const booleanFields = new Set(['midc_area', 'hazardous_materials'])

export function applicationToForm(application: ApplicationRecord): ApplicationFormValues {
  const result: Record<string, string | boolean | null> = { ...blankApplication }
  for (const key of Object.keys(result) as (keyof ApplicationFormValues)[]) {
    const value = application[key as keyof ApplicationRecord]
    if (booleanFields.has(key)) {
      result[key] = (value as boolean | null) ?? null
    } else {
      result[key] = value == null ? '' : String(value)
    }
  }
  return result as unknown as ApplicationFormValues
}

export function formToDraft(values: ApplicationFormValues): Record<string, unknown> {
  const draft: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(values)) {
    if (numericFields.has(key)) {
      draft[key] = value === '' ? null : Number(value)
    } else {
      draft[key] = value === '' ? null : value
    }
  }
  return draft
}

export function formatDate(value: string | null): string {
  if (!value) return 'Not scheduled'
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value))
}

export function statusLabel(status: ApplicationRecord['status']): string {
  return ({
    DRAFT: 'Draft',
    SUBMITTED: 'Pending',
    IN_REVIEW: 'In review',
    ACTION_REQUIRED: 'Action required',
    APPROVED: 'Approved',
    REJECTED: 'Rejected',
  })[status]
}
