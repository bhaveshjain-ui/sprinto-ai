import { useCallback, useEffect, useState } from 'react'

const api = async (path, opts = {}) => {
  const r = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
  return data
}

function useData(path, deps = []) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const load = useCallback(() => api(path).then(setData).catch((e) => setErr(e.message)), [path])
  useEffect(() => { load() }, [load, ...deps])
  return [data, load, err]
}

/* ---------- palette ---------- */
const C = { violet: '#c59d5f', fuchsia: '#8f6a33', emerald: '#6a9a22', amber: '#e4b432', rose: '#d04a2a',
  sky: '#5b8de0', slate: '#cfc7b8', indigo: '#19191b' }

/* ---------- charts (plain SVG, no deps) ---------- */
function Donut({ data, size = 170, center, sub }) {
  const total = data.reduce((a, d) => a + d.value, 0)
  const r = 52, circ = 2 * Math.PI * r
  let offset = 0
  return <div className="flex items-center gap-5 flex-wrap">
    <svg width={size} height={size} viewBox="0 0 140 140">
      <circle cx="70" cy="70" r={r} fill="none" stroke="#efe7d9" strokeWidth="20" />
      {total > 0 && data.map((d) => {
        const len = (d.value / total) * circ
        const el = <circle key={d.label} cx="70" cy="70" r={r} fill="none" stroke={d.color} strokeWidth="20"
          strokeDasharray={`${len} ${circ - len}`} strokeDashoffset={-offset} transform="rotate(-90 70 70)" />
        offset += len
        return el
      })}
      <text x="70" y="68" textAnchor="middle" className="fill-slate-900" style={{ fontSize: 26, fontWeight: 800 }}>{center ?? total}</text>
      <text x="70" y="86" textAnchor="middle" className="fill-slate-500" style={{ fontSize: 10 }}>{sub ?? 'total'}</text>
    </svg>
    <div className="space-y-1.5 text-sm">{data.map((d) => <div key={d.label} className="flex items-center gap-2">
      <span className="w-3 h-3 rounded-full" style={{ background: d.color }} /><span className="text-slate-600">{d.label}</span>
      <b className="ml-auto pl-4">{d.value}</b></div>)}</div>
  </div>
}

function Gauge({ value = 0, size = 96 }) {
  const color = value >= 75 ? C.emerald : value >= 55 ? C.amber : C.rose
  const r = 38, circ = 2 * Math.PI * r, len = (Math.min(value, 100) / 100) * circ
  return <svg width={size} height={size} viewBox="0 0 100 100">
    <circle cx="50" cy="50" r={r} fill="none" stroke="#efe7d9" strokeWidth="12" />
    <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
      strokeDasharray={`${len} ${circ - len}`} transform="rotate(-90 50 50)" />
    <text x="50" y="58" textAnchor="middle" style={{ fontSize: 26, fontWeight: 800 }} fill={color}>{Math.round(value)}</text>
  </svg>
}

function HBars({ rows }) {
  return <div className="space-y-2">{rows.map((r) => <div key={r.label}>
    <div className="flex justify-between text-xs mb-0.5"><span className="font-medium text-slate-700">{r.label}</span>
      <span className="text-slate-500">{r.right}</span></div>
    <div className="h-3 rounded-full bg-slate-200 overflow-hidden"><div className="h-full rounded-full transition-all"
      style={{ width: `${Math.max(r.pct, r.pct > 0 ? 3 : 0)}%`, background: r.color }} /></div></div>)}</div>
}

/* ---------- primitives ---------- */
const Card = ({ title, children, right }) => (
  <section className="bg-white rounded-2xl border border-[#f0e9dc] shadow-[0_6px_24px_rgba(90,60,10,0.06)] mb-6">
    <div className="p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-lg text-[#19191b]">{title}</h2>{right}
      </div>
      {children}
    </div>
  </section>
)
const Btn = ({ children, kind = 'default', ...p }) => (
  <button {...p} className={'px-4 py-2 rounded-xl text-sm font-semibold transition disabled:opacity-50 ' + ({
    default: 'bg-white border border-[#e4dccb] text-[#19191b] hover:border-[#c59d5f] hover:text-[#8f6a33] shadow-sm',
    primary: 'bg-[#c59d5f] text-white shadow-md shadow-[#c59d5f]/30 hover:bg-[#b38848]',
    success: 'bg-[#6a9a22] text-white shadow-md shadow-[#6a9a22]/25 hover:bg-[#587f1a]',
    danger: 'bg-white border border-[#e8b4a6] text-[#b23a1e] hover:bg-[#fbebe6]',
  }[kind])}>{children}</button>
)
const BADGE = { VERIFIED: 'bg-emerald-500 text-white', qualified: 'bg-emerald-500 text-white', High: 'bg-emerald-500 text-white',
  sent: 'bg-emerald-500 text-white', Medium: 'bg-amber-400 text-amber-950', further_investigation: 'bg-amber-400 text-amber-950',
  STALE: 'bg-amber-400 text-amber-950', pending: 'bg-amber-400 text-amber-950', ASSERTED: 'bg-rose-500 text-white',
  rejected: 'bg-rose-500 text-white', stopped: 'bg-rose-500 text-white', failed: 'bg-rose-500 text-white',
  Low: 'bg-slate-400 text-white', NOT_FOUND: 'bg-slate-300 text-slate-700', approved: 'bg-sky-500 text-white',
  lead: 'bg-violet-500 text-white', drafted: 'bg-fuchsia-500 text-white', shortlisted: 'bg-indigo-500 text-white',
  researched: 'bg-sky-500 text-white', filtered: 'bg-slate-400 text-white', promising: 'bg-amber-400 text-amber-950', needs_data: 'bg-slate-400 text-white', low_priority: 'bg-slate-400 text-white', no_draft: 'bg-amber-400 text-amber-950', no_contact: 'bg-amber-400 text-amber-950', dry_run: 'bg-slate-400 text-white' }
