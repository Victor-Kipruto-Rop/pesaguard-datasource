import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertCircle, AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight,
  Bell, Building2, CheckCircle2, ChevronDown, CircleDot, Clock3, Database, KeyRound,
  FileCheck2, FileSpreadsheet, FileText, HardDrive, LayoutDashboard, Menu,
  RefreshCw, Search, Server, Settings, ShieldCheck, SlidersHorizontal,
  Upload, X, ScrollText, Workflow
} from 'lucide-react';
import { api, API_BASE, setCsrfToken } from './api.js';
import ApiKeysPanel from './ApiKeysPanel.jsx';
import DataSourcesPanel from './DataSourcesPanel.jsx';
import LoginPage from './LoginPage.jsx';
import WidgetErrorBoundary from './WidgetErrorBoundary.jsx';
import WorkspaceModulePage from './WorkspaceModulePage.jsx';

const NAV = [
  { name: 'Overview', icon: LayoutDashboard, group: 'WORKSPACE' },
  { name: 'Data Sources', icon: Database, group: 'WORKSPACE' },
  { name: 'Ingestion Jobs', icon: Activity, group: 'WORKSPACE' },
  { name: 'Registry Records', icon: Building2, group: 'WORKSPACE' },
  { name: 'Data Quality', icon: FileCheck2, group: 'GOVERNANCE' },
  { name: 'Warehouse', icon: HardDrive, group: 'GOVERNANCE' },
  { name: 'Validation Rules', icon: ShieldCheck, group: 'GOVERNANCE' },
  { name: 'Audit Logs', icon: ScrollText, group: 'ADMINISTRATION' },
  { name: 'API Keys', icon: KeyRound, group: 'ADMINISTRATION' },
  { name: 'Settings', icon: Settings, group: 'ADMINISTRATION' },
];

const dateLabel = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};
const number = (value) => Number(value || 0).toLocaleString();
const statusTone = (value) => {
  const status = String(value || '').toLowerCase();
  if (['completed', 'completed_with_errors', 'healthy', 'connected', 'ready'].includes(status)) return 'success';
  if (['processing', 'running', 'in_progress', 'pending', 'queued', 'pending_submission'].includes(status)) return 'warning';
  if (['failed', 'error', 'rejected', 'verification_failed'].includes(status)) return 'danger';
  return 'neutral';
};

function StatusPill({ value }) {
  const tone = statusTone(value);
  return <span className={`status-pill ${tone}`}><i />{String(value || 'Unknown').replaceAll('_', ' ')}</span>;
}

function Sidebar({ page, setPage, mobile, setMobile, connected }) {
  let group = '';
  return <aside className={`sidebar ${mobile ? 'sidebar-open' : ''}`}>
    <div className="brand-row">
      <img className="brand-logo" src="/pesaguard-logo.svg" alt="PesaGuard" />
      <button className="icon-button mobile-close" onClick={() => setMobile(false)} aria-label="Close menu"><X size={18} /></button>
    </div>
    <div className="workspace-chip"><span className="pulse-dot" />INTERNAL DATA PLATFORM</div>
    <nav className="side-nav">
      {NAV.map((item) => {
        const showGroup = item.group !== group;
        group = item.group;
        return <React.Fragment key={item.name}>
          {showGroup && <div className="nav-group-label">{item.group}</div>}
          <button className={`nav-item ${page === item.name ? 'active' : ''}`} aria-current={page === item.name ? "page" : undefined} onClick={() => { setPage(item.name); setMobile(false); }}>
            <item.icon size={18} strokeWidth={1.8} /><span>{item.name}</span>
            
          </button>
        </React.Fragment>;
      })}
    </nav>
    <div className="sidebar-footer">
      <div className="secure-icon"><ShieldCheck size={17} /></div>
      <div><strong>Secure workspace</strong><span>Operator access</span></div>
      <span className={`footer-online ${connected ? "" : "muted"}`} title={connected ? "API connected" : "API not connected"} />
    </div>
  </aside>;
}

