import { useEffect, useMemo, useState } from 'react'

type Application = {
  id: number
  application_number: string
  industry_type: string | null
  company_name: string | null
  status: string
}

type Permission = {
  id: string
  name: string
  authority: string
  fee: string
  summary: string
  steps: string[]
  documents: string[]
  website: string
  websiteLabel: string
}

const SEQUENTIAL: Permission[] = [
  {
    id: 'planning', name: 'Site / Planning Approval', authority: 'Local Planning Authority',
    fee: 'As per local authority schedule',
    summary: 'Confirm land-use and planning permission for the proposed industrial site.',
    steps: ['Confirm zoning / land use', 'Prepare site and building documents', 'Submit the planning application', 'Receive approval / NOC'],
    documents: ['Land ownership / lease document', 'Site plan', 'Building plan'],
    website: 'https://mahaonline.gov.in/', websiteLabel: 'MahaOnline',
  },
  {
    id: 'mpcb-cte', name: 'MPCB Consent to Establish', authority: 'Maharashtra Pollution Control Board',
    fee: 'Based on capital investment and applicable category',
    summary: 'Environmental consent required before establishing an activity covered by MPCB consent requirements.',
    steps: ['Register on the online consent portal', 'Upload required documents', 'Pay applicable consent fee', 'Track scrutiny and approval'],
    documents: ['Site plan', 'Process flow sheet', 'Industry registration', 'Land ownership document', 'Pollution-control proposal'],
    website: 'https://www.mpcb.gov.in/en', websiteLabel: 'MPCB official portal',
  },
  {
    id: 'factory-plan', name: 'Factory Plan / Registration', authority: 'Directorate of Industrial Safety & Health',
    fee: 'As per applicable factory rules / schedule',
    summary: 'Factory-related approval and registration requirements depend on the establishment, workforce and activity.',
    steps: ['Prepare factory and process details', 'Submit prescribed drawings and documents', 'Pay applicable fee', 'Track inspection / approval'],
    documents: ['Building plan', 'Factory details', 'Identity / company documents'],
    website: 'https://mahadish.in/', websiteLabel: 'DISH Maharashtra',
  },
]

const PARALLEL: Permission[] = [
  {
    id: 'fire', name: 'Fire Approval / NOC', authority: 'Maharashtra Fire & Emergency Services',
    fee: 'As per applicable fire approval / fund schedule',
    summary: 'Fire-safety approval can be processed alongside other eligible permissions once the required drawings are ready.',
    steps: ['Prepare fire-safety drawings', 'Submit online application', 'Pay applicable charges', 'Complete inspection / compliance', 'Receive approval / NOC'],
    documents: ['Block plan', 'Floor plans', 'Section / elevation drawings', 'Fire-safety details'],
    website: 'https://mahafireservice.gov.in/e-fire.php', websiteLabel: 'Fire E-Approval',
  },
  {
    id: 'electricity', name: 'Electricity Connection', authority: 'Concerned Electricity Distribution Utility',
    fee: 'Based on sanctioned load and connection requirements',
    summary: 'Apply for the required industrial electricity connection after the site and load details are available.',
    steps: ['Determine connected load', 'Submit connection application', 'Pay applicable charges', 'Complete site / meter formalities'],
    documents: ['Applicant / company proof', 'Premises document', 'Load details'],
    website: 'https://www.mahadiscom.in/', websiteLabel: 'MSEDCL',
  },
  {
    id: 'water', name: 'Industrial Water Connection', authority: 'Concerned Local / Industrial Area Authority',
    fee: 'As per connection and consumption schedule',
    summary: 'Water connection requirements depend on the location, source and proposed industrial use.',
    steps: ['Confirm water source / authority', 'Submit connection request', 'Pay applicable charges', 'Complete connection formalities'],
    documents: ['Premises document', 'Site plan', 'Water requirement details'],
    website: 'https://www.midcindia.org/', websiteLabel: 'MIDC',
  },
]

function permissionSet(industry: string | null) {
  const value = (industry || '').toLowerCase()
  if (value.includes('food')) {
    return {
      sequential: [...SEQUENTIAL, {
        id: 'food', name: 'Food Business Licence', authority: 'Food Safety Authority',
        fee: 'As per applicable licence category',
        summary: 'Food-related activities may require a food safety licence based on the nature and scale of the business.',
        steps: ['Identify licence category', 'Prepare food business documents', 'Apply online', 'Pay applicable fee and track approval'],
        documents: ['Business proof', 'Premises proof', 'Food business details'],
        website: 'https://foscos.fssai.gov.in/', websiteLabel: 'FoSCoS',
      } as Permission],
      parallel: PARALLEL,
    }
  }
  return { sequential: SEQUENTIAL, parallel: PARALLEL }
}

