import { apiUrl } from './apiBase'
import { useEffect, useMemo, useState } from 'react'

type GraphNode = {
  id: string
  department_code: string | null
  department: string
  approval_name: string
  estimated_duration_days: number
  current_status: string
  dependencies: string[]
  start_date: string
  expected_completion: string
  display_state: 'completed' | 'current' | 'pending' | 'blocked'
  is_critical_path: boolean
  is_parallel: boolean
  is_blocked: boolean
  graph_level: number
  is_milestone?: boolean
}
type GraphEdge = { source: string; target: string }
type ParallelGroup = { start_day: number; approval_codes: string[]; department_names: string[] }
type CriticalPathData = {
  application_id: number
  application_number: string
  rules_version: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  critical_path: string[]
  parallel_approvals: ParallelGroup[]
  blocked_approvals: Array<{ id: string; department_name: string; blocked_by: string[]; status: string }>
  bottleneck: { department_code: string; department_name: string; estimated_duration_days: number; current_status: string } | null
  estimated_completion_days: number
  estimated_completion_date: string
}

const statusText: Record<GraphNode['display_state'], string> = {
  completed: 'Completed', current: 'Current', pending: 'Pending', blocked: 'Blocked',
}

export default function CriticalPathPage({ applicationId }: { applicationId: number }) {
  const [data, setData] = useState<CriticalPathData | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const token = localStorage.getItem('mahaclear_access_token')
    if (!token) { window.location.assign('/login'); return }
    void fetch(apiUrl(`/api/applications/${applicationId}/critical-path`), { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(body.detail || 'Unable to load the approval schedule.')
        setData(body)
      }).catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Unable to load the approval schedule.'))
  }, [applicationId])

  const layout = useMemo(() => {
    if (!data) return null
    const levels = new Map<number, GraphNode[]>()
    for (const node of data.nodes) {
      const current = levels.get(node.graph_level) ?? []
      current.push(node)
      levels.set(node.graph_level, current)
    }
    const orderedLevels = [...levels.keys()].sort((a, b) => a - b)
    const maxCount = Math.max(1, ...[...levels.values()].map((items) => items.length))
    const cardHeight = 126
    const rowGap = 32
    const height = Math.max(290, 96 + maxCount * (cardHeight + rowGap))
    const positions = new Map<string, { x: number; y: number }>()
    for (const [column, level] of orderedLevels.entries()) {
      const rows = levels.get(level) ?? []
      const total = rows.length * cardHeight + Math.max(0, rows.length - 1) * rowGap
      rows.forEach((node, index) => positions.set(node.id, {
        x: 70 + column * 286,
        y: (height - total) / 2 + index * (cardHeight + rowGap),
      }))
    }
    return { positions, width: Math.max(700, orderedLevels.length * 286 + 90), height }
  }, [data])

  return <div className="critical-page">
    <header className="approval-page-top"><a className="brand" href="/applicant"><span className="brand-mark">M</span><span>MAHA<span className="brand-accent">CLEAR</span><span className="brand-ai">.AI</span></span></a><a className="wizard-exit" href="/applicant">Dashboard <span>↗</span></a></header>
    <main className="critical-page-main">
      <div className="breadcrumb">APPLICANT WORKSPACE <span>/</span> CRITICAL PATH</div>
      {error ? <div className="applicant-error" role="alert">{error}</div> : !data ? <div className="loading-panel">Calculating the approval schedule…</div> : <>
        <div className="critical-heading"><div><span className="eyebrow"><i /> APPROVAL SCHEDULE</span><h1>Critical path & parallel reviews</h1><p>Estimated from this application’s approval dependencies and configured department review times.</p></div><div className="critical-number"><strong>{data.estimated_completion_days}</strong><span>days estimated</span><small>Target {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(`${data.estimated_completion_date}T00:00:00`))}</small></div></div>
        <section className="critical-summary-grid">
          <article className="critical-summary-card"><span className="card-kicker">BOTTLENECK</span><strong>{data.bottleneck?.department_name ?? 'No remaining bottleneck'}</strong><p>{data.bottleneck ? `${data.bottleneck.estimated_duration_days} estimated days · ${data.bottleneck.current_status.replaceAll('_', ' ')}` : 'All required approvals are complete.'}</p></article>
          <article className="critical-summary-card"><span className="card-kicker">CRITICAL PATH</span><strong>{data.critical_path.map((id) => data.nodes.find((node) => node.id === id)?.department ?? id).join(' → ')}</strong><p>Longest dependency chain to final clearance.</p></article>
        </section>
        <section className="critical-graph-panel">
          <div className="critical-panel-head"><div><span className="card-kicker">APPLICATION {data.application_number}</span><h2>Department dependency graph</h2></div><div className="critical-legend"><span><i className="completed"/>Completed</span><span><i className="current"/>Current</span><span><i className="pending"/>Pending</span><span><i className="blocked"/>Blocked</span><span><i className="critical"/>Critical path</span></div></div>
          {layout && <div className="critical-graph-scroll"><svg className="critical-graph" role="img" aria-label="Approval dependency graph generated from application records" viewBox={`0 0 ${layout.width} ${layout.height}`}>
            {data.edges.map((edge) => {
              const source = layout.positions.get(edge.source)
              const target = layout.positions.get(edge.target)
              if (!source || !target) return null
              const critical = data.critical_path.includes(edge.source) && data.critical_path.includes(edge.target)
              const x1 = source.x + 218
              const y1 = source.y + 63
              const x2 = target.x
              const y2 = target.y + 63
              const mid = (x1 + x2) / 2
              return <path key={`${edge.source}-${edge.target}`} className={`graph-edge ${critical ? 'on-critical-path' : ''}`} d={`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`} markerEnd={critical ? 'url(#arrow-critical)' : 'url(#arrow)'} />
            })}
            <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z" fill="#b9c6bf"/></marker><marker id="arrow-critical" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M 0 0 L 8 4 L 0 8 z" fill="#d39145"/></marker></defs>
            {data.nodes.map((node) => {
              const pos = layout.positions.get(node.id)
              if (!pos) return null
              return <g key={node.id} className={`graph-node ${node.display_state} ${node.is_critical_path ? 'critical-node' : ''} ${node.is_parallel ? 'parallel-node' : ''}`} transform={`translate(${pos.x}, ${pos.y})`}>
                <rect width="218" height="126" rx="10" />
                <text className="graph-node-title" x="14" y="25">{node.department}</text>
                <text className="graph-node-status" x="14" y="47">{statusText[node.display_state]} · {node.is_milestone ? 'Milestone' : `${node.estimated_duration_days} days`}</text>
                <text className="graph-node-date" x="14" y="70">Starts {new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short' }).format(new Date(`${node.start_date}T00:00:00`))}</text>
                <text className="graph-node-date" x="14" y="89">Due {new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short' }).format(new Date(`${node.expected_completion}T00:00:00`))}</text>
                {node.is_critical_path && <text className="graph-node-tag" x="14" y="111">CRITICAL PATH</text>}
                {node.is_parallel && <text className="graph-node-parallel" x="204" y="111" textAnchor="end">PARALLEL</text>}
              </g>
            })}
          </svg></div>}
        </section>
        <section className="critical-detail-grid">
          <article className="critical-detail-card"><span className="card-kicker">PARALLEL APPROVALS</span><h2>Reviews that can run together</h2>{data.parallel_approvals.length ? data.parallel_approvals.map((group) => <div className="parallel-group" key={`${group.start_day}-${group.approval_codes.join('-')}`}><small>Planned start: day {group.start_day + 1}</small><p>{group.department_names.join(' · ')}</p></div>) : <p className="critical-muted">No independent approval group is currently scheduled in parallel.</p>}</article>
          <article className="critical-detail-card"><span className="card-kicker">BLOCKED APPROVALS</span><h2>Waiting on dependencies</h2>{data.blocked_approvals.length ? data.blocked_approvals.map((approval) => <div className="blocked-row" key={approval.id}><strong>{approval.department_name}</strong><span>Waiting for {approval.blocked_by.join(', ')}</span></div>) : <p className="critical-muted">No approvals are blocked by an unfinished dependency.</p>}</article>
        </section>
        <p className="critical-method-note">Department durations come from workflow rules version {data.rules_version}. The graph uses the saved approval dependencies for this application; dates are planning estimates.</p>
      </>}
    </main>
  </div>
}
