import { useEffect, useState } from "react";

// Always send the session cookie.
const opts = (extra = {}) => ({ credentials: "include", ...extra });

const api = {
  async me() {
    const r = await fetch("/api/auth/me", opts());
    if (r.status === 401) return null;
    return r.json();
  },
  async logout() { await fetch("/api/auth/logout", opts({ method: "POST" })); },
  async fetch(search) {
    return (await fetch("/api/fetch", opts({
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ search }),
    }))).json();
  },
  async jobs(status) {
    const q = status ? `?status=${status}` : "";
    return (await fetch(`/api/jobs${q}`, opts())).json();
  },
  async draft(id) { return (await fetch(`/api/jobs/${id}/draft`, opts({ method: "POST" }))).json(); },
  async saveDraft(id, subject, body) {
    return (await fetch(`/api/jobs/${id}/draft`, opts({
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, body }),
    }))).json();
  },
  async post(id, action) {
    const r = await fetch(`/api/jobs/${id}/${action}`, opts({ method: "POST" }));
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "request failed");
    return data;
  },
};

function Login() {
  return (
    <div className="login">
      <h1>VA Job Agent</h1>
      <p className="sub">Find US-based remote virtual-assistant roles and apply with reviewed, tailored emails.</p>
      <a className="google-btn" href="/api/auth/login">
        <span className="g">G</span> Sign in with Google
      </a>
      <p className="fineprint">Signing in also authorizes sending email from your Gmail. Access is restricted to approved accounts.</p>
    </div>
  );
}

function ScoreBadge({ score }) {
  const cls = score >= 80 ? "hi" : score >= 60 ? "mid" : "";
  return <span className={`score ${cls}`}>{score ?? "—"}% match</span>;
}

function JobCard({ job, onChange }) {
  const [draft, setDraft] = useState({ subject: job.draft_subject || "", body: job.draft_body || "" });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const run = async (fn) => {
    setBusy(true); setMsg("");
    try { await fn(); } catch (e) { setMsg(e.message); } finally { setBusy(false); }
  };

  const generate = () => run(async () => { const d = await api.draft(job.id); setDraft(d); setOpen(true); onChange(); });
  const save = () => run(async () => { await api.saveDraft(job.id, draft.subject, draft.body); onChange(); });
  const gmailDraft = () => run(async () => { await api.post(job.id, "gmail-draft"); setMsg("Saved to your Gmail drafts."); onChange(); });
  const send = () => run(async () => { const r = await api.post(job.id, "send"); setMsg(`Sent. ${r.sent_today} sent today.`); onChange(); });
  const skip = () => run(async () => { await api.post(job.id, "skip"); onChange(); });

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3>{job.title}</h3>
        <span className={`status ${job.status}`}>{job.status}</span>
      </div>
      <div className="meta">
        <span>{job.company || "Unknown company"}</span>
        <span>· {job.location || "—"}</span>
        <span>· {job.source}</span>
        {job.score != null && <span>· <ScoreBadge score={job.score} /></span>}
      </div>
      {job.description && <div className="desc">{job.description}</div>}

      <div className="row">
        {job.url && <a href={job.url} target="_blank" rel="noreferrer"><button className="ghost">View listing ↗</button></a>}
        <button onClick={generate} disabled={busy}>{job.draft_body ? "Regenerate draft" : "Generate draft"}</button>
        {job.draft_body && <button onClick={() => setOpen(!open)}>{open ? "Hide" : "Review draft"}</button>}
        <button className="ghost" onClick={skip} disabled={busy}>Skip</button>
      </div>

      {open && (
        <div style={{ marginTop: 12 }}>
          <input className="draft-subject" type="text" value={draft.subject}
            onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
          <textarea rows={12} value={draft.body}
            onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
          <div className="row" style={{ marginTop: 8 }}>
            <button onClick={save} disabled={busy}>Save edits</button>
            {job.contact_email ? (
              <>
                <button className="primary" onClick={gmailDraft} disabled={busy}>Save to Gmail drafts</button>
                <button className="go" onClick={send} disabled={busy}>Send now → {job.contact_email}</button>
              </>
            ) : (
              <span className="no-email">No contact email on this listing — apply via the listing link instead.</span>
            )}
          </div>
        </div>
      )}
      {msg && <div className="meta" style={{ marginTop: 8 }}>{msg}</div>}
    </div>
  );
}

function Dashboard({ me, onLogout }) {
  const [search, setSearch] = useState("virtual assistant");
  const [jobs, setJobs] = useState([]);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState(me);

  const load = async () => setJobs(await api.jobs(filter || undefined));
  useEffect(() => { load(); }, [filter]);

  const fetchJobs = async () => {
    setBusy(true); setNote("");
    try {
      const r = await api.fetch(search);
      setNote(`Fetched ${r.found} matching roles, ${r.new} new.`);
      await load();
      setStatus(await api.me());
    } finally { setBusy(false); }
  };

  return (
    <div className="app">
      <header>
        <h1>VA Job Agent</h1>
        <span className="pill">{status.llm ? "LLM drafts on" : "Template drafts"} · {status.sent_today}/{status.daily_limit} sent today</span>
        <span className="spacer" />
        <span className="who">{status.email}</span>
        <button className="ghost" onClick={onLogout}>Sign out</button>
      </header>
      <p className="sub">US-based remote virtual-assistant roles from public job APIs. Drafts are written for you to review before anything is sent.</p>

      <div className="banner">
        Review every draft before sending. Keep daily volume low and messages genuinely tailored —
        automated mass cold emails break Gmail's policy and CAN-SPAM, and tank your deliverability.
      </div>

      <div className="bar">
        <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="search term (e.g. virtual assistant)" />
        <button className="primary" onClick={fetchJobs} disabled={busy}>{busy ? "Fetching…" : "Fetch jobs"}</button>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All</option>
          <option value="new">New</option>
          <option value="drafted">Drafted</option>
          <option value="approved">Approved</option>
          <option value="sent">Sent</option>
          <option value="skipped">Skipped</option>
        </select>
        <button className="ghost" onClick={load}>Refresh</button>
        {note && <span className="pill">{note}</span>}
      </div>

      <div className="grid">
        {jobs.length === 0 && <div className="empty">No jobs yet. Click “Fetch jobs” to pull the latest listings.</div>}
        {jobs.map((j) => <JobCard key={j.id} job={j} onChange={load} />)}
      </div>
    </div>
  );
}

export default function App() {
  const [me, setMe] = useState(undefined); // undefined = loading, null = logged out

  useEffect(() => { api.me().then(setMe); }, []);

  const logout = async () => { await api.logout(); setMe(null); };

  if (me === undefined) return <div className="app"><div className="empty">Loading…</div></div>;
  if (me === null) return <Login />;
  return <Dashboard me={me} onLogout={logout} />;
}
