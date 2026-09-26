import { apiUrl } from './apiBase'
import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import ApplicantDashboard from './ApplicantDashboard'
import ApplicationWizard, { StartApplication } from './ApplicationWizard'
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const response = await fetch(apiUrl('/api/auth/login'), {
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
      {import.meta.env.DEV && <DemoCredentials />}
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
      const response = await fetch(apiUrl('/api/auth/register'), {
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

export default function App() {
  const path = window.location.pathname.replace(/\/$/, '') || '/'
  if (path === '/register') return <RegisterPage />
  if (path === '/login' || path === '/') return <LoginPage />
  if (path === '/notifications') return <NotificationCenterPage />
  if (path === '/applicant') return <ApplicantDashboard />
  if (path === '/applicant/fees') return <ApplicantFeesPage />
  if (path === '/applicant/applications/new') return <StartApplication />
  const prevalidationRoute = path.match(/^\/applicant\/applications\/(\d+)\/prevalidation$/)
  if (prevalidationRoute) return <PrevalidationPage applicationId={Number(prevalidationRoute[1])} />
  const riskRoute = path.match(/^\/applicant\/applications\/(\d+)\/risk$/)
  if (riskRoute) return <RiskAssessmentPage applicationId={Number(riskRoute[1])} />
  const approvalsRoute = path.match(/^\/applicant\/applications\/(\d+)\/approvals$/)
  if (approvalsRoute) return <ApprovalStatusPage applicationId={Number(approvalsRoute[1])} />
  const criticalPathRoute = path.match(/^\/applicant\/applications\/(\d+)\/critical-path$/)
  if (criticalPathRoute) return <CriticalPathPage applicationId={Number(criticalPathRoute[1])} />
  const assistantRoute = path.match(/^\/applicant\/applications\/(\d+)\/assistant$/)
  if (assistantRoute) return <MahaClearAssistantPage applicationId={Number(assistantRoute[1])} />
  const activityRoute = path.match(/^\/applicant\/applications\/(\d+)\/activity$/)
  if (activityRoute) return <ApplicationActivityPage applicationId={Number(activityRoute[1])} />
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
  const adminApplicationRoute = path.match(/^\/admin\/applications\/(\d+)$/)
  if (adminApplicationRoute) return <AdminApplicationPage applicationId={Number(adminApplicationRoute[1])} />
  if (path === '/admin/audit') return <AdminAuditPage />
  if (path === '/admin') return <AdminDashboardPage />
  return <LoginPage />
}
