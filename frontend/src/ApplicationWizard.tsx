import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, FormEvent, ReactNode } from 'react'
import {
  APPLICATION_STEPS,
  blankApplication,
  applicationToForm,
  formToDraft,
  type ApplicationDocument,
  type ApplicationFormValues,
  type ApplicationRecord,
} from './applicationTypes'
import { DOCUMENT_TYPES, INDUSTRIES, POLLUTION_CATEGORIES } from './applicationTypes'

type Props = { applicationId: number; readOnly: boolean }
type FieldErrors = Record<string, string>

async function errorMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}))
  if (typeof body.detail === 'string') return body.detail
  if (body.detail?.message) {
    const fields: string[] = body.detail.fields ?? []
    return fields.length ? `${body.detail.message} Missing or invalid: ${fields.join(', ')}.` : body.detail.message
  }
  return 'Something went wrong. Please try again.'
}

function numericError(value: string, label: string, positive = false): string | null {
  if (!value.trim()) return `${label} is required.`
  const number = Number(value)
  if (!Number.isFinite(number) || number < 0 || (positive && number === 0)) {
    return `${label} must be ${positive ? 'greater than zero' : 'zero or greater'}.`
  }
  return null
}

function stepErrors(step: number, values: ApplicationFormValues, documentCount: number): FieldErrors {
  const errors: FieldErrors = {}
  const need = (key: keyof ApplicationFormValues, message: string) => { errors[key] = message }
  if (step === 0) {
    if (values.applicant_name.trim().length < 2) need('applicant_name', 'Enter your name.')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.applicant_email)) need('applicant_email', 'Enter a valid email address.')
    if (values.applicant_phone.replace(/\D/g, '').length < 10 || values.applicant_phone.replace(/\D/g, '').length > 15) need('applicant_phone', 'Enter a phone number with 10 to 15 digits.')
  }
  if (step === 1) {
    if (values.company_name.trim().length < 2) need('company_name', 'Enter the company or startup name.')
    if (!/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(values.pan.trim().toUpperCase())) need('pan', 'Enter a valid 10-character PAN.')
    if (values.gstin && !/^[0-9A-Z]{15}$/i.test(values.gstin.trim())) need('gstin', 'GSTIN must contain 15 letters or digits.')
    if (values.cin && !/^[0-9A-Z]{21}$/i.test(values.cin.trim())) need('cin', 'CIN must contain 21 letters or digits.')
  }
  if (step === 2) {
    if (values.project_type.trim().length < 2) need('project_type', 'Choose a project type.')
    if (values.project_description.trim().length < 20) need('project_description', 'Describe the project in at least 20 characters.')
    for (const [key, label, positive] of [
      ['investment_amount', 'Investment amount', false],
      ['number_of_employees', 'Number of employees', false],
      ['built_up_area', 'Built-up area', true],
      ['power_requirement', 'Power requirement', false],
      ['water_requirement', 'Water requirement', false],
    ] as const) {
      const message = numericError(values[key], label, positive)
      if (message) need(key, message)
    }
    if (values.number_of_employees && !/^\d+$/.test(values.number_of_employees)) need('number_of_employees', 'Enter a whole number of employees.')
  }
  if (step === 3) {
    if (values.project_location.trim().length < 5) need('project_location', 'Enter the project location.')
    if (values.land_details.trim().length < 5) need('land_details', 'Add the land and possession details.')
    if (values.midc_area === null) need('midc_area', 'Select whether this project is in an MIDC area.')
    if (values.midc_area && values.midc_area_name.trim().length < 2) need('midc_area_name', 'Enter the MIDC area name.')
  }
  if (step === 4) {
    if (!INDUSTRIES.includes(values.industry_type as typeof INDUSTRIES[number])) need('industry_type', 'Select an industry.')
    if (values.industry_type === 'Other' && values.other_industry_name.trim().length < 2) need('other_industry_name', 'Specify the industry.')
    if (!POLLUTION_CATEGORIES.includes(values.pollution_category as typeof POLLUTION_CATEGORIES[number])) need('pollution_category', 'Select a pollution category, or choose Not sure.')
    if (values.hazardous_materials === null) need('hazardous_materials', 'Select whether hazardous materials will be used.')
    if (values.hazardous_materials && values.hazardous_materials_details.trim().length < 3) need('hazardous_materials_details', 'Describe the hazardous materials.')
    if (values.factory_information.trim().length < 5) need('factory_information', 'Add basic factory information.')
    if (values.fire_safety_information.trim().length < 5) need('fire_safety_information', 'Add basic fire safety information.')
  }
  if (step === 5 && documentCount === 0) errors.documents = 'Upload at least one supporting document before continuing.'
  return errors
}

