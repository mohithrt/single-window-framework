import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import ApplicantDashboard from './ApplicantDashboard'
import ApplicationWizard, { StartApplication } from './ApplicationWizard'
import PrevalidationPage from './PrevalidationPage'
import RiskAssessmentPage from './RiskAssessmentPage'
import ApprovalStatusPage from './ApprovalStatusPage'
import CriticalPathPage from './CriticalPathPage'
import OfficerPortal from './OfficerPortal'

type Role = 'APPLICANT' | 'OFFICER' | 'ADMIN'
type User = { id: number; email: string; full_name: string; role: Role }
type AuthResult = { access_token: string; user: User }
type DashboardData = Record<string, string | number | null>

const dashboardFor: Record<Role, string> = {
  APPLICANT: '/applicant',
  OFFICER: '/officer',
  ADMIN: '/admin',
}

const roleLabels: Record<Role, string> = {
  APPLICANT: 'Applicant',
  OFFICER: 'Department officer',
  ADMIN: 'Government administrator',
}

function redirect(path: string) {
  window.location.assign(path)
}

async function readError(response: Response) {
  const body = await response.json().catch(() => ({}))
  return body.detail ?? 'Something went wrong. Please try again.'
}

function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!response.ok) throw new Error(await readError(response))
      const result: AuthResult = await response.json()
      localStorage.setItem('mahaclear_access_token', result.access_token)
      redirect(dashboardFor[result.user.role])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to sign in.')
      setBusy(false)
    }
  }

  return (
    <AuthFrame eyebrow="WELCOME BACK" title="Your next step starts here."
      description="Sign in to your single-window approval workspace.">
      <form className="auth-form" onSubmit={submit}>
        <label>Email address<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" /></label>
        <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary-button full-width" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'} <span aria-hidden="true">→</span></button>
      </form>
      <p className="auth-switch">New to MAHACLEAR-AI? <a href="/register">Create an account</a></p>
      <DemoCredentials />
    </AuthFrame>
  )
}

function RegisterPage() {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [complete, setComplete] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: fullName, email, company_name: companyName || null, password }),
      })
      if (!response.ok) throw new Error(await readError(response))
      setComplete(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to create your account.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthFrame eyebrow="CREATE YOUR ACCOUNT" title={complete ? 'You’re ready to sign in.' : 'A clearer path begins with one account.'}
      description={complete ? 'Your applicant account has been created.' : 'Start with one profile. Your account will have applicant access.'}>
      {complete ? <div className="success-panel"><span className="success-mark">✓</span><p>Account created for <strong>{email}</strong>.</p><a className="primary-button full-width button-link" href="/login">Continue to sign in <span>→</span></a></div> : (
        <form className="auth-form" onSubmit={submit}>
          <label>Full name<input autoComplete="name" required minLength={2} maxLength={160} value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Your name" /></label>
          <label>Email address<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" /></label>
          <label>Company name <span className="optional-label">OPTIONAL</span><input autoComplete="organization" maxLength={200} value={companyName} onChange={(event) => setCompanyName(event.target.value)} placeholder="Your organization" /></label>
          <label>Password<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 12 characters" /><small>Use at least 12 characters.</small></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button full-width" type="submit" disabled={busy}>{busy ? 'Creating account…' : 'Create applicant account'} <span aria-hidden="true">→</span></button>
        </form>
      )}
      <p className="auth-switch">Already registered? <a href="/login">Sign in</a></p>
    </AuthFrame>
  )
}

function AuthFrame({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: ReactNode }) {
  return (
    <main className="auth-layout">
      <section className="auth-story">
        <Brand />
        <div className="story-copy"><span className="eyebrow"><i /> {eyebrow}</span><h1>{title}</h1><p>{description}</p></div>
        <div className="story-footer">ONE WINDOW. EVERY APPROVAL.</div>
      </section>
      <section className="auth-panel"><div className="mobile-brand"><Brand /></div><div className="auth-panel-inner">{children}</div></section>
    </main>
  )
}