function Topbar({ page, connected, onRefresh, loading, search, setSearch, setMobile, onSignOut, previewMode, onTogglePreview, failedJobs, notificationsOpen, setNotificationsOpen, onViewJobs }) {
  return <header className="topbar">
    <div className="topbar-left">
      <button className="icon-button mobile-menu" onClick={() => setMobile(true)} aria-label="Open menu"><Menu size={20} /></button>
      <div className="breadcrumb"><span>Datasource</span><span className="breadcrumb-slash">/</span><strong>{page}</strong></div>
    </div>
    <div className="topbar-tools">
      <label className="global-search"><Search size={16} /><input aria-label="Search records, jobs and sources" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search records, jobs, sources…" /><kbd>⌘ K</kbd></label>
      <button className={`environment preview-toggle ${previewMode ? 'active' : ''}`} onClick={onTogglePreview} aria-pressed={previewMode} title="Preview mode disables dashboard write actions"><span className={connected ? 'pulse-dot' : 'pulse-dot muted'} />{previewMode ? 'Preview mode' : (connected ? 'API connected' : 'API offline')}</button>
      <div className="notification-wrap"><button className="icon-button notification-button" aria-label={`Notifications, ${failedJobs.length} failed jobs`} aria-expanded={notificationsOpen} onClick={() => setNotificationsOpen(!notificationsOpen)}><Bell size={18} />{failedJobs.length > 0 && <i>{failedJobs.length > 99 ? '99+' : failedJobs.length}</i>}</button>
      {notificationsOpen && <div className="notification-popover"><strong>Workspace alerts</strong>{failedJobs.length ? failedJobs.slice(0,5).map(job => <button key={job.id} className="notification-item" onClick={() => { setNotificationsOpen(false); onViewJobs(); }}><span className="notification-danger-dot"/><span><b>{job.file_name || 'Ingestion job failed'}</b><small>{job.error_summary || 'This job needs investigation.'}</small></span></button>) : <p>No failed ingestion jobs are currently reported.</p>}<button className="button-link" onClick={() => { setNotificationsOpen(false); }}>Close alerts</button></div>}</div>
      {connected && <button className="button-secondary" onClick={onSignOut}>Sign out</button>}
      <button className="icon-button refresh-button" onClick={onRefresh} aria-label="Refresh data" disabled={loading}><RefreshCw size={17} className={loading ? 'spin' : ''} /></button>
    </div>
  </header>;
}

function MetricCard({ icon: Icon, label, value, note, accent = 'green' }) {
  return <article className="metric-card">
    <div className="metric-top"><span>{label}</span><span className={`metric-icon ${accent}`}><Icon size={18} strokeWidth={1.8} /></span></div>
    <div className="metric-value" aria-busy={value === '—'}>{value === '—' ? <span className="metric-skeleton" aria-label="Loading metric" /> : value}</div>
    <div className="metric-note"><span>{note}</span></div>
  </article>;
}