const Badge = ({ v }) => <span className={'px-2.5 py-0.5 rounded-full text-xs font-bold ' + (BADGE[v] || 'bg-slate-200 text-slate-700')}>{String(v).replaceAll('_', ' ')}</span>
const Link = ({ href }) => href ? <a className="text-violet-600 hover:text-fuchsia-600 underline break-all" href={href} target="_blank" rel="noreferrer">{href}</a> : '-'

function Sources({ urls }) {
  const [show, setShow] = useState(false)
  const real = (urls || []).filter((u) => !u.includes('vertexaisearch.cloud.google.com'))
  return <div>
    <Btn onClick={() => setShow(!show)}>{show ? 'Hide sources' : `Sources (${real.length})`}</Btn>
    {show && <div className="mt-2 space-y-1 text-xs">{real.map((u) => <div key={u}><Link href={u} /></div>)}</div>}
  </div>
}

function Jobs() {
  const [jobs, setJobs] = useState({})
  useEffect(() => { const t = setInterval(() => api('/jobs').then(setJobs).catch(() => {}), 2000); return () => clearInterval(t) }, [])
  const list = Object.entries(jobs).filter(([, j]) => j.running || j.error)
  if (!list.length) return null
  return <div className="mb-5 space-y-2">{list.map(([k, j]) => (
    <div key={k} className={'text-sm font-medium rounded-xl px-4 py-3 text-white ' + (j.error ? 'bg-rose-500' : 'bg-gradient-to-r from-indigo-500 to-violet-500 animate-pulse')}>
      <div className="flex items-center gap-3"><span className="flex-1"><b>{k === 'process' ? 'Background research' : k}</b>: {j.error ? 'error - ' + j.error : j.message}</span>
        {j.running && !j.error && <button onClick={() => api('/jobs/' + k + '/stop', { method: 'POST' })} className="px-3 py-1 rounded-lg bg-black/30 hover:bg-black/50 text-xs font-semibold">{j.cancel ? 'Stopping...' : 'Stop'}</button>}</div></div>))}</div>
}