function DemoCredentials() {
  return (
    <aside className="demo-box">
      <strong>Demo accounts</strong>
      <span>applicant@demo.com</span>
      <span>officer@demo.com</span>
      <span>admin@demo.com</span>
      <small>Password: <code>MahaClearDemo2026!</code></small>
    </aside>
  )
}

function Brand() {
  return <a className="brand" href="/login"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
}

function DashboardPage({ expectedRole }: { expectedRole: Role }) {
  const [user, setUser] = useState<User | null>(null)
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { redirect('/login'); return }
    const headers = { Authorization: `Bearer ${token}` }

    async function load() {
      try {
        const who = await fetch('/api/auth/me', { headers })
        if (!who.ok) throw new Error('Please sign in again.')
        const currentUser: User = await who.json()
        if (currentUser.role !== expectedRole) { redirect(dashboardFor[currentUser.role]); return }
        setUser(currentUser)

        const endpoint = expectedRole === 'APPLICANT' ? '/api/applicant/dashboard'
          : expectedRole === 'OFFICER' ? '/api/officer/department' : '/api/admin/overview'
        const dashboard = await fetch(endpoint, { headers })
        if (!dashboard.ok) throw new Error('Could not load your workspace.')
        setData(await dashboard.json())
      } catch (caught) {
        localStorage.removeItem('mahaclear_access_token')
        setError(caught instanceof Error ? caught.message : 'Could not load your workspace.')
      }
    }
    void load()
  }, [expectedRole])

  function signOut() {
    localStorage.removeItem('mahaclear_access_token')
    redirect('/login')
  }

  const role = expectedRole
  const title = role === 'APPLICANT' ? 'Applicant dashboard' : role === 'OFFICER' ? 'Department dashboard' : 'Government administration'
  const intro = role === 'APPLICANT' ? 'Your single-window workspace for industrial approvals.' : role === 'OFFICER' ? 'Your department workspace and assigned responsibilities.' : 'Your government administration workspace.'

  return (
    <div className="workspace">
      <header className="workspace-topbar"><Brand /><nav aria-label="Main navigation"><a className="nav-active" href={dashboardFor[role]}>Overview</a><a href="#account">Account</a></nav><button className="signout-button" onClick={signOut}>Sign out <span>↗</span></button></header>
      <aside className="workspace-sidebar"><div className="workspace-nav-label">WORKSPACE</div><a className="side-link selected" href={dashboardFor[role]}><span>◫</span> Overview</a><div className="sidebar-note"><span className="sidebar-note-mark">✳</span><strong>Faster, Smarter<br />Industrial Approvals</strong><small>North-Star · SIH 2026</small></div><div className="sidebar-bottom">MAHACLEAR-AI <span>·</span> v0.1</div></aside>
      <main className="workspace-main">
        <div className="breadcrumb">WORKSPACE <span>/</span> OVERVIEW</div>
        <div className="dashboard-heading"><div><span className="eyebrow"><i /> {roleLabels[role].toUpperCase()} WORKSPACE</span><h1>{title}</h1><p>{intro}</p></div><span className="access-badge">{roleLabels[role]}</span></div>
        {error ? <div className="workspace-error" role="alert">{error} <a href="/login">Sign in</a></div> : !user ? <div className="loading-panel">Loading your secure workspace…</div> : (
          <>
            <section className="welcome-card"><div><span className="card-kicker">WELCOME TO YOUR WORKSPACE</span><h2>Hello, {user.full_name.split(' ')[0]}.</h2><p>{role === 'APPLICANT' ? 'Your account is ready. Your approval workspace is set up for you.' : role === 'OFFICER' ? 'You’re signed in to your department workspace.' : 'Your government administration access is active.'}</p></div><div className="welcome-symbol" aria-hidden="true">{role === 'APPLICANT' ? '↗' : role === 'OFFICER' ? '▤' : '⌘'}</div></section>
            <div className="section-title"><div><span className="card-kicker">AT A GLANCE</span><h2>Your workspace</h2></div><span className="secure-label"><i /> SECURE SESSION</span></div>
            <section className="workspace-cards">
              <article className="workspace-card"><span className="workspace-card-icon green">{role === 'APPLICANT' ? '◎' : role === 'OFFICER' ? '▤' : '⌘'}</span><span className="card-kicker">ACCESS LEVEL</span><h3>{roleLabels[role]}</h3><p>Your role determines which workspace areas you can access.</p><span className="card-foot">ROLE VERIFIED <b>✓</b></span></article>
              <article className="workspace-card"><span className="workspace-card-icon sand">◷</span><span className="card-kicker">ACCOUNT</span><h3>{user.email}</h3><p>{role === 'OFFICER' ? `Department: ${String(data?.department ?? 'Not assigned')}` : role === 'ADMIN' ? `Registered users: ${String(data?.user_count ?? '—')}` : `Company: ${String(data?.company_id ? 'Linked to your profile' : 'Not added yet')}`}</p><span className="card-foot">ACCOUNT ACTIVE <b>✓</b></span></article>
            </section>
            <section className="next-panel"><span className="next-icon">i</span><div><strong>Your secure workspace is ready</strong><p>Approval application and review features will appear here as they are added.</p></div><span className="phase-tag">FOUNDATION PHASE</span></section>
          </>
        )}
      </main>
      <footer className="workspace-footer"><span>MAHACLEAR-AI <span>· Faster, Smarter Industrial Approvals</span></span><span>TEAM NORTH-STAR <i>·</i> SIH 2026</span></footer>
    </div>
  )
}