function ActivityChart({ jobs }) {
  const points = useMemo(() => {
    const days = new Map();
    for (const job of jobs) {
      if (!job.created_at) continue;
      const date = new Date(job.created_at);
      if (Number.isNaN(date.getTime())) continue;
      const key = date.toISOString().slice(0, 10);
      const row = days.get(key) || { key, label: date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }), processed: 0, inserted: 0, jobs: 0 };
      row.processed += Number(job.records_processed || 0);
      row.inserted += Number(job.records_inserted || 0);
      row.jobs += 1;
      days.set(key, row);
    }
    return [...days.values()].sort((a, b) => a.key.localeCompare(b.key)).slice(-7);
  }, [jobs]);
  const max = Math.max(1, ...points.flatMap(p => [p.processed, p.inserted]));
  const chartPoints = (field) => points.map((p, i) => {
    const x = points.length <= 1 ? 50 : 28 + i * (244 / (points.length - 1));
    const y = 150 - (p[field] / max) * 112;
    return `${x},${y}`;
  }).join(' ');
  return <div className="chart-area">
    {points.length ? <>
      <div className="chart-legend"><span><i className="legend-green" />Records processed</span><span><i className="legend-mint" />Records inserted</span><span className="chart-note">Based on loaded jobs</span></div>
      <svg className="activity-chart" viewBox="0 0 300 190" role="img" aria-label="Records processed and inserted by job creation date" preserveAspectRatio="none">
        {[38, 76, 114, 152].map(y => <line key={y} x1="28" x2="274" y1={y} y2={y} className="chart-grid" />)}
        <polyline points={chartPoints('processed')} className="chart-line chart-line-dark" />
        <polyline points={chartPoints('inserted')} className="chart-line chart-line-mint" />
        {points.map((p, i) => {
          const x = points.length <= 1 ? 50 : 28 + i * (244 / (points.length - 1));
          return <g key={p.key}><circle cx={x} cy={150 - (p.processed / max) * 112} r="3.5" className="chart-point-dark" /><circle cx={x} cy={150 - (p.inserted / max) * 112} r="3.5" className="chart-point-mint" /></g>;
        })}
      </svg>
      <div className="chart-xlabels">{points.map(p => <span key={p.key}>{p.label}</span>)}</div>
    </> : <div className="chart-empty"><Activity size={25} /><strong>Activity will appear here</strong><span>Register or enable a source and process ingestion jobs to populate this chart.</span></div>}
  </div>;
}

function QualityPanel({ summary }) {
  const valid = summary?.data_quality?.valid_percentage;
  const missing = summary?.data_quality?.missing_percentage;
  const duplicate = summary?.data_quality?.duplicate_percentage;
  const hasQuality = [valid, missing].some(v => v !== undefined && v !== null);
  const rows = hasQuality ? [
    ['Field completeness', Number(valid || 0), 'quality-valid'],
    ['Missing required fields', Number(missing || 0), 'quality-missing'],
    ...(duplicate === undefined || duplicate === null ? [] : [['Duplicate candidates', Number(duplicate), 'quality-duplicate']]),
  ] : null;
  return <div className="quality-panel">
    <div className="card-heading"><div><h2>Data quality</h2><p>Registry validation overview</p></div><div className="heading-icon"><SlidersHorizontal size={17} /></div></div>
    {rows ? rows.map(([label, pct, cls]) => <div className="quality-row" key={label}><div className="quality-label"><span>{label}</span><strong>{pct.toFixed(1)}%</strong></div><div className="quality-track"><span className={cls} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} /></div></div>) : <div className="quality-unavailable"><ShieldCheck size={24} /><strong>Quality metrics not available yet</strong><span>The API does not currently expose aggregate quality percentages. Values are intentionally not estimated.</span></div>}
    <div className="quality-foot"><span className="tiny-dot" />{hasQuality ? 'Field-presence check · not schema validation' : 'Waiting for quality metrics endpoint'}</div>
  </div>;
}

function JobsTable({ jobs, compact = false, search = '' }) {
  const filtered = jobs.filter(j => [j.file_name, j.status, j.source_name, j.id].some(v => String(v || '').toLowerCase().includes(search.toLowerCase())));
  if (!filtered.length) return <div className="empty-state"><div className="empty-icon"><Database size={23} /></div><strong>{search ? 'No matching ingestion jobs' : 'No ingestion jobs yet'}</strong><span>{search ? 'Try a different search term.' : 'Upload a dataset to create your first ingestion job.'}</span></div>;
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>DATASET / FILE</th><th>STATUS</th><th>PROCESSED</th><th>INSERTED</th><th>CREATED</th></tr></thead><tbody>
    {filtered.slice(0, compact ? 5 : 50).map(job => <tr key={job.id}>
      <td><div className="file-cell"><span className={`file-icon ${String(job.file_name || '').toLowerCase().endsWith('.pdf') ? 'pdf' : 'csv'}`}>{String(job.file_name || '').toLowerCase().endsWith('.pdf') ? <FileText size={17} /> : <FileSpreadsheet size={17} />}</span><span><strong>{job.file_name || 'Unnamed dataset'}</strong><small>JOB-{String(job.id || '').slice(0, 8).toUpperCase()}</small></span></div></td>
      <td><StatusPill value={job.status} /></td><td>{number(job.records_processed)}</td><td>{number(job.records_inserted)}</td><td className="date-cell">{dateLabel(job.created_at)}</td>
    </tr>)}
  </tbody></table></div>;
}