/* ---------- pages ---------- */
function Overview() {
  const [d, load] = useData('/overview')
  useEffect(() => { const t = setInterval(load, 4000); return () => clearInterval(t) }, [load])
  const [domains, setDomains] = useState('')
  const [msg, setMsg] = useState('')
  const run = async (fn) => { try { setMsg(''); await fn(); load() } catch (e) { setMsg(e.message) } }
  const tiles = d && [
    ['Discovered', d.discovered, 'from-violet-600 to-indigo-500'], ['Researched', d.researched, 'from-sky-500 to-cyan-400'],
    ['Qualified', d.qualified, 'from-emerald-500 to-teal-400'], ['Further investigation', d.further_investigation, 'from-amber-500 to-orange-400'],
    ['Rejected', d.rejected, 'from-rose-500 to-pink-500'], ['High-priority leads', d.high_priority, 'from-fuchsia-600 to-purple-500'],
    ['Pending approvals', d.pending_approvals, 'from-indigo-600 to-blue-500'], ['Emails sent', d.sent, 'from-teal-500 to-emerald-400']]
  const unscored = d ? Math.max(d.discovered - d.qualified - d.further_investigation - d.rejected, 0) : 0
  const funnel = d && [['Discovered', d.discovered, C.violet], ['Researched', d.researched, C.sky], ['Qualified', d.qualified, C.emerald],
    ['High priority', d.high_priority, C.fuchsia], ['Pending approval', d.pending_approvals, C.indigo], ['Sent', d.sent, C.amber]]
  const top = d ? Math.max(d.discovered, 1) : 1
  return <>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">{tiles?.map(([k, v], i) => (
      <div key={k} className="bg-white rounded-2xl border border-[#f0e9dc] shadow-[0_6px_24px_rgba(90,60,10,0.06)] p-4 flex items-center gap-3">
        <div className="w-11 h-11 rounded-xl bg-[#f6efe4] text-[#b38848] flex items-center justify-center text-lg font-bold shrink-0">{['◈', '⌕', '★', '◎', '✕', '▲', '✉', '➤'][i]}</div>
        <div><div className="text-2xl font-bold text-[#19191b] leading-none">{v}</div><div className="text-xs text-slate-500 mt-1">{k}</div></div></div>))}</div>
    {d && <div className="grid lg:grid-cols-2 gap-6">
      <Card title="Outcome split" accent="from-emerald-400 to-teal-500"><Donut center={d.discovered} sub="companies" data={[
        { label: 'Qualified', value: d.qualified, color: C.emerald }, { label: 'Further investigation', value: d.further_investigation, color: C.amber },
        { label: 'Rejected', value: d.rejected, color: C.rose }, { label: 'Being researched / queued', value: d.in_queue, color: C.sky }, { label: 'Filtered at shortlist', value: d.filtered_out, color: C.slate }]} /></Card>
      <Card title="Pipeline funnel" accent="from-sky-400 to-indigo-500"><HBars rows={funnel.map(([label, v, color]) => ({ label, right: v, pct: (v / top) * 100, color }))} /></Card>
    </div>}
    <section className="rounded-2xl bg-[#c59d5f] text-white p-6 mb-6 shadow-[0_8px_26px_rgba(197,157,95,0.35)]">
      <h2 className="text-2xl font-semibold">Welcome back, Bhavesh!</h2>
      <p className="text-sm text-white/85 mt-1">{d ? `${d.pending_approvals} drafts are waiting for your review.` : ' '} Run the pipeline or add company domains below.</p>
      <div className="flex flex-wrap gap-3 mt-4 mb-4">
        <button className="px-4 py-2 rounded-xl bg-white text-[#19191b] text-sm font-semibold shadow-sm hover:shadow-md" onClick={() => run(() => api('/autonomous', { method: 'POST' }))}>Autonomous discovery + full run</button>
        <button className="px-4 py-2 rounded-xl bg-white text-[#19191b] text-sm font-semibold shadow-sm hover:shadow-md" onClick={() => run(() => api('/discover', { method: 'POST' }))}>Discover &amp; shortlist only</button>
        <button className="px-4 py-2 rounded-xl bg-white text-[#19191b] text-sm font-semibold shadow-sm hover:shadow-md" onClick={() => run(() => api('/companies/process', { method: 'POST' }))}>Process shortlisted</button>
      </div>
      <textarea className="w-full rounded-xl p-3 text-sm text-[#19191b] placeholder-slate-400 outline-none" rows="2" value={domains}
        onChange={(e) => setDomains(e.target.value)} placeholder="Company domains, one per line or comma-separated: acme.com, example.io" />
      <div className="mt-3 flex items-center gap-3"><button className="px-4 py-2 rounded-xl bg-[#19191b] text-white text-sm font-semibold" onClick={() => run(async () => {
        const r = await api('/companies/manual', { method: 'POST', body: { domains: domains.split(/[\s,]+/).filter(Boolean) } })
        setMsg(`Added ${r.added.length}` + (r.invalid.length ? `; invalid: ${r.invalid.join(', ')}` : '') + '. Click "Process shortlisted".'); setDomains('')
      })}>Add domains</button>{msg && <span className="text-sm text-white font-medium">{msg}</span>}</div>
    </section>
  </>
}

function Icp() {
  const [d, load] = useData('/icp')
  const [busy, setBusy] = useState(false)
  const r = d?.report
  const H = ({ children, c = 'text-violet-700' }) => <h3 className={'font-bold mb-2 ' + c}>{children}</h3>
  return <Card title="ICP research report" right={<Btn kind="primary" disabled={busy} onClick={async () => {
    setBusy(true); await api('/icp/run', { method: 'POST' }).catch(() => {}); setTimeout(() => { load(); setBusy(false) }, 15000) }}>
    {busy ? 'Generating...' : 'Regenerate'}</Btn>}>
    {!r ? <p className="text-sm text-slate-500">No report yet. Generate one (needs GEMINI_API_KEY).</p> : <div className="space-y-5 text-sm">
      <p className="text-base bg-gradient-to-r from-violet-50 to-fuchsia-50 rounded-xl p-4 text-slate-700">{r.summary}</p>
      <div className="grid md:grid-cols-2 gap-5">
        <div className="rounded-xl bg-indigo-50 p-4"><H c="text-indigo-700">Industries</H><ul className="space-y-1.5">{r.industries?.map((i, k) => <li key={k}><b>{i.name}</b>: {i.why}</li>)}</ul></div>
        <div className="rounded-xl bg-emerald-50 p-4"><H c="text-emerald-700">Buying signals</H><ul className="space-y-1.5">{r.buying_signals?.map((s, k) => <li key={k}><b>{s.signal}</b>: {s.why_it_matters}</li>)}</ul></div>
        <div className="rounded-xl bg-amber-50 p-4"><H c="text-amber-700">Compliance triggers</H><ul className="list-disc ml-5 space-y-1">{r.compliance_triggers?.map((s, k) => <li key={k}>{s}</li>)}</ul></div>
        <div className="rounded-xl bg-fuchsia-50 p-4"><H c="text-fuchsia-700">Enterprise expansion signals</H><ul className="list-disc ml-5 space-y-1">{r.enterprise_expansion_signals?.map((s, k) => <li key={k}>{s}</li>)}</ul></div>
      </div>
      <div className="rounded-xl bg-sky-50 p-4"><H c="text-sky-700">Funding stages</H><p>{r.funding_stages}</p></div>
      <Sources urls={d.sources} />
    </div>}
  </Card>
}