export default function App() {
  const path = window.location.pathname.replace(/\/$/, '') || '/'
  if (path === '/register') return <RegisterPage />
  if (path === '/login' || path === '/') return <LoginPage />
  if (path === '/applicant') return <ApplicantDashboard />
  if (path === '/applicant/applications/new') return <StartApplication />
  const prevalidationRoute = path.match(/^\/applicant\/applications\/(\d+)\/prevalidation$/)
  if (prevalidationRoute) return <PrevalidationPage applicationId={Number(prevalidationRoute[1])} />
  const riskRoute = path.match(/^\/applicant\/applications\/(\d+)\/risk$/)
  if (riskRoute) return <RiskAssessmentPage applicationId={Number(riskRoute[1])} />
  const approvalsRoute = path.match(/^\/applicant\/applications\/(\d+)\/approvals$/)
  if (approvalsRoute) return <ApprovalStatusPage applicationId={Number(approvalsRoute[1])} />
  const criticalPathRoute = path.match(/^\/applicant\/applications\/(\d+)\/critical-path$/)
  if (criticalPathRoute) return <CriticalPathPage applicationId={Number(criticalPathRoute[1])} />
  const applicationRoute = path.match(/^\/applicant\/applications\/(\d+)\/(edit|view)$/)
  if (applicationRoute) return <ApplicationWizard applicationId={Number(applicationRoute[1])} readOnly={applicationRoute[2] === 'view'} />
  const officerReviewRoute = path.match(/^\/officer\/approvals\/(\d+)$/)
  if (officerReviewRoute) return <OfficerPortal view="review" approvalId={Number(officerReviewRoute[1])} />
  const officerRoutes: Record<string, 'dashboard' | 'queue' | 'inspections' | 'joint-inspections' | 'documents' | 'escalations' | 'reports' | 'profile'> = {
    '/officer': 'dashboard', '/officer/queue': 'queue', '/officer/inspections': 'inspections',
    '/officer/joint-inspections': 'joint-inspections', '/officer/documents': 'documents',
    '/officer/escalations': 'escalations', '/officer/reports': 'reports', '/officer/profile': 'profile',
  }
  if (officerRoutes[path]) return <OfficerPortal view={officerRoutes[path]} />
  if (path === '/admin') return <DashboardPage expectedRole="ADMIN" />
  return <LoginPage />
}