function OrganizationsTable({ rows, total, page, pageSize, onPageChange }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (!rows.length) return <div className="empty-state"><div className="empty-icon"><Building2 size={23} /></div><strong>No registry records found</strong><span>Connect the API or import a dataset to populate the registry.</span></div>;
  return <>
    <div className="table-scroll"><table className="data-table"><thead><tr><th>ORGANIZATION</th><th>REGISTRATION NUMBER</th><th>STATUS</th><th>SOURCE FILE</th></tr></thead><tbody>{rows.map(org => <tr key={org.id}><td><div className="org-cell"><span className="org-avatar"><Building2 size={16} /></span><span><strong>{org.legal_name || 'Unnamed organization'}</strong><small>Record {String(org.id || '').slice(0, 8)}</small></span></div></td><td>{org.registration_number || '—'}</td><td><StatusPill value={org.status} /></td><td>{org.source_file || '—'}</td></tr>)}</tbody></table></div>
    <div className="pagination"><span>Showing {total ? ((page - 1) * pageSize + 1) : 0}–{Math.min(page * pageSize, total)} of {number(total)} organizations</span><div><button className="button-secondary" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous</button><button className="button-secondary" disabled={page >= pages} onClick={() => onPageChange(page + 1)}>Next</button></div></div>
  </>;
}

function ServiceStatus({ label, detail, icon: Icon, value, connected }) {
  return <div className="service-card"><div className="service-icon"><Icon size={19} /></div><div className="service-copy"><strong>{label}</strong><span>{detail}</span></div><StatusPill value={value || (connected ? 'Connected' : 'Unknown')} /></div>;
}