export function StartApplication() {
  const started = useRef(false)
  const [message, setMessage] = useState('Preparing a secure draft…')
  const [error, setError] = useState('')

  useEffect(() => {
    if (started.current) return
    started.current = true
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    void fetch('/api/applications', { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (!response.ok) throw new Error(await errorMessage(response))
        const application: ApplicationRecord = await response.json()
        window.location.replace(`/applicant/applications/${application.id}/edit`)
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Could not start an application.')
        setMessage('')
      })
  }, [])

  return <main className="wizard-message"><span className="eyebrow"><i /> NEW APPLICATION</span><h1>{message || 'We could not start your draft.'}</h1>{error && <p role="alert">{error}</p>}<a href="/applicant">Return to dashboard</a></main>
}

export default function ApplicationWizard({ applicationId, readOnly }: Props) {
  const [application, setApplication] = useState<ApplicationRecord | null>(null)
  const [correctionApprovalId, setCorrectionApprovalId] = useState<number | null>(null)
  const [correctionReady, setCorrectionReady] = useState(false)
  const [values, setValues] = useState<ApplicationFormValues>(blankApplication)
  const [step, setStep] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [saveState, setSaveState] = useState('')
  const [busy, setBusy] = useState(false)
  const [documentType, setDocumentType] = useState<string>(DOCUMENT_TYPES[0][0])
  const [uploaded, setUploaded] = useState<ApplicationDocument[]>([])
  const [uploadPercent, setUploadPercent] = useState<number | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const saveQueue = useRef<Promise<void>>(Promise.resolve())
  const savedSnapshot = useRef('')
  const valuesRef = useRef(values)

  useEffect(() => { valuesRef.current = values }, [values])

  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    const headers = { Authorization: `Bearer ${token}` }
    void (async () => {
      try {
        const me = await fetch('/api/auth/me', { headers })
        if (!me.ok) throw new Error('Your session has expired. Sign in again.')
        const account: { role: string } = await me.json()
        if (account.role !== 'APPLICANT') {
          window.location.assign(account.role === 'OFFICER' ? '/officer' : '/admin')
          return
        }
        const response = await fetch(`/api/applications/${applicationId}`, { headers })
        if (!response.ok) throw new Error(await errorMessage(response))
        const record: ApplicationRecord = await response.json()
        setApplication(record)
        let openCorrectionId: number | null = null
        if (!readOnly && record.status !== 'DRAFT') {
          const workflowResponse = await fetch(`/api/applications/${applicationId}/approvals`, { headers })
          if (workflowResponse.ok) {
            const workflow = await workflowResponse.json()
            const correction = workflow.approvals?.find((item: { status: string }) => item.status === 'DOCUMENT_CORRECTION')
            openCorrectionId = correction?.id ?? null
            setCorrectionReady(Boolean(correction?.correction_can_submit))
          }
        }
        setCorrectionApprovalId(openCorrectionId)
        const form = applicationToForm(record)
        setValues(form)
        valuesRef.current = form
        savedSnapshot.current = JSON.stringify(formToDraft(form))
        setUploaded(record.documents ?? [])
        if (readOnly || (record.status !== 'DRAFT' && openCorrectionId === null)) setStep(6)
        else {
          const requestedStep = Number(new URLSearchParams(window.location.search).get('step'))
          if (Number.isInteger(requestedStep) && requestedStep >= 0 && requestedStep <= 7) setStep(requestedStep)
          else if (openCorrectionId !== null) setStep(0)
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'Unable to load this application.')
      } finally {
        setLoading(false)
      }
    })()
  }, [applicationId, readOnly])

  const isCorrectionMode = correctionApprovalId !== null && !readOnly
  const isReadOnly = readOnly || (application?.status !== 'DRAFT' && !isCorrectionMode)

  async function sendDraft(snapshot: ApplicationFormValues): Promise<ApplicationRecord> {
    const token = localStorage.getItem('mahaclear_access_token')
    const response = await fetch(`/api/applications/${applicationId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(formToDraft(snapshot)),
    })
    if (!response.ok) throw new Error(await errorMessage(response))
    const record: ApplicationRecord = await response.json()
    setApplication(record)
    savedSnapshot.current = JSON.stringify(formToDraft(snapshot))
    if (correctionApprovalId !== null) setCorrectionReady(true)
    return record
  }

  function queueDraft(snapshot: ApplicationFormValues): Promise<ApplicationRecord> {
    const next = saveQueue.current.then(() => sendDraft(snapshot))
    saveQueue.current = next.then(() => undefined, () => undefined)
    return next
  }

  async function refreshApplication(token: string | null) {
    const response = await fetch(`/api/applications/${applicationId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (response.ok) setApplication(await response.json())
  }

  useEffect(() => {
    if (loading || !application || isReadOnly) return
    const snapshot = values
    const serialized = JSON.stringify(formToDraft(snapshot))
    if (serialized === savedSnapshot.current) return
    setSaveState('Saving changes…')
    const timer = window.setTimeout(() => {
      void queueDraft(snapshot)
        .then(() => {
          if (JSON.stringify(formToDraft(valuesRef.current)) === serialized) setSaveState('All changes saved')
        })
        .catch((caught: unknown) => setSaveState(caught instanceof Error ? caught.message : 'Autosave failed'))
    }, 750)
    return () => window.clearTimeout(timer)
  }, [application, isReadOnly, loading, values])

  function update<K extends keyof ApplicationFormValues>(key: K, value: ApplicationFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }))
    setFieldErrors((current) => { const next = { ...current }; delete next[key]; return next })
  }

  async function saveNow(snapshot = values): Promise<boolean> {
    if (JSON.stringify(formToDraft(snapshot)) === savedSnapshot.current) return true
    setSaveState('Saving changes…')
    try {
      await queueDraft(snapshot)
      setSaveState('All changes saved')
      return true
    } catch (caught) {
      setSaveState(caught instanceof Error ? caught.message : 'Could not save this draft')
      return false
    }
  }

  async function saveAndExit() {
    setBusy(true)
    if (await saveNow()) window.location.assign('/applicant')
    else setBusy(false)
  }

  async function goToStep(nextStep: number) {
    if (nextStep > step) {
      const errors = stepErrors(step, values, uploaded.length)
      if (Object.keys(errors).length) { setFieldErrors(errors); return }
    }
    setFieldErrors({})
    if (!isReadOnly && !(await saveNow())) return
    setStep(nextStep)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function processFiles(files: File[], uploadType = documentType): Promise<boolean> {
    if (!files.length) return false
    setError('')
    setBusy(true)
    try {
      const token = localStorage.getItem('mahaclear_access_token')
      for (const file of files) {
        if (file.size > 15 * 1024 * 1024) throw new Error(`${file.name} exceeds the 15 MB limit.`)
        const extension = file.name.toLowerCase().split('.').pop()
        const allowedMime = ['application/pdf', 'image/jpeg', 'image/png', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        const allowedExtension = ['pdf', 'jpg', 'jpeg', 'png', 'docx'].includes(extension ?? '')
        if (!allowedMime.includes(file.type) && !allowedExtension) throw new Error(`${file.name}: choose a PDF, JPG, PNG, or DOCX file.`)
        const body = new FormData()
        body.append('document_type', uploadType)
        body.append('file', file)
        const document: ApplicationDocument = await new Promise((resolve, reject) => {
          const request = new XMLHttpRequest()
          request.open('POST', `/api/applications/${applicationId}/documents`)
          if (token) request.setRequestHeader('Authorization', `Bearer ${token}`)
          request.upload.onprogress = (progress) => {
            if (progress.lengthComputable) setUploadPercent(Math.round(progress.loaded * 100 / progress.total))
          }
          request.onerror = () => reject(new Error('Upload failed. Check your connection and try again.'))
          request.onload = () => {
            if (request.status >= 200 && request.status < 300) resolve(JSON.parse(request.responseText) as ApplicationDocument)
            else { let message = 'Upload failed.'; try { message = JSON.parse(request.responseText).detail ?? message } catch { /* use generic message */ }; reject(new Error(message)) }
          }
          request.send(body)
        })
        setUploaded((current) => [...current, document])
        if (correctionApprovalId !== null) setCorrectionReady(true)
        setSaveState('Document uploaded')
      }
      await refreshApplication(token)
      return true
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Upload failed.')
      return false
    } finally {
      setUploadPercent(null)
      setBusy(false)
    }
  }

  async function uploadFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    await processFiles(files)
  }

  function onDropFiles(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragActive(false)
    if (!busy) void processFiles(Array.from(event.dataTransfer.files))
  }

  async function replaceDocument(document: ApplicationDocument) {
    if (isReadOnly || busy) return
    const input = window.document.createElement('input')
    input.type = 'file'
    input.accept = '.pdf,.jpg,.jpeg,.png,.docx,application/pdf,image/jpeg,image/png,application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    input.multiple = false
    input.onchange = () => {
      const files = Array.from(input.files ?? [])
      if (!files.length) return
      void (async () => {
        try {
          const uploadedSuccessfully = await processFiles(files, document.document_type)
          if (!uploadedSuccessfully) return
          await removeDocument(document.id)
          setSaveState('Document replaced')
        } catch {
          // processFiles already reports upload errors
        }
      })()
    }
    input.click()
  }

  async function removeDocument(documentId: number) {
    const token = localStorage.getItem('mahaclear_access_token')
    const response = await fetch(`/api/applications/${applicationId}/documents/${documentId}`, {
      method: 'DELETE',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) { setError(await errorMessage(response)); return }
    setUploaded((current) => current.filter((document) => document.id !== documentId))
    setSaveState('Document removed')
    await refreshApplication(token)
  }

  function openPrevalidation() {
    window.location.assign(`/applicant/applications/${applicationId}/prevalidation`)
  }

  async function submitApplication() {
    const errors: FieldErrors = {}
    for (let index = 0; index <= 5; index += 1) Object.assign(errors, stepErrors(index, values, uploaded.length))
    if (Object.keys(errors).length) {
      setFieldErrors(errors)
      setStep(Number(Object.keys(errors).some((key) => ['applicant_name', 'applicant_email', 'applicant_phone'].includes(key)) ? 0 :
        Object.keys(errors).some((key) => ['company_name', 'pan', 'gstin', 'cin'].includes(key)) ? 1 :
        Object.keys(errors).some((key) => ['project_type', 'project_description', 'investment_amount', 'number_of_employees', 'built_up_area', 'power_requirement', 'water_requirement'].includes(key)) ? 2 :
        Object.keys(errors).some((key) => ['project_location', 'land_details', 'midc_area', 'midc_area_name'].includes(key)) ? 3 :
        Object.keys(errors).includes('documents') ? 5 : 4))
      return
    }
    setBusy(true)
    setError('')
    try {
      if (!(await saveNow(values))) throw new Error('Your draft could not be saved. Please try again.')
      const token = localStorage.getItem('mahaclear_access_token')
      const response = await fetch(`/api/applications/${applicationId}/submit`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!response.ok) throw new Error(await errorMessage(response))
      const submitted: ApplicationRecord = await response.json()
      setApplication(submitted)
      setStep(7)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not submit your application.')
    } finally {
      setBusy(false)
    }
  }

  async function submitCorrection() {
    if (correctionApprovalId === null) return
    setBusy(true)
    setError('')
    try {
      if (!(await saveNow(values))) throw new Error('Your correction could not be saved. Please try again.')
      const token = localStorage.getItem('mahaclear_access_token')
      const response = await fetch(`/api/approvals/${correctionApprovalId}/correction-submitted`, {
        method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!response.ok) throw new Error(await errorMessage(response))
      window.location.assign(`/applicant/applications/${applicationId}/approvals`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not submit the correction.')
    } finally { setBusy(false) }
  }

  if (loading) return <main className="wizard-message"><span className="eyebrow"><i /> APPLICATION</span><h1>Loading application…</h1></main>
  if (error && !application) return <main className="wizard-message"><span className="eyebrow"><i /> APPLICATION</span><h1>We couldn’t open this application.</h1><p>{error}</p><a href="/applicant">Return to dashboard</a></main>
  if (!application) return null
  const submitted = application.status !== 'DRAFT'

  return (
    <div className="wizard-shell">
      <header className="wizard-topbar"><a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><div className="wizard-top-meta"><span>{isCorrectionMode ? 'CORRECTION RESPONSE' : submitted ? 'SUBMITTED APPLICATION' : 'APPLICATION DRAFT'}</span><strong>{application.application_number}</strong></div><a className="wizard-exit" href="/applicant">Exit to dashboard <span>↗</span></a></header>
      <main className="wizard-main">
        {isCorrectionMode ? <div className="submitted-banner correction-banner"><span>!</span><div><strong>Department correction requested</strong><p>Update the requested details or supporting files, then submit your correction for review.</p></div><a href={`/applicant/applications/${applicationId}/approvals`}>View request →</a></div> : submitted && <div className="submitted-banner"><span>✓</span><div><strong>Application submitted</strong><p>Your application is saved. You can track updates from your dashboard.</p></div><a href="/applicant">View dashboard →</a></div>}
        <div className="wizard-heading"><div><span className="eyebrow"><i /> {isCorrectionMode ? 'DEPARTMENT CORRECTION' : submitted ? 'APPLICATION DETAILS' : 'NEW INDUSTRIAL APPROVAL'}</span><h1>{isCorrectionMode ? 'Respond to correction' : submitted ? 'Application details' : 'Start your application'}</h1><p>{isCorrectionMode ? 'Update the requested information or replace a supporting document. Changes save automatically.' : 'Complete each section. Your draft saves automatically as you go.'}</p></div><div className="wizard-saved"><span className={`save-dot ${saveState.includes('fail') || saveState.includes('could not') ? 'save-error' : ''}`} />{isReadOnly ? submitted ? 'Submitted' : 'Read only' : saveState || 'Draft ready'}</div></div>
        <div className="wizard-progress"><div><span>STEP {step + 1} OF 8</span><strong>{APPLICATION_STEPS[step]}</strong></div><div className="wizard-progress-track"><i style={{ width: `${Math.max(application.progress_percent, ((step + 1) / 8) * 100)}%` }} /></div><span>{application.progress_percent}% COMPLETE</span></div>
        <nav className="wizard-step-nav" aria-label="Application steps">{APPLICATION_STEPS.map((label, index) => <button key={label} className={`${index === step ? 'active' : ''} ${index < step ? 'complete' : ''}`} onClick={() => { if (index < step) void goToStep(index) }} disabled={index >= step}><span>{index < step ? '✓' : String(index + 1).padStart(2, '0')}</span><small>{label}</small></button>)}</nav>

        <form className="wizard-card" onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}>
          <div className="wizard-card-heading"><div><span className="card-kicker">STEP {String(step + 1).padStart(2, '0')} / 08</span><h2>{APPLICATION_STEPS[step]}</h2><p>{stepDescription(step)}</p></div><span className="wizard-lock">{isReadOnly ? 'VIEW ONLY' : isCorrectionMode ? 'CORRECTION RESPONSE' : 'SECURE DRAFT'}</span></div>
          {error && <div className="wizard-error" role="alert">{error}</div>}
          <div className="wizard-fields">
            {step === 0 && <>
              <Field label="Applicant name" error={fieldErrors.applicant_name}><input autoComplete="name" disabled={isReadOnly} value={values.applicant_name} onChange={(event) => update('applicant_name', event.target.value)} placeholder="Full name of the applicant" /></Field>
              <Field label="Email address" error={fieldErrors.applicant_email}><input type="email" autoComplete="email" disabled={isReadOnly} value={values.applicant_email} onChange={(event) => update('applicant_email', event.target.value)} placeholder="name@company.com" /></Field>
              <Field label="Phone number" hint="Include country code if applicable." error={fieldErrors.applicant_phone}><input type="tel" autoComplete="tel" disabled={isReadOnly} value={values.applicant_phone} onChange={(event) => update('applicant_phone', event.target.value)} placeholder="+91 98765 43210" /></Field>
            </>}
            {step === 1 && <>
              <Field label="Company / startup name" error={fieldErrors.company_name}><input autoComplete="organization" disabled={isReadOnly} value={values.company_name} onChange={(event) => update('company_name', event.target.value)} placeholder="Registered company or startup name" /></Field>
              <Field label="PAN" hint="10-character Permanent Account Number." error={fieldErrors.pan}><input disabled={isReadOnly} maxLength={10} value={values.pan} onChange={(event) => update('pan', event.target.value.toUpperCase())} placeholder="ABCDE1234F" /></Field>
              <Field label="GSTIN" optional error={fieldErrors.gstin}><input disabled={isReadOnly} maxLength={15} value={values.gstin} onChange={(event) => update('gstin', event.target.value.toUpperCase())} placeholder="15-character GSTIN" /></Field>
              <Field label="CIN" optional error={fieldErrors.cin}><input disabled={isReadOnly} maxLength={21} value={values.cin} onChange={(event) => update('cin', event.target.value.toUpperCase())} placeholder="21-character CIN" /></Field>
              <Field label="Udyam number" optional><input disabled={isReadOnly} maxLength={30} value={values.udyam_number} onChange={(event) => update('udyam_number', event.target.value.toUpperCase())} placeholder="Udyam registration number" /></Field>
            </>}
            {step === 2 && <>
              <Field label="Project type" error={fieldErrors.project_type}><select disabled={isReadOnly} value={values.project_type} onChange={(event) => update('project_type', event.target.value)}><option value="">Select project type</option><option>Greenfield / new unit</option><option>Expansion</option><option>Modernization</option><option>Diversification</option><option>Other</option></select></Field>
              <Field label="Project description" hint="Describe the proposed facility and what it will produce." error={fieldErrors.project_description}><textarea rows={4} maxLength={5000} disabled={isReadOnly} value={values.project_description} onChange={(event) => update('project_description', event.target.value)} placeholder="Describe the project (at least 20 characters)" /></Field>
              <div className="wizard-grid-2">
                <Field label="Investment amount (₹)" error={fieldErrors.investment_amount}><input type="number" min="0" step="0.01" disabled={isReadOnly} value={values.investment_amount} onChange={(event) => update('investment_amount', event.target.value)} placeholder="e.g. 12500000" /></Field>
                <Field label="Number of employees" error={fieldErrors.number_of_employees}><input type="number" min="0" step="1" disabled={isReadOnly} value={values.number_of_employees} onChange={(event) => update('number_of_employees', event.target.value)} placeholder="e.g. 48" /></Field>
                <Field label="Built-up area (sq. ft.)" error={fieldErrors.built_up_area}><input type="number" min="0.01" step="0.01" disabled={isReadOnly} value={values.built_up_area} onChange={(event) => update('built_up_area', event.target.value)} placeholder="e.g. 8600" /></Field>
                <Field label="Power requirement (kW)" error={fieldErrors.power_requirement}><input type="number" min="0" step="0.01" disabled={isReadOnly} value={values.power_requirement} onChange={(event) => update('power_requirement', event.target.value)} placeholder="e.g. 340" /></Field>
                <Field label="Water requirement (KL/day)" error={fieldErrors.water_requirement}><input type="number" min="0" step="0.01" disabled={isReadOnly} value={values.water_requirement} onChange={(event) => update('water_requirement', event.target.value)} placeholder="e.g. 1250" /></Field>
              </div>
            </>}
            {step === 3 && <>
              <Field label="Project location" hint="Include plot, area, city, district, and state." error={fieldErrors.project_location}><textarea rows={3} disabled={isReadOnly} value={values.project_location} onChange={(event) => update('project_location', event.target.value)} placeholder="Plot and full project address" /></Field>
              <Field label="Land details" hint="Ownership or lease, plot area, possession, and supporting records." error={fieldErrors.land_details}><textarea rows={3} disabled={isReadOnly} value={values.land_details} onChange={(event) => update('land_details', event.target.value)} placeholder="Describe land ownership or lease and plot details" /></Field>
              <ChoiceGroup label="Is the project within an MIDC area?" value={values.midc_area} disabled={isReadOnly} error={fieldErrors.midc_area} onChange={(value) => update('midc_area', value)} />
              {values.midc_area && <Field label="MIDC area name" error={fieldErrors.midc_area_name}><input disabled={isReadOnly} value={values.midc_area_name} onChange={(event) => update('midc_area_name', event.target.value)} placeholder="e.g. Chakan MIDC Phase II" /></Field>}
            </>}
            {step === 4 && <>
              <Field label="Industry type" error={fieldErrors.industry_type}><select disabled={isReadOnly} value={values.industry_type} onChange={(event) => update('industry_type', event.target.value)}><option value="">Select industry</option>{INDUSTRIES.map((industry) => <option key={industry}>{industry}</option>)}</select></Field>
              {values.industry_type === 'Other' && <Field label="Specify industry" error={fieldErrors.other_industry_name}><input disabled={isReadOnly} value={values.other_industry_name} onChange={(event) => update('other_industry_name', event.target.value)} placeholder="Describe the industry" /></Field>}
              <div className="risk-info-divider"><span>RISK INFORMATION</span><small>This records information for review. No risk score is calculated.</small></div>
              <Field label="Pollution category" error={fieldErrors.pollution_category}><select disabled={isReadOnly} value={values.pollution_category} onChange={(event) => update('pollution_category', event.target.value)}><option value="">Select category</option>{POLLUTION_CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select></Field>
              <ChoiceGroup label="Will the project use hazardous materials?" value={values.hazardous_materials} disabled={isReadOnly} error={fieldErrors.hazardous_materials} onChange={(value) => update('hazardous_materials', value)} />
              {values.hazardous_materials && <Field label="Hazardous materials details" error={fieldErrors.hazardous_materials_details}><textarea rows={3} disabled={isReadOnly} value={values.hazardous_materials_details} onChange={(event) => update('hazardous_materials_details', event.target.value)} placeholder="List materials and their intended use" /></Field>}
              <Field label="Factory information" error={fieldErrors.factory_information}><textarea rows={3} disabled={isReadOnly} value={values.factory_information} onChange={(event) => update('factory_information', event.target.value)} placeholder="Process, capacity, shifts, and machinery overview" /></Field>
              <Field label="Fire safety information" error={fieldErrors.fire_safety_information}><textarea rows={3} disabled={isReadOnly} value={values.fire_safety_information} onChange={(event) => update('fire_safety_information', event.target.value)} placeholder="Planned fire detection, suppression, and evacuation measures" /></Field>
            </>}
            {step === 5 && <>
              <div className="document-instructions"><span className="document-symbol">↥</span><div><strong>Supporting documents</strong><p>Upload the required registration, location, project, safety, and identity documents. PDF, JPG, PNG, and DOCX files up to 15 MB each.</p></div></div>
              {!isReadOnly && <div className="upload-row"><Field label="Document type"><select value={documentType} onChange={(event) => setDocumentType(event.target.value)}>{DOCUMENT_TYPES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></Field><div className={`upload-dropzone ${dragActive ? 'drag-active' : ''} ${busy ? 'disabled' : ''}`} onDragOver={(event) => { event.preventDefault(); if (!busy) setDragActive(true) }} onDragLeave={() => setDragActive(false)} onDrop={onDropFiles}><strong>{dragActive ? 'Drop documents here' : 'Drag & drop documents here'}</strong><span>or choose multiple PDF, JPG, PNG or DOCX files · up to 15 MB each</span><label className="upload-button">Choose files<input type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,application/pdf,image/jpeg,image/png,application/vnd.openxmlformats-officedocument.wordprocessingml.document" multiple disabled={busy} onChange={(event) => void uploadFiles(event)} /></label></div></div>}
              {uploadPercent !== null && <div className="upload-progress-panel"><div><strong>Uploading document</strong><span>{uploadPercent}%</span></div><progress max="100" value={uploadPercent} /></div>}
              {fieldErrors.documents && <p className="field-error">{fieldErrors.documents}</p>}
              {uploaded.length === 0 ? <div className="no-documents">No documents uploaded yet.</div> : <ul className="document-list">{uploaded.map((document) => <li key={document.id}><span className="file-mark">FILE</span><span className="document-name"><strong>{document.file_name}</strong><small>{documentLabel(document.document_type)} · {formatBytes(document.size_bytes)} · {document.status}</small></span><a href={`/api/applications/${applicationId}/documents/${document.id}/download`} onClick={(event) => { event.preventDefault(); void downloadDocument(applicationId, document.id) }}>View</a>{!isReadOnly && <><button type="button" aria-label={`Replace ${document.file_name}`} onClick={() => replaceDocument(document)}>Replace</button><button type="button" aria-label={`Remove ${document.file_name}`} onClick={() => void removeDocument(document.id)}>Remove</button></>}</li>)}</ul>}
              {!isReadOnly && <button className="secondary-button" type="button" onClick={() => void openPrevalidation()} disabled={busy}>Run document pre-validation →</button>}
            </>}
            {step === 6 && <><Review values={values} application={application} documents={uploaded} /><a className="risk-review-link" href={`/applicant/applications/${applicationId}/risk`}>Open transparent risk assessment <span>→</span></a></>}
            {step === 7 && <div className="final-submit-panel"><span className="submit-seal">{isCorrectionMode ? '↻' : '✓'}</span><span className="card-kicker">FINAL STEP</span><h3>{isCorrectionMode ? 'Ready to submit your correction?' : submitted ? 'Your application has been submitted.' : 'Ready to submit?'}</h3><p>{isCorrectionMode ? correctionReady ? 'Your updated information will return to the requesting department for review.' : 'Update an application detail or upload/replace a document before submitting the response.' : submitted ? 'The application is locked for editing and appears in your applicant dashboard.' : 'Submitting locks this application draft. It will appear in your dashboard as pending. You can track its status there.'}</p><div className="submit-summary"><span>APPLICATION ID</span><strong>{application.application_number}</strong><span>RISK ASSESSMENT</span><strong>{application.risk_tier || 'Not calculated'}</strong></div><a className="risk-review-link" href={`/applicant/applications/${applicationId}/risk`}>View risk assessment and factors <span>→</span></a></div>}
          </div>
          <div className="wizard-actions">
            <div className="wizard-action-left">{step > 0 && <button className="secondary-button" type="button" onClick={() => void goToStep(step - 1)}>← Back</button>}</div>
            <div className="wizard-action-right">{!isReadOnly && <button className="text-button" type="button" onClick={() => void saveAndExit()} disabled={busy}>{isCorrectionMode ? 'Save & return' : 'Save draft & exit'}</button>}{step < 7 ? <button className="primary-button" type="button" onClick={() => void goToStep(step + 1)} disabled={busy}>{isReadOnly ? 'Continue' : step === 6 ? 'Review submission' : 'Save & continue'} <span>→</span></button> : isCorrectionMode ? <button className="primary-button submit-button" type="button" onClick={() => void submitCorrection()} disabled={busy || !correctionReady}>{busy ? 'Submitting…' : 'Submit correction'} <span>→</span></button> : !submitted ? <button className="primary-button submit-button" type="button" onClick={() => void submitApplication()} disabled={busy}>{busy ? 'Submitting…' : 'Submit application'} <span>→</span></button> : <a className="primary-button button-link" href="/applicant">Back to dashboard <span>→</span></a>}</div>
          </div>
        </form>
        <div className="wizard-footnote"><span>YOUR DRAFT IS PRIVATE</span><span>Progress saves automatically · No workflow or risk calculation is performed</span></div>
      </main>
    </div>
  )

}

function Field({ label, hint, optional, error, children }: { label: string; hint?: string; optional?: boolean; error?: string; children: ReactNode }) {
  return <label className="wizard-field"><span>{label}{optional && <small className="optional-label">OPTIONAL</small>}</span>{children}{hint && <small className="field-hint">{hint}</small>}{error && <small className="field-error">{error}</small>}</label>
}

function ChoiceGroup({ label, value, disabled, error, onChange }: { label: string; value: boolean | null; disabled: boolean; error?: string; onChange: (value: boolean) => void }) {
  return <fieldset className="choice-field"><legend>{label}</legend><div><button type="button" className={value === true ? 'chosen' : ''} disabled={disabled} onClick={() => onChange(true)}>Yes</button><button type="button" className={value === false ? 'chosen' : ''} disabled={disabled} onClick={() => onChange(false)}>No</button></div>{error && <small className="field-error">{error}</small>}</fieldset>
}

function Review({ values, application, documents }: { values: ApplicationFormValues; application: ApplicationRecord; documents: ApplicationDocument[] }) {
  return <div className="review-groups">
    <ReviewGroup title="Applicant"><ReviewLine label="Applicant name" value={values.applicant_name} /><ReviewLine label="Email" value={values.applicant_email} /><ReviewLine label="Phone" value={values.applicant_phone} /></ReviewGroup>
    <ReviewGroup title="Company"><ReviewLine label="Company" value={values.company_name} /><ReviewLine label="PAN" value={values.pan} /><ReviewLine label="GSTIN" value={values.gstin} /><ReviewLine label="CIN" value={values.cin} /><ReviewLine label="Udyam" value={values.udyam_number} /></ReviewGroup>
    <ReviewGroup title="Project"><ReviewLine label="Industry" value={values.industry_type === 'Other' ? values.other_industry_name : values.industry_type} /><ReviewLine label="Project type" value={values.project_type} /><ReviewLine label="Description" value={values.project_description} /><ReviewLine label="Investment" value={formatCurrency(values.investment_amount)} /><ReviewLine label="Employees" value={values.number_of_employees} /><ReviewLine label="Built-up area" value={withUnit(values.built_up_area, 'sq. ft.')} /><ReviewLine label="Power" value={withUnit(values.power_requirement, 'kW')} /><ReviewLine label="Water" value={withUnit(values.water_requirement, 'KL/day')} /></ReviewGroup>
    <ReviewGroup title="Location & industry"><ReviewLine label="Location" value={values.project_location} /><ReviewLine label="Land" value={values.land_details} /><ReviewLine label="MIDC area" value={values.midc_area ? values.midc_area_name : 'No'} /><ReviewLine label="Pollution category" value={values.pollution_category} /><ReviewLine label="Hazardous materials" value={values.hazardous_materials ? values.hazardous_materials_details : 'No'} /><ReviewLine label="Factory" value={values.factory_information} /><ReviewLine label="Fire safety" value={values.fire_safety_information} /></ReviewGroup>
    <ReviewGroup title={`Documents (${documents.length})`}>{documents.length ? documents.map((document) => <ReviewLine key={document.id} label={documentLabel(document.document_type)} value={document.file_name} />) : <ReviewLine label="Uploaded" value="No documents" />}</ReviewGroup>
    <p className="review-risk-note">Risk tier: {application.risk_tier || 'Not assessed. Risk calculation is not part of this phase.'}</p>
  </div>
}

function ReviewGroup({ title, children }: { title: string; children: ReactNode }) { return <section className="review-group"><h3>{title}</h3><div>{children}</div></section> }
function ReviewLine({ label, value }: { label: string; value: string }) { return <p><span>{label}</span><strong>{value || '—'}</strong></p> }

function stepDescription(step: number): string {
  return [
    'Confirm the primary contact for this application.',
    'Add the applicant company and registration details.',
    'Describe the proposed project and its estimated requirements.',
    'Tell us where the project will be located and the land details.',
    'Select the industry and provide the requested safety and pollution information.',
    'Attach the documents that support this application.',
    'Review the information you have provided before submission.',
    'Submit the application to create your official record.',
  ][step]
}

function documentLabel(type: string): string { return DOCUMENT_TYPES.find(([value]) => value === type)?.[1] ?? type }
function formatBytes(bytes: number): string { return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB` }
function formatCurrency(value: string): string { return value ? `₹${Number(value).toLocaleString('en-IN')}` : '—' }
function withUnit(value: string, unit: string): string { return value ? `${Number(value).toLocaleString('en-IN')} ${unit}` : '—' }

async function downloadDocument(applicationId: number, documentId: number) {
  const token = localStorage.getItem('mahaclear_access_token')
  const response = await fetch(`/api/applications/${applicationId}/documents/${documentId}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) return
  const file = await response.blob()
  const url = URL.createObjectURL(file)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = response.headers.get('content-disposition')?.match(/filename="?([^";]+)"?/i)?.[1] ?? 'application-document'
  anchor.click()
  URL.revokeObjectURL(url)
}
