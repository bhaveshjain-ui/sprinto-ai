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
const C = { violet: '#8a9570', fuchsia: '#b8c18f', emerald: '#8fcf5a', amber: '#b8c18f', rose: '#5a6540',
  sky: '#7f8a5a', slate: '#3f4830', indigo: '#cdd5ad' }

/* ---------- charts (plain SVG, no deps) ---------- */
function Donut({ data, size = 170, center, sub }) {
  const total = data.reduce((a, d) => a + d.value, 0)
  const r = 52, circ = 2 * Math.PI * r
  let offset = 0
  return <div className="flex items-center gap-5 flex-wrap">
    <svg width={size} height={size} viewBox="0 0 140 140">
      <circle cx="70" cy="70" r={r} fill="none" stroke="#343b27" strokeWidth="20" />
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
    <circle cx="50" cy="50" r={r} fill="none" stroke="#343b27" strokeWidth="12" />
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
const Card = ({ title, children, right, accent = 'from-violet-500 to-fuchsia-500' }) => (
  <section className="bg-white rounded-2xl shadow-md shadow-indigo-100 mb-6 overflow-hidden">
    <div className={'h-1.5 bg-gradient-to-r ' + accent} />
    <div className="p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-bold text-lg text-slate-800">{title}</h2>{right}
      </div>
      {children}
    </div>
  </section>
)
const Btn = ({ children, kind = 'default', ...p }) => (
  <button {...p} className={'px-4 py-2 rounded-xl text-sm font-semibold transition disabled:opacity-50 ' + ({
    default: 'bg-white border-2 border-slate-200 text-slate-700 hover:border-violet-400 hover:text-violet-700',
    primary: 'bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white shadow-md shadow-fuchsia-200 hover:brightness-110',
    success: 'bg-gradient-to-r from-emerald-500 to-teal-500 text-white shadow-md shadow-emerald-200 hover:brightness-110',
    danger: 'bg-white border-2 border-rose-300 text-rose-600 hover:bg-rose-50',
  }[kind])}>{children}</button>
)
const BADGE = { VERIFIED: 'bg-emerald-500 text-white', qualified: 'bg-emerald-500 text-white', High: 'bg-emerald-500 text-white',
  sent: 'bg-emerald-500 text-white', Medium: 'bg-amber-400 text-amber-950', further_investigation: 'bg-amber-400 text-amber-950',
  STALE: 'bg-amber-400 text-amber-950', pending: 'bg-amber-400 text-amber-950', ASSERTED: 'bg-rose-500 text-white',
  rejected: 'bg-rose-500 text-white', stopped: 'bg-rose-500 text-white', failed: 'bg-rose-500 text-white',
  Low: 'bg-slate-400 text-white', NOT_FOUND: 'bg-slate-300 text-slate-700', approved: 'bg-sky-500 text-white',
  lead: 'bg-violet-500 text-white', drafted: 'bg-fuchsia-500 text-white', shortlisted: 'bg-indigo-500 text-white',
  researched: 'bg-sky-500 text-white', filtered: 'bg-slate-400 text-white', no_contact: 'bg-amber-400 text-amber-950', dry_run: 'bg-slate-400 text-white' }
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
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">{tiles?.map(([k, v, g]) => (
      <div key={k} className={'rounded-2xl p-4 text-white shadow-lg bg-gradient-to-br ' + g}>
        <div className="text-4xl font-extrabold">{v}</div><div className="text-sm opacity-90 font-medium">{k}</div></div>))}</div>
    {d && <div className="grid lg:grid-cols-2 gap-6">
      <Card title="Outcome split" accent="from-emerald-400 to-teal-500"><Donut center={d.discovered} sub="companies" data={[
        { label: 'Qualified', value: d.qualified, color: C.emerald }, { label: 'Further investigation', value: d.further_investigation, color: C.amber },
        { label: 'Rejected', value: d.rejected, color: C.rose }, { label: 'Being researched / queued', value: d.in_queue, color: C.sky }, { label: 'Filtered at shortlist', value: d.filtered_out, color: C.slate }]} /></Card>
      <Card title="Pipeline funnel" accent="from-sky-400 to-indigo-500"><HBars rows={funnel.map(([label, v, color]) => ({ label, right: v, pct: (v / top) * 100, color }))} /></Card>
    </div>}
    <Card title="Run the pipeline" accent="from-fuchsia-500 to-rose-500">
      <div className="flex flex-wrap gap-3 mb-4">
        <Btn kind="primary" onClick={() => run(() => api('/autonomous', { method: 'POST' }))}>Autonomous discovery + full run</Btn>
        <Btn onClick={() => run(() => api('/discover', { method: 'POST' }))}>Discover &amp; shortlist only</Btn>
        <Btn onClick={() => run(() => api('/companies/process', { method: 'POST' }))}>Process shortlisted</Btn>
      </div>
      <label className="text-sm text-slate-600 font-medium">Or enter company domains (one per line or comma-separated)</label>
      <textarea className="w-full border-2 border-slate-200 focus:border-violet-400 outline-none rounded-xl p-3 mt-1 text-sm" rows="3" value={domains}
        onChange={(e) => setDomains(e.target.value)} placeholder="acme.com, example.io" />
      <div className="mt-3"><Btn onClick={() => run(async () => {
        const r = await api('/companies/manual', { method: 'POST', body: { domains: domains.split(/[\s,]+/).filter(Boolean) } })
        setMsg(`Added ${r.added.length}` + (r.invalid.length ? `; invalid: ${r.invalid.join(', ')}` : '') + '. Click "Process shortlisted".'); setDomains('')
      })}>Add domains</Btn></div>
      {msg && <p className="text-sm text-violet-700 font-medium mt-3">{msg}</p>}
    </Card>
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

