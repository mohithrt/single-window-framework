import { apiUrl } from './apiBase'
import { useEffect, useState } from 'react'
import type { RiskAssessment, RiskResponse } from './applicationTypes'

type Props = { applicationId: number }

async function readRiskResponse(response: Response): Promise<RiskResponse> {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Could not load the risk assessment.')
  return payload as RiskResponse
}

export default function RiskAssessmentPage({ applicationId }: Props) {
  const [result, setResult] = useState<RiskResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    setBusy(true)
    setError('')
    try {
      const response = await fetch(apiUrl(`/api/applications/${applicationId}/risk`), {
        headers: { Authorization: `Bearer ${token}` },
      })
      setResult(await readRiskResponse(response))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load the risk assessment.')
    } finally { setBusy(false) }
  }

  async function recalculate() {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    setBusy(true)
    setError('')
    try {
      const response = await fetch(apiUrl(`/api/applications/${applicationId}/risk/recalculate`), {
        method: 'POST', headers: { Authorization: `Bearer ${token}` },
      })
      setResult(await readRiskResponse(response))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not calculate risk.')
    } finally { setBusy(false) }
  }

  useEffect(() => { void load() }, [applicationId])

  if (!result && !error) return <main className="wizard-message"><span className="eyebrow"><i /> RISK TIERING</span><h1>Loading risk assessment…</h1></main>
  const assessment = result?.assessment ?? null

  return <div className="wizard-shell">
    <header className="wizard-topbar"><a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><div className="wizard-top-meta"><span>RISK ASSESSMENT</span><strong>Application {applicationId}</strong></div><a className="wizard-exit" href={`/applicant/applications/${applicationId}/edit?step=6`}>Back to review <span>↗</span></a></header>
    <main className="risk-main">
      <div className="wizard-heading"><div><span className="eyebrow"><i /> TRANSPARENT RULE-BASED REVIEW</span><h1>Risk assessment</h1><p>Every point comes from a disclosed factor and configurable scoring rule.</p></div><button className="primary-button" type="button" disabled={busy} onClick={() => void recalculate()}>{busy ? 'Calculating…' : assessment ? 'Recalculate risk' : 'Calculate risk'} <span>↻</span></button></div>
      {error && <div className="wizard-error" role="alert">{error}</div>}
      {!assessment ? <section className="risk-empty"><span className="submit-seal">◌</span><h2>No assessment saved yet</h2><p>Calculate a rules-based assessment for the current application details. Recalculations are saved as an assessment history.</p><button className="primary-button" type="button" disabled={busy} onClick={() => void recalculate()}>{busy ? 'Calculating…' : 'Calculate risk now'} <span>→</span></button></section> : <>
        {assessment.is_stale && <div className="risk-stale"><strong>Application details changed</strong><span>This saved score uses an earlier input snapshot. Recalculate to assess the current details.</span></div>}
        <section className={`risk-score-card tier-${assessment.risk_tier.toLowerCase()}`}>
          <div className="risk-score-number"><strong>{assessment.risk_score}</strong><span>/ 100</span></div>
          <div className="risk-score-detail"><span className="card-kicker">RULE-BASED RISK SCORE</span><h2><span className={`risk-tier-pill tier-${assessment.risk_tier.toLowerCase()}`}>{assessment.risk_tier}</span> risk</h2><div className="risk-score-track"><i style={{ width: `${assessment.risk_score}%` }} /></div><p>Raw factor total: {assessment.raw_score} points · Rules v{assessment.rules_version}</p></div>
        </section>
        <section className="risk-reasons-grid">
          <RiskFactorGroup title="Risk-increasing factors" kicker="ADDS POINTS" factors={assessment.positive_factors} empty="No configured risk-increasing factors matched." tone="high" />
          <RiskFactorGroup title="Low-risk factors" kicker="REDUCES POINTS" factors={assessment.low_risk_factors} empty="No configured low-risk factors matched." tone="low" />
        </section>
        <section className="risk-breakdown-panel"><div className="risk-panel-heading"><div><span className="card-kicker">HOW THE SCORE WAS BUILT</span><h2>Factor breakdown</h2></div><span className="risk-factor-count">{assessment.factor_breakdown.length} FACTORS</span></div>
          <div className="risk-factor-list">{assessment.factor_breakdown.map((factor) => <article className="risk-factor-row" key={factor.key}><div className={`risk-factor-points ${factor.points > 0 ? 'risk-points-up' : factor.points < 0 ? 'risk-points-down' : ''}`}>{factor.points > 0 ? '+' : ''}{factor.points}</div><div className="risk-factor-copy"><div><strong>{factor.label}</strong><span>{factor.value}</span></div><p>{factor.explanation}</p>{factor.signals.length > 0 && <small>Matched signals: {factor.signals.join(', ')}</small>}</div></article>)}</div>
        </section>
        <section className="risk-explanation"><span className="card-kicker">EXPLANATION &amp; LIMITS</span>{assessment.explanation.map((line) => <p key={line}>{line}</p>)}</section>
        <p className="risk-timestamp">Calculated {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(assessment.created_at))}</p>
      </>}
    </main>
  </div>
}

function RiskFactorGroup({ title, kicker, factors, empty, tone }: {
  title: string; kicker: string; factors: RiskAssessment['positive_factors']; empty: string; tone: 'high' | 'low'
}) {
  return <section className={`risk-reason-card risk-reason-${tone}`}><div><span className="card-kicker">{kicker}</span><h2>{title}</h2></div>{factors.length ? <ul>{factors.map((factor) => <li key={factor.key}><span>{factor.points > 0 ? '+' : ''}{factor.points}</span><div><strong>{factor.label}</strong><p>{factor.explanation}</p></div></li>)}</ul> : <p className="risk-reason-empty">{empty}</p>}</section>
}