const STATE_COLOR = { positive: C.emerald, negative: C.rose, unverified: C.slate, conflict: C.amber }

function CompanyDetail({ id, onClose }) {
  const [d, load] = useData('/companies/' + id)
  if (!d) return <p>Loading...</p>
  const { company: c } = d
  const counts = ['VERIFIED', 'STALE', 'ASSERTED', 'NOT_FOUND'].map((s) => ({ label: s, value: d.facts.filter((f) => f.status === s).length,
    color: { VERIFIED: C.emerald, STALE: C.amber, ASSERTED: C.rose, NOT_FOUND: C.slate }[s] }))
  const detail = c.score_detail?.detail
  return <>
    <Card title={`${c.name} (${c.domain})`} right={<div className="flex gap-2">
      <Btn onClick={() => api(`/companies/${id}/process`, { method: 'POST' }).then(() => setTimeout(load, 3000))}>Re-research &amp; re-score</Btn>
      <Btn onClick={onClose}>Close</Btn></div>}>
      <div className="flex items-center gap-6 flex-wrap">
        <Gauge value={c.score ?? 0} size={110} />
        <div className="space-y-2"><div className="flex gap-2 items-center">{c.classification && <Badge v={c.classification} />}{c.priority && <Badge v={c.priority} />}<Badge v={c.status} /></div>
          {c.stop_reason && <div className="text-rose-600 font-medium text-sm">Stopped: {c.stop_reason}</div>}
          {c.score_detail && <p className="text-slate-600 text-sm max-w-xl">{c.score_detail.reason}</p>}</div>
        <div className="ml-auto"><Donut size={130} data={counts} sub="facts" /></div>
      </div>
    </Card>
    {detail && <Card title="Score breakdown" accent="from-emerald-400 to-sky-500"><HBars rows={Object.entries(detail).filter(([, v]) => v.max > 0).map(([k, v]) => ({
      label: k.replaceAll('_', ' '), right: `${v.points}/${v.max} - ${v.explanation}`, pct: (v.points / v.max) * 100, color: STATE_COLOR[v.state] }))} />
      <div className="flex gap-4 mt-3 text-xs text-slate-600">{Object.entries(STATE_COLOR).map(([k, col]) => <span key={k} className="flex items-center gap-1"><i className="w-3 h-3 rounded-full inline-block" style={{ background: col }} />{k}</span>)}</div></Card>}
    {c.intent?.signals?.length > 0 && <Card title="Buying signals" accent="from-fuchsia-400 to-rose-500"><div className="flex gap-2 flex-wrap">
      {c.intent.signals.map((s, k) => <span key={k} className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-fuchsia-500 to-violet-500 text-white text-sm font-semibold">{s.type.replaceAll('_', ' ')} <span className="opacity-75">(facts {s.fact_ids.join(', ')})</span></span>)}</div></Card>}
    <Card title="Research evidence" accent="from-sky-400 to-indigo-500"><div className="overflow-x-auto"><table className="w-full text-xs"><thead className="text-left text-slate-500 uppercase">
      <tr><th className="pb-2">Criterion</th><th>Value</th><th>Status</th><th>Source</th><th>Published</th><th>Retrieved</th><th>Attempt</th><th>Snippet</th></tr></thead><tbody>
      {d.facts.map((f) => <tr key={f.id} className="border-t border-slate-100 align-top">
        <td className="py-2 pr-2 font-semibold">{f.criterion}</td><td className="pr-2">{f.value || 'UNVERIFIED'}</td>
        <td className="pr-2"><Badge v={f.status} />{f.conflict ? ' conflict' : ''}<div className="text-slate-500 mt-1">{f.status_reason}</div></td>
        <td className="pr-2 max-w-48"><Link href={f.source_url} /></td><td className="pr-2">{f.page_date || '-'}</td>
        <td className="pr-2">{(f.retrieved_at || '').slice(0, 10)}</td><td className="pr-2">{f.attempt ?? '-'} {f.method}</td>
        <td className="max-w-64 text-slate-600">{f.snippet}</td></tr>)}</tbody></table></div></Card>
    <div className="grid lg:grid-cols-2 gap-6">
      <Card title="Research attempts" accent="from-amber-400 to-orange-500">{d.research_log.map((l) => <div key={l.id} className="text-xs text-slate-600 py-0.5">
        <b className="text-slate-800">#{l.attempt}</b> {l.method} - {l.criterion}: <span className={l.outcome === 'verified' ? 'text-emerald-600 font-bold' : 'text-rose-500'}>{l.outcome}</span></div>)}</Card>
      <Card title="Decision log" accent="from-indigo-400 to-violet-500">{d.decisions.map((l) => <div key={l.id} className="text-xs text-slate-600 py-0.5">{l.created_at} <b>[{l.stage}]</b> {l.decision} - {l.detail}</div>)}</Card>
    </div>
    <Card title="Discovery sources" accent="from-teal-400 to-emerald-500">{c.discover_sources?.map((s, k) => <div key={k} className="text-xs mb-2">{s.trigger} <Link href={s.url} /></div>)}</Card>
  </>
}

// What happened to the company, in plain words (the raw status 'further_investigation' now only means "scored below 55").
const statusLabel = (c) => c.status === 'stopped'
  ? ({ shortlist: 'filtered', score: 'rejected', intent: 'low_priority', contact: 'no_contact', draft: 'no_draft' }[c.stage] || 'stopped')
  : c.status === 'further_investigation' ? 'needs_data' : c.status

function Research() {
  const [list, load] = useData('/companies')
  const [open, setOpen] = useState(null)
  useEffect(() => { const t = setInterval(load, 5000); return () => clearInterval(t) }, [load])
  if (open) return <CompanyDetail id={open} onClose={() => setOpen(null)} />
  return <Card title="Companies">
    <table className="w-full text-sm"><thead className="text-left text-slate-500 uppercase text-xs"><tr><th className="pb-2">Company</th><th>Origin</th><th>Status</th><th>Score</th><th>Class</th><th>Priority</th><th>Why stopped</th></tr></thead>
      <tbody>{list?.map((c) => <tr key={c.id} className="border-t border-slate-100 cursor-pointer hover:bg-violet-50" onClick={() => setOpen(c.id)}>
        <td className="py-2.5"><b>{c.name}</b><div className="text-xs text-slate-500">{c.domain}</div></td><td>{c.origin}</td><td><Badge v={statusLabel(c)} /></td>
        <td>{c.score != null ? <div className="flex items-center gap-2 w-28"><div className="flex-1 h-2.5 bg-slate-200 rounded-full overflow-hidden"><div className="h-full rounded-full" style={{ width: c.score + '%', background: c.score >= 75 ? C.emerald : c.score >= 55 ? C.amber : C.rose }} /></div><b>{c.score}</b></div> : '-'}</td>
        <td>{c.classification && <Badge v={c.classification === 'further_investigation' ? (c.score >= 55 ? 'promising' : 'needs_data') : c.classification} />}
          {c.classification === 'further_investigation' && c.missing?.length > 0 && <div className="text-[11px] text-slate-500 mt-1 max-w-48">Missing: {c.missing.map((m) => m.replaceAll('_', ' ')).join(', ')}</div>}</td><td>{c.priority && <Badge v={c.priority} />}</td>
        <td className="text-slate-600 max-w-72 text-xs">{c.stop_reason}</td></tr>)}</tbody></table>
    {list?.length === 0 && <p className="text-sm text-slate-500">No companies yet. Run discovery or add domains on Overview.</p>}
  </Card>
}

function Leads() {
  const [list] = useData('/leads')
  return <>{list?.map((l) => <Card key={l.id} title={`${l.name} (${l.domain})`} accent="from-emerald-400 to-teal-500" right={<div className="flex gap-3 items-center"><Badge v={l.priority} /><Gauge value={l.score} size={70} /></div>}>
    <div className="grid md:grid-cols-2 gap-5 text-sm">
      <div className="rounded-xl bg-indigo-50 p-4"><h3 className="font-bold text-indigo-700 mb-2">Decision-maker</h3>{l.contacts.map((c) => <div key={c.id}>
        <div className="text-base"><b>{c.first_name} {c.last_name}</b>, {c.position}</div><div className="text-violet-700">{c.email}</div>
        <div className="mt-1 flex gap-2"><Badge v={c.verification === 'valid' ? 'VERIFIED' : 'STALE'} /><span className="text-slate-600">Hunter confidence <b>{c.confidence}</b></span></div>
        <div className="text-slate-600 text-xs mt-2">{c.reasoning}</div></div>)}</div>
      <div className="rounded-xl bg-fuchsia-50 p-4"><h3 className="font-bold text-fuchsia-700 mb-2">Pain points</h3>{l.intent.pain_points?.map((p, k) => <div key={k} className="mb-3">
        <div><b>Evidence:</b> {p.pain} <span className="text-slate-500">(facts {p.evidence_fact_ids.join(', ')})</span></div>
        <div className="text-slate-600"><b>Interpretation:</b> {p.interpretation}</div></div>)}</div>
    </div></Card>)}
    {list?.length === 0 && <p className="text-sm text-slate-500">No qualified leads yet.</p>}</>
}

function Review() {
  const [allDrafts, load] = useData('/drafts')
  const [filter, setFilter] = useState('open')
  const [edit, setEdit] = useState({})
  const [msg, setMsg] = useState({})
  const [confirming, setConfirming] = useState(null)
  const [settings] = useData('/settings')
  const recipient = settings?.recipient
  const reload = () => load()
  const act = async (id, fn) => { try { setMsg((m) => ({ ...m, [id]: '' })); const r = await fn(); setMsg((m) => ({ ...m, [id]: r?.status ? 'Result: ' + r.status + (r.error ? ' - ' + r.error : '') : '' })); reload() } catch (e) { setMsg((m) => ({ ...m, [id]: e.message })) } }
  const groups = { open: ['pending', 'approved'], sent: ['sent', 'failed'], rejected: ['rejected'] }
  const count = (k) => (allDrafts || []).filter((d) => groups[k].includes(d.status)).length
  const all = (allDrafts || []).filter((d) => groups[filter].includes(d.status))
  return <><div className="flex gap-2 mb-5">{[['open', 'Awaiting review'], ['sent', 'Sent'], ['rejected', 'Rejected']].map(([k, label]) =>
    <button key={k} onClick={() => setFilter(k)} className={'px-4 py-2 rounded-lg text-sm font-semibold border transition ' + (filter === k ? 'bg-[#b6e68a] text-[#0d0f09] border-[#b6e68a]' : 'bg-white text-slate-700 border-slate-200 hover:border-slate-400')}>
      {label} <span className={'ml-1 text-xs rounded-full px-2 py-0.5 ' + (filter === k ? 'bg-black/15' : 'bg-slate-100')}>{count(k)}</span></button>)}</div>
    {all.map((d) => { const e = edit[d.id]; return <Card key={d.id} title={`${d.company.name} -> ${d.contact.first_name} ${d.contact.last_name}`}
    right={<div className="flex gap-3 items-center"><Badge v={d.status} /><Badge v={d.company.priority} /><Gauge value={d.company.score} size={64} /></div>}>
    <div className="grid lg:grid-cols-2 gap-6 text-sm">
      <div className="space-y-4">
        <div className="rounded-xl bg-indigo-50 p-3"><h3 className="font-bold text-indigo-700">Contact</h3>{d.contact.first_name} {d.contact.last_name}, {d.contact.position} - {d.contact.email}
          <div className="text-slate-600">Hunter confidence {d.contact.confidence}; email {d.contact.verification}</div>
          <div className="text-slate-500 text-xs mt-1">{d.contact.reasoning}</div></div>
        <div><h3 className="font-bold text-emerald-700 mb-1">ICP reasoning</h3><HBars rows={Object.entries(d.score_detail.detail || {}).filter(([, v]) => v.max > 0).map(([k, v]) => ({
          label: k.replaceAll('_', ' '), right: `${v.points}/${v.max}`, pct: (v.points / v.max) * 100, color: STATE_COLOR[v.state] }))} /></div>
        <div><h3 className="font-bold text-fuchsia-700 mb-1">Buying signals</h3><div className="flex gap-1.5 flex-wrap">{d.intent.signals?.map((s, k) => <Badge key={k} v={s.type} />)}</div></div>
        <div><h3 className="font-bold text-amber-700 mb-1">Pain points</h3>{d.intent.pain_points?.map((p, k) => <div key={k} className="text-xs mb-1.5"><b>{p.pain}</b><div className="text-slate-600">Interpretation: {p.interpretation}</div></div>)}</div>
        <div><h3 className="font-bold text-sky-700 mb-1">Sources behind the email</h3>{d.sources.map((s) => <div key={s.id} className="text-xs mb-1">
          <b>{s.criterion}</b>: {s.value} <Link href={s.source_url} /></div>)}</div>
      </div>
      <div>
        <h3 className="font-bold text-violet-700 mb-2">Email draft</h3>
        {e ? <>
          <input className="w-full border-2 border-slate-200 focus:border-violet-400 outline-none rounded-xl p-2.5 mb-2" value={e.subject} onChange={(x) => setEdit({ ...edit, [d.id]: { ...e, subject: x.target.value } })} />
          <textarea className="w-full border-2 border-slate-200 focus:border-violet-400 outline-none rounded-xl p-3 font-mono text-xs" rows="16" value={e.body} onChange={(x) => setEdit({ ...edit, [d.id]: { ...e, body: x.target.value } })} />
          <div className="flex gap-2 mt-2"><Btn kind="primary" onClick={() => act(d.id, async () => { await api('/drafts/' + d.id, { method: 'PUT', body: e }); setEdit({ ...edit, [d.id]: null }) })}>Save edit</Btn>
            <Btn onClick={() => setEdit({ ...edit, [d.id]: null })}>Cancel</Btn></div></> : <>
          <div className="rounded-2xl border-2 border-violet-200 bg-gradient-to-br from-violet-50 to-fuchsia-50 p-4"><div className="font-bold mb-2 text-violet-900">Subject: {d.subject}</div>
            <pre className="whitespace-pre-wrap font-sans text-slate-800">{d.body}</pre></div>
          {d.sends?.length > 0 && <div className="mt-3 text-xs text-slate-600">{d.sends.map((x, k) => <div key={k}><Badge v={x.status} /> {x.created_at}{x.resend_id ? ` - Resend id ${x.resend_id}` : ''}{x.error ? ` - ${x.error}` : ''}</div>)}</div>}
          <div className={'flex gap-3 mt-4 ' + (d.status === 'sent' || d.status === 'rejected' ? 'hidden' : '')}>
            <Btn onClick={() => setEdit({ ...edit, [d.id]: { subject: d.subject, body: d.body } })}>Edit Email</Btn>
            {confirming === d.id
              ? <span className="flex items-center gap-2 bg-emerald-50 border-2 border-emerald-300 rounded-xl px-3 py-1.5"><span className="text-sm text-emerald-900">Send to <b>{recipient || 'your inbox'}</b>?</span>
                <Btn kind="success" onClick={() => { setConfirming(null); act(d.id, () => api(`/drafts/${d.id}/approve-send`, { method: 'POST' })) }}>Yes, send</Btn>
                <Btn onClick={() => setConfirming(null)}>Cancel</Btn></span>
              : <Btn kind="success" onClick={() => setConfirming(d.id)}>Approve &amp; Send</Btn>}
            <Btn kind="danger" onClick={() => act(d.id, () => api(`/drafts/${d.id}/reject`, { method: 'POST' }))}>Reject</Btn></div></>}
        {msg[d.id] && <p className="mt-2 text-sm font-medium text-rose-600">{msg[d.id]}</p>}
        <p className="text-xs text-slate-500 mt-3">Delivery goes only to your own address. An edit resets approval and is re-validated against verified facts.</p>
      </div></div></Card> })}
    {all.length === 0 && <div className="bg-white rounded-2xl shadow-sm p-8 text-center text-slate-500 text-sm">{filter === 'open'
      ? 'No drafts awaiting review. Drafts appear here when a company scores 55 or above and has a verified contact. Companies scoring lower stay in Company Research.'
      : `No ${filter} drafts yet.`}</div>}</>
}

function Sent() {
  const [list] = useData('/sent')
  const by = ['sent', 'failed', 'dry_run'].map((s) => ({ label: s.replace('_', ' '), value: (list || []).filter((x) => x.status === s).length, color: { sent: C.emerald, failed: C.rose, dry_run: C.slate }[s] }))
  return <>
    {list?.length > 0 && <Card title="Delivery status" accent="from-emerald-400 to-teal-500"><Donut data={by} sub="emails" /></Card>}
    <Card title="Sent emails"><table className="w-full text-sm"><thead className="text-left text-slate-500 uppercase text-xs"><tr><th className="pb-2">When</th><th>Company</th><th>Subject</th><th>To</th><th>Status</th><th>Resend id</th></tr></thead>
      <tbody>{list?.map((s) => <tr key={s.id} className="border-t border-slate-100 align-top"><td className="py-2">{s.created_at}</td><td>{s.company}</td>
        <td>{s.subject}<details><summary className="text-xs text-violet-600 cursor-pointer">content</summary><pre className="whitespace-pre-wrap text-xs">{s.body}</pre></details></td>
        <td>{s.to_email}</td><td><Badge v={s.status} />{s.error && <div className="text-xs text-rose-600">{s.error}</div>}</td><td className="text-xs">{s.resend_id}</td></tr>)}</tbody></table>
      {list?.length === 0 && <p className="text-sm text-slate-500">No emails sent yet.</p>}</Card></>
}

function Integrations() {
  const [s, load] = useData('/settings')
  const [tests, setTests] = useState({})
  const test = async (n) => { setTests((t) => ({ ...t, [n]: '...' })); const r = await api('/selftest/' + n, { method: 'POST' }); setTests((t) => ({ ...t, [n]: (r.ok ? 'OK' : 'FAILED') + (r.detail ? ' - ' + (typeof r.detail === 'string' ? r.detail : JSON.stringify(r.detail)) : '') })) }
  const relevant = s ? Object.entries(s.integrations).filter(([k]) => !(s.cloud && s.local_only?.includes(k))) : []
  const on = relevant.filter(([, v]) => v).length
  return <>
    <Card title="Connected services (keys stay in the backend, never in the browser)" accent="from-sky-400 to-indigo-500"
      right={s && <Gauge value={(on / Math.max(relevant.length, 1)) * 100} size={60} />}>
      <table className="w-full text-sm"><tbody>{s && Object.entries(s.integrations).map(([k, v]) => <tr key={k} className="border-t border-slate-100">
        <td className="py-2 font-mono">{k}</td><td>{s.cloud && s.local_only?.includes(k) ? <><Badge v="VERIFIED" /> <span className="text-slate-500 text-sm">runs locally, not needed here</span></> : <><Badge v={v ? 'VERIFIED' : 'NOT_FOUND'} /> {v ? 'configured' : 'missing'}</>}</td>
        <td>{(s.cloud && s.local_only?.includes(k) ? [] : ['GEMINI_API_KEY:gemini', 'HUNTER_API_KEY:hunter', 'RESEND_API_KEY:resend']).filter((x) => x.startsWith(k)).map((x) => {
          const n = x.split(':')[1]; return <span key={n}><Btn onClick={() => test(n)}>Test</Btn> <span className="text-xs">{tests[n]}</span></span> })}</td></tr>)}</tbody></table>
    </Card>
  </>
}

const TABS = { Overview, 'Company Research': Research, 'Qualified Leads': Leads, 'My Activity': Activity, 'ICP Discovery': Icp, 'Review Centre': Review, 'Sent Emails': Sent, Integrations }
const ICONS = { Overview: '◈', 'My Activity': '◷', 'ICP Discovery': '◎', 'Company Research': '⌕', 'Qualified Leads': '★', 'Review Centre': '✉', 'Sent Emails': '➤', Integrations: '⚙' }

function Activity({ setTab }) {
  const [drafts] = useData('/drafts?status=pending')
  const [sent] = useData('/sent')
  const [companies] = useData('/companies')
  const Block = ({ title, to, children }) => <Card title={title} right={<button onClick={() => setTab(to)} className="text-xs text-[#b38848] hover:underline">View all</button>}>
    <div className="space-y-2.5">{children}</div></Card>
  const Item = ({ top, sub, badge }) => <div className="bg-[#f7f1e8] rounded-xl px-3.5 py-2.5 flex items-center gap-3">
    <div className="min-w-0 flex-1"><div className="text-sm font-medium text-[#19191b] truncate">{top}</div><div className="text-[11px] text-slate-500 truncate">{sub}</div></div>{badge}</div>
  const top = (companies || []).filter((c) => c.score != null).slice(0, 5)
  return <div className="grid lg:grid-cols-3 gap-6">
    <Block title="Awaiting review" to="Review Centre">{(drafts || []).slice(0, 5).map((d) => <Item key={d.id} top={d.company.name}
      sub={`${d.contact.first_name} ${d.contact.last_name} - ${d.contact.position}`} badge={<Badge v={d.company.priority} />} />)}
      {drafts && drafts.length === 0 && <div className="text-xs text-slate-500">Nothing waiting.</div>}</Block>
    <Block title="Top scored companies" to="Company Research">{top.map((c) => <Item key={c.id} top={c.name} sub={c.domain}
      badge={<span className="text-sm font-bold text-[#8f6a33]">{c.score}</span>} />)}</Block>
    <Block title="Latest sent" to="Sent Emails">{(sent || []).slice(0, 5).map((x) => <Item key={x.id} top={x.company} sub={x.subject} badge={<Badge v={x.status} />} />)}
      {sent && sent.length === 0 && <div className="text-xs text-slate-500">No emails sent yet.</div>}</Block>
  </div>
}

export default function App() {
  const [tab, setTab] = useState('Overview')
  const [ov] = useData('/overview')
  const Page = TABS[tab]
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  return <div className="min-h-screen bg-[#c59d5f] p-3 md:p-10">
    <div className="bg-[#19191b] rounded-[32px] p-3 md:p-4 flex gap-3 md:gap-4 min-h-[calc(100vh-5rem)] shadow-2xl shadow-black/30">
      <nav className="w-60 shrink-0 flex flex-col text-[#a1a1a8] px-2 py-3">
        <div className="flex items-center gap-2.5 px-3 pb-8 pt-2">
          <div className="w-9 h-9 rounded-xl bg-[#c59d5f] flex items-center justify-center text-white font-extrabold">S</div>
          <div className="text-white text-2xl font-extrabold tracking-tight">Sprinto<span className="text-[#c59d5f]">AI</span></div>
        </div>
        <div className="flex-1">{Object.keys(TABS).map((t) => <button key={t} onClick={() => setTab(t)}
          className={'flex items-center gap-3 w-full text-left px-4 py-3 rounded-xl text-sm font-medium mb-2 transition ' + (t === tab
            ? 'bg-[#c59d5f] text-white shadow-md shadow-black/20' : 'hover:bg-white/5 hover:text-white')}>
          <span className="text-base w-5 text-center">{ICONS[t]}</span>{t}
          {t === 'Review Centre' && ov?.pending_approvals > 0 && <span className={'ml-auto text-xs font-bold rounded-full px-2 py-0.5 ' + (t === tab ? 'bg-white text-[#8f6a33]' : 'bg-[#c59d5f] text-white')}>{ov.pending_approvals}</span>}
        </button>)}</div>
        <div className="rounded-xl border border-white/10 px-3 py-2.5 flex items-center gap-3 mt-4">
          <div className="w-8 h-8 rounded-full bg-[#c59d5f] text-white flex items-center justify-center text-sm font-bold">B</div>
          <div><div className="text-sm text-white font-medium leading-tight">Bhavesh</div><div className="text-[11px] text-[#c59d5f]">Active</div></div>
        </div>
      </nav>
      <div className="flex-1 min-w-0 flex bg-white rounded-3xl overflow-hidden">
        <main className="flex-1 min-w-0 p-6 md:p-8 overflow-y-auto">
          <h1 className="text-3xl font-bold text-[#19191b]">{tab}</h1>
          <div className="text-xs text-slate-500 mt-1 mb-6">{today}</div>
          <Jobs /><Page key={tab} setTab={setTab} />
        </main>
      </div>
    </div>
  </div>
}
