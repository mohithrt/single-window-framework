import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import ApplicantDashboard from './ApplicantDashboard'
import ApplicantApplicationsPage from './ApplicantApplicationsPage'
import ApplicationWizard, { StartApplication } from './ApplicationWizard'
import ApplicationEntryPage from './ApplicationEntryPage'
import PrevalidationPage from './PrevalidationPage'
import RiskAssessmentPage from './RiskAssessmentPage'
import ApprovalStatusPage from './ApprovalStatusPage'
import CriticalPathPage from './CriticalPathPage'
import OfficerPortal from './OfficerPortal'
import NotificationCenterPage from './NotificationCenterPage'
import ApplicationActivityPage from './ApplicationActivityPage'
import AdminDashboardPage from './AdminDashboardPage'
import MahaClearAssistantPage from './MahaClearAssistantPage'
import { AdminApplicationPage, AdminAuditPage } from './AdminInspectionPages'
import ApplicantFeesPage from './ApplicantFeesPage'
import SystemHealthPage from './SystemHealthPage'
import AssistantFab from './AssistantFab'

type Role = 'APPLICANT' | 'OFFICER' | 'ADMIN'
type User = { id: number; email: string; full_name: string; role: Role }
type AuthResult = { access_token: string; user: User }

const dashboardFor: Record<Role, string> = {
  APPLICANT: '/applicant',
  OFFICER: '/officer',
  ADMIN: '/admin',
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

  async function demoLogin(role: 'APPLICANT' | 'OFFICER' | 'ADMIN') {
    const demoAccounts = {
      APPLICANT: 'applicant@demo.com',
      OFFICER: 'officer@demo.com',
      ADMIN: 'admin@demo.com',
    } as const
    setError('')
    setBusy(true)
    setEmail(demoAccounts[role])
    setPassword('MahaClearDemo2026!')
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: demoAccounts[role], password: 'MahaClearDemo2026!' }),
      })
      if (!response.ok) throw new Error(await readError(response))
      const result: AuthResult = await response.json()
      localStorage.setItem('mahaclear_access_token', result.access_token)
      redirect(dashboardFor[result.user.role])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to start demo.')
      setBusy(false)
    }
  }

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
      <DemoCredentials onDemoLogin={demoLogin} busy={busy} />
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

function DemoCredentials({ onDemoLogin, busy }: { onDemoLogin: (role: 'APPLICANT' | 'OFFICER' | 'ADMIN') => void; busy: boolean }) {
  return (
    <aside className="demo-box">
      <div className="demo-heading"><strong>Instant demo access</strong><small>No registration required</small></div>
      <div className="demo-actions">
        <button type="button" onClick={() => onDemoLogin('APPLICANT')} disabled={busy}>Applicant demo <span>→</span></button>
        <button type="button" onClick={() => onDemoLogin('OFFICER')} disabled={busy}>Officer demo <span>→</span></button>
        <button type="button" onClick={() => onDemoLogin('ADMIN')} disabled={busy}>Admin demo <span>→</span></button>
      </div>
      <small className="demo-password">Demo password: <code>MahaClearDemo2026!</code></small>
    </aside>
  )
}

function WorkspacePage({ children, applicationId }: { children: ReactNode; applicationId?: number }) {
  return <><>{children}</><AssistantFab applicationId={applicationId} /></>
}

function Brand() {
  return <a className="brand" href="/login"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a>
}