export default function ApplicantPermissionsPage() {
  const [applications, setApplications] = useState<Application[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    void fetch('/api/applications', { headers: { Authorization: `Bearer ${token}` } })
      .then(async response => {
        const body = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Unable to load your applications.')
        const items = (body.applications || []) as Application[]
        setApplications(items)
        setSelectedId(items[0]?.id ?? null)
      })
      .catch(caught => setError(caught instanceof Error ? caught.message : 'Unable to load your applications.'))
  }, [])

  const selected = applications.find(item => item.id === selectedId) || null
  const permissions = useMemo(() => permissionSet(selected?.industry_type || null), [selected?.industry_type])
  const signOut = () => { localStorage.removeItem('mahaclear_access_token'); window.location.assign('/login') }

  return (
    <div className="applicant-shell">
      <header className="applicant-topbar">
        <a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
        <div className="applicant-topbar-spacer" aria-hidden="true" />
        <button className="applicant-signout" type="button" onClick={signOut}><span className="signout-icon">↪</span><strong>Sign out</strong></button>
      </header>

      <aside className="applicant-sidebar">
        <div className="workspace-nav-label">APPLICANT WORKSPACE</div>
        <a className="side-link" href="/applicant/documents"><span>▣</span> Documents</a>
        <a className="side-link selected" href="/applicant/permissions"><span>◎</span> Permissions &amp; fees</a>
        <a className="side-link" href="/notifications"><span>◉</span> Verification &amp; updates</a>
        <a className="side-link" href="/applicant/applications"><span>▤</span> My applications</a>
        <div className="sidebar-note"><span className="sidebar-note-mark">✳</span><strong>One window.<br />Every approval.</strong><small>North-Star · SIH 2026</small></div>
        <div className="sidebar-bottom">MAHACLEAR-AI <span>·</span> APPLICANT</div>
      </aside>

      <main className="applicant-main permissions-main">
        <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> PERMISSIONS &amp; FEES</div>
        <div className="applicant-heading">
          <div><span className="eyebrow"><i /> APPROVAL ROADMAP</span><h1>Permissions &amp; fees</h1><p>Follow the approval sequence. Branch permissions can be processed in parallel where applicable.</p></div>
        </div>

        {error && <div className="applicant-error" role="alert">{error} <button onClick={() => window.location.reload()}>Retry</button></div>}

        {applications.length > 0 && (
          <div className="permission-application-picker">
            <label>APPLICATION
              <select value={selectedId ?? ''} onChange={event => { setSelectedId(Number(event.target.value)); setExpanded(null) }}>
                {applications.map(application => <option key={application.id} value={application.id}>{application.application_number}{application.industry_type ? ` · ${application.industry_type}` : ''}</option>)}
              </select>
            </label>
            <div><span>INDUSTRY</span><strong>{selected?.industry_type || 'Industry not specified'}</strong></div>
            <div><span>STATUS</span><strong>{selected?.status?.replaceAll('_', ' ') || '—'}</strong></div>
          </div>
        )}

        {!selected && !error ? (
          <div className="empty-applications permission-empty"><span className="empty-mark">◎</span><h3>No application selected</h3><p>Create an application and choose its industry to get an industry-specific roadmap.</p><a className="primary-button button-link" href="/applicant/applications/new">Start an application <span>→</span></a></div>
        ) : (
          <section className="permission-flow-card">
            <div className="permission-flow-legend">
              <div><span className="flow-dot sequential-dot" /> Sequential — follow the arrows</div>
              <div><span className="flow-dot parallel-dot" /> Parallel — can run independently where applicable</div>
            </div>
            <div className="permission-flow">
              <div className="flow-sequential">
                <div className="flow-section-label"><span>01</span><div><strong>Sequential approvals</strong><small>Complete in this order</small></div><b>{permissions.sequential.length}</b></div>
                {permissions.sequential.map((permission, index) => (
                  <PermissionNode key={permission.id} permission={permission} index={index} expanded={expanded === permission.id} onToggle={() => setExpanded(expanded === permission.id ? null : permission.id)} />
                ))}
              </div>

              <div className="flow-branch">
                <div className="flow-branch-line" aria-hidden="true" />
                <div className="flow-branch-label"><span>02</span><div><strong>Parallel approvals</strong><small>Can run alongside the main sequence</small></div><b>{permissions.parallel.length}</b></div>
                <div className="parallel-nodes">
                  {permissions.parallel.map((permission, index) => (
                    <PermissionNode key={permission.id} permission={permission} index={index} expanded={expanded === permission.id} onToggle={() => setExpanded(expanded === permission.id ? null : permission.id)} parallel />
                  ))}
                </div>
              </div>
            </div>
          </section>
        )}

        <div className="permission-ai-note"><span>✦</span><div><strong>AI-ready permission mapping</strong><small>Industry-specific permissions, dependencies and applicable fees can be updated by the AI/rules layer. Current portals are official government links.</small></div></div>
      </main>

      <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Approval roadmap</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
    </div>
  )
}

function PermissionNode({ permission, index, expanded, onToggle, parallel = false }: { permission: Permission; index: number; expanded: boolean; onToggle: () => void; parallel?: boolean }) {
  return (
    <div className={`permission-node-wrap ${expanded ? 'is-expanded' : ''}`}>
      <button className={`permission-node ${parallel ? 'parallel-node' : ''}`} type="button" onClick={onToggle} aria-expanded={expanded}>
        <span className="permission-node-number">{String(index + 1).padStart(2, '0')}</span>
        <span className="permission-node-copy"><strong>{permission.name}</strong><small>{permission.authority}</small></span>
        <span className="permission-node-fee">{permission.fee}</span>
        <span className="permission-node-arrow">{expanded ? '⌃' : '→'}</span>
      </button>
      {expanded && (
        <div className="permission-node-details">
          <p>{permission.summary}</p>
          <div className="permission-detail-grid">
            <div><strong>How to apply</strong><ol>{permission.steps.map(step => <li key={step}>{step}</li>)}</ol></div>
            <div><strong>Usually required</strong><ul>{permission.documents.map(document => <li key={document}>{document}</li>)}</ul></div>
          </div>
          <div className="permission-fee-detail"><strong>Applicable fee</strong><span>{permission.fee}</span></div>
          <a className="permission-website" href={permission.website} target="_blank" rel="noreferrer">Official portal: {permission.websiteLabel} <span>↗</span></a>
        </div>
      )}
      {!parallel && <span className="permission-down-arrow" aria-hidden="true">↓</span>}
    </div>
  )
}