function Research() {
  const [list, load] = useData('/companies')
  const [open, setOpen] = useState(null)
  useEffect(() => { const t = setInterval(load, 5000); return () => clearInterval(t) }, [load])
  if (open) return <CompanyDetail id={open} onClose={() => setOpen(null)} />
  return <Card title="Companies">
    <table className="w-full text-sm"><thead className="text-left text-slate-500 uppercase text-xs"><tr><th className="pb-2">Company</th><th>Origin</th><th>Status</th><th>Score</th><th>Class</th><th>Priority</th><th>Why stopped</th></tr></thead>
      <tbody>{list?.map((c) => <tr key={c.id} className="border-t border-slate-100 cursor-pointer hover:bg-violet-50" onClick={() => setOpen(c.id)}>
        <td className="py-2.5"><b>{c.name}</b><div className="text-xs text-slate-500">{c.domain}</div></td><td>{c.origin}</td><td><Badge v={c.status === 'stopped' ? (c.stage === 'shortlist' ? 'filtered' : c.stage === 'score' ? 'rejected' : 'no_contact') : c.status} /></td>
        <td>{c.score != null ? <div className="flex items-center gap-2 w-28"><div className="flex-1 h-2.5 bg-slate-200 rounded-full overflow-hidden"><div className="h-full rounded-full" style={{ width: c.score + '%', background: c.score >= 75 ? C.emerald : c.score >= 55 ? C.amber : C.rose }} /></div><b>{c.score}</b></div> : '-'}</td>
        <td>{c.classification && <Badge v={c.classification} />}</td><td>{c.priority && <Badge v={c.priority} />}</td>
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

function Settings() {
  const [s, load] = useData('/settings')
  const [tests, setTests] = useState({})
  const test = async (n) => { setTests((t) => ({ ...t, [n]: '...' })); const r = await api('/selftest/' + n, { method: 'POST' }); setTests((t) => ({ ...t, [n]: (r.ok ? 'OK' : 'FAILED') + (r.detail ? ' - ' + (typeof r.detail === 'string' ? r.detail : JSON.stringify(r.detail)) : '') })) }
  const on = s ? Object.values(s.integrations).filter(Boolean).length : 0
  return <>
    <Card title="Integrations (keys live in the backend .env, never in the browser)" accent="from-sky-400 to-indigo-500"
      right={s && <Gauge value={(on / Math.max(Object.keys(s.integrations).length, 1)) * 100} size={60} />}>
      <table className="w-full text-sm"><tbody>{s && Object.entries(s.integrations).map(([k, v]) => <tr key={k} className="border-t border-slate-100">
        <td className="py-2 font-mono">{k}</td><td><Badge v={v ? 'VERIFIED' : 'NOT_FOUND'} /> {v ? 'configured' : 'missing'}</td>
        <td>{['GEMINI_API_KEY:gemini', 'HUNTER_API_KEY:hunter', 'RESEND_API_KEY:resend'].filter((x) => x.startsWith(k)).map((x) => {
          const n = x.split(':')[1]; return <span key={n}><Btn onClick={() => test(n)}>Test</Btn> <span className="text-xs">{tests[n]}</span></span> })}</td></tr>)}</tbody></table>
    </Card>
  </>
}

const TABS = { 'Company Research': Research, 'Qualified Leads': Leads, Overview, 'ICP Discovery': Icp, 'Review Centre': Review, 'Sent Emails': Sent, Settings }
const ICONS = { Overview: '◈', 'ICP Discovery': '◎', 'Company Research': '⌕', 'Qualified Leads': '★', 'Review Centre': '✉', 'Sent Emails': '➤', Settings: '⚙' }

export default function App() {
  const [tab, setTab] = useState('Overview')
  const [ov] = useData('/overview')
  const Page = TABS[tab]
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  return <div className="flex flex-row-reverse min-h-screen bg-[#12140d]">
    <nav className="w-64 shrink-0 bg-[#0d0f09] text-[#b3bb9b] flex flex-col border-l border-[#2a3020]">
      <div className="px-5 py-6 border-b border-[#2a3020]">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#b6e68a] to-[#8fcf5a] flex items-center justify-center text-[#0d0f09] font-extrabold text-lg">S</div>
          <div><div className="text-[#f1f5e3] font-bold leading-tight">Sprinto AI</div><div className="text-xs text-[#78845b]">Outbound intelligence</div></div>
        </div>
      </div>
      <div className="p-3 flex-1">
        <div className="px-3 pt-2 pb-2 text-[11px] uppercase tracking-wider text-[#67704f] font-semibold">Workspace</div>
        {Object.keys(TABS).map((t) => <button key={t} onClick={() => setTab(t)}
          className={'flex items-center gap-3 w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium mb-1 transition border-r-4 ' + (t === tab
            ? 'bg-[#232819] text-[#f1f5e3] border-[#b6e68a]' : 'border-transparent hover:bg-[#181b11] hover:text-[#f1f5e3]')}>
          <span className="text-base w-5 text-center text-[#8a9570]">{ICONS[t]}</span>{t}
          {t === 'Review Centre' && ov?.pending_approvals > 0 && <span className="ml-auto bg-[#b6e68a] text-[#0d0f09] text-xs font-bold rounded-full px-2 py-0.5">{ov.pending_approvals}</span>}
        </button>)}
      </div>
      <div className="p-4 border-t border-[#2a3020] text-xs text-[#67704f]">All emails are delivered to your own inbox only, after your approval.</div>
    </nav>
    <main className="flex-1 min-w-0">
      <header className="bg-[#1a1e13] border-b border-[#2a3020] px-8 py-4 flex items-center justify-between">
        <div><h1 className="text-2xl font-bold text-slate-900">{tab}</h1><div className="text-xs text-slate-500 mt-0.5">{today}</div></div>
        {ov && <div className="flex gap-6 text-right">
          {[['Companies', ov.discovered], ['Qualified', ov.qualified], ['Sent', ov.sent]].map(([k, v]) => <div key={k}>
            <div className="text-xl font-bold text-slate-900 leading-none">{v}</div><div className="text-[11px] uppercase tracking-wide text-slate-500 mt-1">{k}</div></div>)}</div>}
      </header>
      <div className="p-8 max-w-6xl"><Jobs /><Page key={tab} /></div>
    </main>
  </div>
}