export default function App() {
  const path = window.location.pathname.replace(/\/$/, '') || '/'
  if (path === '/register') return <RegisterPage />
  if (path === '/login' || path === '/') return <LoginPage />
  if (path === '/notifications') return <WorkspacePage><NotificationCenterPage /></WorkspacePage>
  if (path === '/applicant') return <WorkspacePage><ApplicantDashboard /></WorkspacePage>
  if (path === '/applicant/applications') return <WorkspacePage><ApplicantApplicationsPage /></WorkspacePage>
  if (path === '/applicant/fees') return <WorkspacePage><ApplicantFeesPage /></WorkspacePage>
  if (path === '/applicant/applications/new') return <WorkspacePage><ApplicationEntryPage /></WorkspacePage>
  const prevalidationRoute = path.match(/^\/applicant\/applications\/(\d+)\/prevalidation$/)
  if (prevalidationRoute) { const applicationId = Number(prevalidationRoute[1]); return <WorkspacePage applicationId={applicationId}><PrevalidationPage applicationId={applicationId} /></WorkspacePage> }
  const riskRoute = path.match(/^\/applicant\/applications\/(\d+)\/risk$/)
  if (riskRoute) { const applicationId = Number(riskRoute[1]); return <WorkspacePage applicationId={applicationId}><RiskAssessmentPage applicationId={applicationId} /></WorkspacePage> }
  const approvalsRoute = path.match(/^\/applicant\/applications\/(\d+)\/approvals$/)
  if (approvalsRoute) { const applicationId = Number(approvalsRoute[1]); return <WorkspacePage applicationId={applicationId}><ApprovalStatusPage applicationId={applicationId} /></WorkspacePage> }
  const criticalPathRoute = path.match(/^\/applicant\/applications\/(\d+)\/critical-path$/)
  if (criticalPathRoute) { const applicationId = Number(criticalPathRoute[1]); return <WorkspacePage applicationId={applicationId}><CriticalPathPage applicationId={applicationId} /></WorkspacePage> }
  const assistantRoute = path.match(/^\/applicant\/applications\/(\d+)\/assistant$/)
  if (assistantRoute) return <WorkspacePage applicationId={Number(assistantRoute[1])}><MahaClearAssistantPage applicationId={Number(assistantRoute[1])} /></WorkspacePage>
  const activityRoute = path.match(/^\/applicant\/applications\/(\d+)\/activity$/)
  if (activityRoute) { const applicationId = Number(activityRoute[1]); return <WorkspacePage applicationId={applicationId}><ApplicationActivityPage applicationId={applicationId} /></WorkspacePage> }
  const applicationRoute = path.match(/^\/applicant\/applications\/(\d+)\/(edit|view)$/)
  if (applicationRoute) { const applicationId = Number(applicationRoute[1]); return <WorkspacePage applicationId={applicationId}><ApplicationWizard applicationId={applicationId} readOnly={applicationRoute[2] === 'view'} /></WorkspacePage> }
  const officerReviewRoute = path.match(/^\/officer\/approvals\/(\d+)$/)
  if (officerReviewRoute) return <WorkspacePage><OfficerPortal view="review" approvalId={Number(officerReviewRoute[1])} /></WorkspacePage>
  const officerRoutes: Record<string, 'dashboard' | 'queue' | 'inspections' | 'joint-inspections' | 'documents' | 'escalations' | 'reports' | 'profile'> = {
    '/officer': 'dashboard', '/officer/queue': 'queue', '/officer/inspections': 'inspections',
    '/officer/joint-inspections': 'joint-inspections', '/officer/documents': 'documents',
    '/officer/escalations': 'escalations', '/officer/reports': 'reports', '/officer/profile': 'profile',
  }
  if (officerRoutes[path]) return <WorkspacePage><OfficerPortal view={officerRoutes[path]} /></WorkspacePage>
  const adminApplicationRoute = path.match(/^\/admin\/applications\/(\d+)$/)
  if (adminApplicationRoute) return <WorkspacePage><AdminApplicationPage applicationId={Number(adminApplicationRoute[1])} /></WorkspacePage>
  if (path === '/admin/audit') return <WorkspacePage><AdminAuditPage /></WorkspacePage>
  if (path === '/admin/system-health') return <WorkspacePage><SystemHealthPage /></WorkspacePage>
  if (path === '/admin') return <WorkspacePage><AdminDashboardPage /></WorkspacePage>
  return <LoginPage />
}