export default function App() {
  const [page, setPage] = useState('Overview');
  const [authed, setAuthed] = useState(false);
  const [password, setPassword] = useState('');
  const [checking, setChecking] = useState(true);
  const [signingIn, setSigningIn] = useState(false);
  const [connected, setConnected] = useState(false);
  const [summary, setSummary] = useState(null);
  const [registryOverview, setRegistryOverview] = useState(null);
  const [activity, setActivity] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [orgPage, setOrgPage] = useState(1);
  const [orgTotal, setOrgTotal] = useState(0);
  const [jobs, setJobs] = useState([]);
  const [jobsPage, setJobsPage] = useState(1);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [mobile, setMobile] = useState(false);
  const [previewMode, setPreviewMode] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const request = api;
  const refresh = useCallback(async () => {
    if (!authed) return;
    setLoading(true); setError('');
    try {
      const results = await Promise.allSettled([
        request('/api/v1/admin/workspace/metrics').then(r => r.json()),
        request('/api/v1/admin/registry/overview').then(r => r.json()),
        request('/api/v1/admin/ingestion/activity?limit=50').then(r => r.json()),
        request('/api/v1/admin/organizations?page=' + orgPage + '&page_size=100' + (search ? '&q=' + encodeURIComponent(search) : '')).then(r => r.json()),
        request('/api/v1/admin/ingestion/jobs?page=' + jobsPage + '&page_size=25' + (search ? '&q=' + encodeURIComponent(search) : '')).then(r => r.json())
      ]);
      const [metricsResult, registryResult, activityResult, orgResult, jobsResult] = results;
      if (metricsResult.status === 'fulfilled') {
        const metrics = metricsResult.value;
        setSummary(current => ({ ...(current || {}), ...metrics, total_organizations: metrics.indexed_organizations, total_jobs: metrics.ingestion_jobs }));
        setConnected(true);
      } else { throw metricsResult.reason; }
      if (registryResult.status === 'fulfilled') {
        const registry = registryResult.value; setRegistryOverview(registry);
        setSummary(current => ({ ...(current || {}), data_quality: registry.completeness_percentage == null ? null : { valid_percentage: registry.null_assertion_pass_percentage, missing_percentage: Math.max(0, 100 - registry.completeness_percentage), duplicate_percentage: null } }));
      }
      if (activityResult.status === 'fulfilled') setActivity(activityResult.value.items || []);
      if (orgResult.status === 'fulfilled') { setOrgs(orgResult.value.items || []); setOrgTotal(orgResult.value.total || 0); }
      if (jobsResult.status === 'fulfilled') { setJobs(jobsResult.value.items || []); setJobsTotal(jobsResult.value.total || 0); }
      const failedPanels = results.slice(1).filter(result => result.status === 'rejected').length;
      if (failedPanels) setError(failedPanels + ' workspace panel(s) could not refresh. Other available panels remain usable.');
    } catch (e) {
      setConnected(false);
      if (e.status === 401) { setAuthed(false); setCsrfToken(''); setError('Your session has expired. Sign in again.'); }
      else setError(e.message || 'Unable to connect to the Registry API.');
    }
    finally { setLoading(false); }
  }, [authed, request, orgPage, search, jobsPage]);

  useEffect(() => {
    if (!authed) return undefined;
    const timer = window.setInterval(() => { refresh(); }, 15000);
    return () => window.clearInterval(timer);
  }, [authed, refresh]);

  useEffect(() => {
    if (!authed || typeof EventSource === 'undefined') return undefined;
    const stream = new EventSource(API_BASE + '/api/v1/admin/workspace/stream', { withCredentials: true });
    stream.addEventListener('workspace', (event) => {
      try {
        const snapshot = JSON.parse(event.data);
        setSummary(current => ({ ...(current || {}), ...snapshot.metrics,
          total_organizations: snapshot.metrics.indexed_organizations, total_jobs: snapshot.metrics.ingestion_jobs }));
        setJobs(snapshot.jobs || []);
        setConnected(true);
      } catch { /* Keep last valid snapshot; REST refresh remains available. */ }
    });
    stream.onerror = () => stream.close();
    return () => stream.close();
  }, [authed]);

  useEffect(() => {
    const onShortcut = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); document.querySelector('.global-search input')?.focus();
      }
      if (event.key === 'Escape' && document.activeElement?.matches('.global-search input')) {
        setSearch(''); document.activeElement.blur();
      }
    };
    window.addEventListener('keydown', onShortcut);
    return () => window.removeEventListener('keydown', onShortcut);
  }, []);

  useEffect(() => {
    // Restore an existing server-side session after a page reload.
    api('/api/v1/admin/session').then(r => r.json()).then(s => { setCsrfToken(s.csrf_token); setAuthed(true); }).catch(() => {}).finally(() => setChecking(false));
  }, []);
  useEffect(() => { if (authed) refresh(); }, [authed, refresh]);
  useEffect(() => { setOrgPage(1); }, [search]);
  useEffect(() => { if (page !== 'Ingestion Jobs' && jobsPage !== 1) setJobsPage(1); }, [page, jobsPage]);

  const signIn = async (event) => {
    event.preventDefault();
    setError(''); setSigningIn(true);
    try {
      const response = await api('/api/v1/admin/login', { method: 'POST', body: JSON.stringify({ password }) });
      setCsrfToken((await response.json()).csrf_token);
      setPassword(''); setAuthed(true);
    } catch (e) { setError(e.message || 'Sign-in failed.'); }
    finally { setSigningIn(false); }
  };
  const signOut = async () => {
    try { await api('/api/v1/admin/logout', { method: 'POST' }); } catch { /* cookie is cleared server-side or expires */ }
    setCsrfToken(''); setAuthed(false); setConnected(false); setSummary(null); setRegistryOverview(null); setActivity([]); setOrgs([]); setJobs([]);
  };
  const upload = async (event) => {
    event.preventDefault();
    if (!file) return;
    setLoading(true); setError(''); setMessage('Uploading file and creating an ingestion job…');
    try {
      let result;
      if (file.size > 50 * 1024 * 1024) {
        const presignResponse = await request('/api/v1/admin/ingestion/uploads/presign', { method: 'POST', body: JSON.stringify({ file_name: file.name, size_bytes: file.size }) });
        const ticket = await presignResponse.json();
        setMessage('Uploading directly to private object storage…');
        const putStatus = await new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest(); xhr.open('PUT', ticket.upload_url); xhr.setRequestHeader('Content-Type', ticket.content_type);
          xhr.upload.onprogress = (e) => { if (e.lengthComputable) setMessage(`Uploading directly to private object storage… ${Math.round(e.loaded / e.total * 100)}%`); };
          xhr.onload = () => resolve(xhr.status); xhr.onerror = () => reject(new Error('Direct storage upload failed. Check bucket CORS and retry before the upload URL expires.')); xhr.send(file);
        });
        if (putStatus < 200 || putStatus >= 300) throw new Error('Direct storage upload failed. Check bucket CORS and retry before the upload URL expires.');
        const completeResponse = await request(`/api/v1/admin/ingestion/uploads/${ticket.job_id}/complete`, { method: 'POST' });
        result = await completeResponse.json();
      } else {
        const form = new FormData(); form.append('file', file);
        const response = await request('/api/v1/admin/ingestion/uploads', { method: 'POST', body: form });
        result = await response.json();
      }
      setMessage(`Queued job ${String(result.job_id || '').slice(0, 8)}. Processing runs asynchronously; refresh the jobs list for the outcome.`);
      setFile(null); await refresh();
    } catch (e) { setMessage(''); setError(e.message || 'Upload failed.'); }
    finally { setLoading(false); }
  };

  const metrics = summary || {};
  const navToUpload = () => setPage('Upload center');
  const knownPage = ['Overview', 'Data Sources', 'Registry Records', 'Ingestion Jobs', 'Upload center', 'API Keys', 'Data Quality', 'Warehouse', 'Validation Rules', 'Audit Logs', 'Settings'].includes(page);

  if (!authed && !checking) return <LoginPage password={password} setPassword={setPassword} onSubmit={signIn} error={error} busy={signingIn} />;

  return <div className="app-shell">
    {mobile && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobile(false)} />}
    <Sidebar page={page} setPage={setPage} mobile={mobile} setMobile={setMobile} connected={connected} />
    <main className="main-content">
      <Topbar page={page} connected={connected} onRefresh={refresh} loading={loading} search={search} setSearch={setSearch} setMobile={setMobile} onSignOut={signOut} previewMode={previewMode} onTogglePreview={() => setPreviewMode(v => !v)} failedJobs={jobs.filter(job => ['failed','error'].includes(String(job.status || '').toLowerCase()))} notificationsOpen={notificationsOpen} setNotificationsOpen={setNotificationsOpen} onViewJobs={() => setPage('Ingestion Jobs')} />
      <div className="page-content">
        {previewMode && <div className="alert-banner info"><ShieldCheck size={17}/><span>Preview mode is active. Write actions are disabled; data shown still comes from the connected backend.</span></div>}
        {error && <div className="alert-banner error"><AlertTriangle size={17} /><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error"><X size={16} /></button></div>}
        {message && <div className="alert-banner success"><CheckCircle2 size={17} /><span>{message}</span><button onClick={() => setMessage('')} aria-label="Dismiss message"><X size={16} /></button></div>}

        {page === 'Overview' && <>
          <div className="page-heading"><div><div className="eyebrow-label">REGISTRY OPERATIONS</div><h1>Datasource overview</h1><p>Monitor registry ingestion, data quality, and warehouse activity from one workspace.</p></div><div className="heading-actions"><button className="button-secondary" onClick={() => setPage('Ingestion Jobs')}>View jobs</button><button className="button-primary" onClick={navToUpload} disabled={previewMode} title={previewMode ? 'Disable Preview mode to upload data' : undefined}><Upload size={16} /> Upload dataset</button></div></div>
          <div className="metric-grid">
            <MetricCard icon={Building2} label="Indexed organizations" value={summary ? number(metrics.total_organizations) : '—'} note="Persisted registry records" />
            <MetricCard icon={Workflow} label="Ingestion jobs" value={summary ? number(metrics.total_jobs) : '—'} note="Tracked import runs" accent="mint" />
            <MetricCard icon={CheckCircle2} label="Completed jobs" value={summary ? number(metrics.completed_jobs) : '—'} note="Successfully processed" accent="green" />
            <MetricCard icon={AlertCircle} label="Failed jobs" value={summary ? number(metrics.failed_jobs) : '—'} note="May require investigation" accent="amber" />
          </div>
          <div className="dashboard-grid">
            <section className="panel activity-panel"><div className="panel-heading"><div><h2>Ingestion activity</h2><p>Processed and inserted records from recent jobs</p></div><span className="panel-period"><Activity size={14} /> Recent activity</span></div>{summary?.enabled_sources_count === 0 ? <div className="chart-empty"><Activity size={25} /><strong>Activity will appear here</strong><span>Connect the API and process ingestion jobs to populate this chart.</span><button className="button-link" onClick={() => setPage('Data Sources')}>Connect a source <ArrowRight size={15} /></button></div> : <WidgetErrorBoundary label="Ingestion activity"><ActivityChart jobs={jobs} /></WidgetErrorBoundary>}</section>
            <section className="panel"><WidgetErrorBoundary label="Data quality"><QualityPanel summary={summary} /></WidgetErrorBoundary></section>
          </div>
          <section className="panel jobs-panel"><div className="panel-heading"><div><h2>Recent ingestion jobs</h2><p>Latest persisted pipeline activity</p></div><button className="button-link" onClick={() => setPage('Ingestion Jobs')}>View all jobs <ArrowRight size={15} /></button></div><WidgetErrorBoundary label="Recent ingestion jobs"><JobsTable jobs={jobs} compact search={search} /></WidgetErrorBoundary></section>
          <section className="infra-section"><div className="section-title"><div><h2>Infrastructure health</h2><p>Connection state reported by the current datasource session</p></div><span className="health-summary"><i /> {connected ? 'API reachable' : 'Awaiting connection'}</span></div><div className="service-grid"><ServiceStatus label="Registry API" detail="Datasource application" value={connected ? 'Connected' : 'Not connected'} connected={connected} icon={Server} /><ServiceStatus label="Database metrics" detail="Registry data access" value={summary ? 'Available' : 'Unknown'} connected={!!summary} icon={Database} /><ServiceStatus label="External verification" detail="KRA / BRS integrations" value="Not verified" connected={false} icon={ShieldCheck} /></div></section>
        </>}

        {page === 'Data Sources' && <WidgetErrorBoundary label="Data Sources"><DataSourcesPanel onUpload={() => setPage('Upload center')} readOnly={previewMode} searchTerm={search} /></WidgetErrorBoundary>}
        {page === 'Ingestion Jobs' && <section className="panel full-panel"><div className="panel-heading"><div><h2>Ingestion jobs</h2><p>{number(jobsTotal)} persisted jobs · page {jobsPage} of {Math.max(1, Math.ceil(jobsTotal / 25))}.</p></div><div className="heading-actions"><button className="button-secondary" onClick={refresh} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : ''} /> Refresh</button><button className="button-primary" onClick={navToUpload} disabled={previewMode} title={previewMode ? "Disable Preview mode to upload data" : undefined}><Upload size={15}/> Upload dataset</button></div></div><WidgetErrorBoundary label="Ingestion jobs"><JobsTable jobs={jobs} search={search} /><div className="pagination"><span>Showing {jobsTotal ? ((jobsPage - 1) * 25 + 1) : 0}–{Math.min(jobsPage * 25, jobsTotal)} of {number(jobsTotal)} jobs</span><div><button className="button-secondary" disabled={loading || jobsPage <= 1} onClick={() => setJobsPage(p => Math.max(1, p - 1))}>Previous</button><button className="button-secondary" disabled={loading || jobsPage >= Math.max(1, Math.ceil(jobsTotal / 25))} onClick={() => setJobsPage(p => p + 1)}>Next</button></div></div></WidgetErrorBoundary></section>}
        {page === 'Registry Records' && <WidgetErrorBoundary label="Registry Records"><section className="panel full-panel"><div className="panel-heading"><div><h2>Registry records</h2><p>Search imported organizations and inspect source information.</p></div><span className="record-count">{number(orgTotal)} records</span></div><OrganizationsTable rows={orgs} total={orgTotal} page={orgPage} pageSize={100} onPageChange={setOrgPage} /></section></WidgetErrorBoundary>}
        {page === 'API Keys' && <WidgetErrorBoundary label="API Keys"><ApiKeysPanel readOnly={previewMode} searchTerm={search} /></WidgetErrorBoundary>}
        {['Data Quality', 'Warehouse', 'Validation Rules', 'Audit Logs', 'Settings'].includes(page) && <WidgetErrorBoundary label={page}><WorkspaceModulePage page={page} searchTerm={search} /></WidgetErrorBoundary>}
        {page === 'Upload center' && <WidgetErrorBoundary label="Upload center"><section className="panel upload-panel"><div className="panel-heading"><div><h2>Upload dataset</h2><p>Submit registry files for asynchronous ingestion.</p></div><div className="heading-icon"><Upload size={18} /></div></div><form onSubmit={upload} className="upload-form"><label className="dropzone"><input type="file" accept=".csv,.pdf" onChange={e => setFile(e.target.files?.[0] || null)} /><span className="dropzone-icon"><Upload size={25} /></span><strong>{file ? file.name : 'Choose a dataset to upload'}</strong><span>{file ? `${(file.size / 1048576).toFixed(2)} MB · ready to submit` : 'Drag a file here or browse from your device'}</span><small>CSV and PDF · backend size limits apply</small></label><div className="upload-actions"><p>Only upload datasets you are authorized to process. PDF files may be stored even where structured extraction is not yet enabled.</p><button className="button-primary" disabled={!file || loading || previewMode}>{loading ? 'Submitting…' : <><Upload size={16} /> Queue import</>}</button></div></form></section></WidgetErrorBoundary>}
        {!knownPage && <section className="coming-soon panel"><div className="coming-icon"><Database size={25} /></div><span className="eyebrow-label">DATASOURCE MODULE</span><h2>{page}</h2><p>This navigation entry is reserved for the {page.toLowerCase()} workspace. Its production data view has not been connected yet, so this screen does not display fabricated records.</p><button className="button-secondary" onClick={() => setPage('Overview')}>Return to overview</button></section>}
        <footer className="page-footer"><span>© PesaGuard Datasource</span><span className="compliance-state"><ShieldCheck size={14}/>{typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'HTTPS transport' : 'HTTPS not verified'}<i/>RLS: not verified</span><span><span className={connected ? 'footer-status-dot' : 'footer-status-dot muted'} />{connected ? 'Connected to datasource API' : 'Local preview · not connected'}</span></footer>
      </div>
    </main>
  </div>;
}
