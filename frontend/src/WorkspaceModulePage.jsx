import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Database, FileCheck2, RefreshCw, Search, Server, Settings2, ShieldCheck, ScrollText, HardDrive } from 'lucide-react';
import { api } from './api.js';

const MODULES = {
  'Data Quality': {
    endpoint: '/api/v1/admin/data-quality/overview', icon: FileCheck2, eyebrow: 'GOVERNANCE',
    title: 'Data quality', description: 'Measure registry completeness and review ingestion quality signals.',
    metrics: [
      ['total_records', 'Registry records', 'number'], ['complete_records', 'Complete records', 'number'],
      ['incomplete_records', 'Incomplete records', 'number'], ['ingestion_row_errors', 'Ingestion row errors', 'number'],
      ['completeness_percentage', 'Field completeness', 'percent'], ['unreviewed_records', 'Unreviewed records', 'number']
    ],
    note: 'Completeness measures presence of required fields. It does not prove that a registration number or KRA PIN is authentic.',
    details: d => [{label:'Required fields measured', value:(d.required_fields || []).join(', ') || 'Not available'}]
  },
  'Warehouse': {
    endpoint: '/api/v1/admin/warehouse/overview', icon: HardDrive, eyebrow: 'DATA OPERATIONS',
    title: 'Warehouse', description: 'Inspect persisted raw imports, storage footprint, and recorded warehouse access events.',
    metrics: [['raw_imports','Raw imports','number'],['stored_bytes','Stored bytes','bytes'],['warehouse_access_events','Access events','number'],['unresolved_dead_letter_rows','Unresolved dead-letter rows','number']],
    note: 'Only imports and access events recorded in this datasource database are shown. This is not a claim that external warehouse storage is healthy.',
    sections: [
      {key:'imports', title:'Recent raw imports', columns:[['file_name','File'],['content_type','Content type'],['byte_size','Size','bytes'],['source_name','Source'],['status','Status'],['created_at','Created','date']]},
      {key:'access_events', title:'Recent warehouse access', columns:[['caller_service','Caller'],['method','Method'],['endpoint','Endpoint'],['status_code','HTTP status'],['duration_ms','Duration (ms)'],['outcome','Outcome'],['created_at','Created','date']]}
    ]
  },
  'Validation Rules': {
    endpoint: '/api/v1/admin/validation/rules', icon: ShieldCheck, eyebrow: 'GOVERNANCE',
    title: 'Validation rules', description: 'Review the registry checks currently defined by application behavior.',
    metrics: [['total','Defined checks','number']],
    note: 'These checks are application-defined and read-only. This deployment does not have a persisted, user-editable validation-rule model.',
    sections: [{key:'items', title:'Current application checks', columns:[['name','Rule'],['field','Field'],['severity','Severity'],['status','Implementation'],['description','Description']]}]
  },
  'Audit Logs': {
    endpoint: '/api/v1/admin/audit/logs?limit=200', icon: ScrollText, eyebrow: 'ADMINISTRATION',
    title: 'Audit logs', description: 'Review recent persisted datasource administration events.',
    metrics: [['count','Events returned','number']],
    note: 'The table lists recorded datasource audit events. It does not include every request or external service audit trail.',
    sections: [{key:'items', title:'Recent audit events', columns:[['created_at','Time','date'],['action','Action'],['actor','Actor'],['file_name','File'],['detail_fields','Recorded detail fields','join']]}]
  },
  'Settings': {
    endpoint: '/api/v1/admin/settings/overview', icon: Settings2, eyebrow: 'ADMINISTRATION',
    title: 'Workspace settings', description: 'Inspect safe runtime configuration and security controls for this datasource service.',
    metrics: [],
    note: 'Read-only diagnostics. Secret values are never sent to the browser and configuration changes must be made through the deployment environment.',
    settings: true
  }
};

const fmtNumber = value => value == null ? '—' : Number(value).toLocaleString();
const fmtBytes = value => {
  if (value == null) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (n < 1024) return n + ' B';
  const units = ['KB','MB','GB','TB']; let v=n/1024, i=0;
  while(v>=1024 && i<units.length-1){v/=1024;i++}
  return v.toFixed(1)+' '+units[i];
};
const fmtDate = value => {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
};
const renderValue = (value, type) => {
  if (type === 'number') return fmtNumber(value);
  if (type === 'percent') return value == null ? 'Not available' : Number(value).toFixed(1)+'%';
  if (type === 'bytes') return fmtBytes(value);
  if (type === 'date') return fmtDate(value);
  if (type === 'join') return Array.isArray(value) ? value.join(', ') || '—' : (value ?? '—');
  if (typeof value === 'boolean') return value ? 'Enabled' : 'Disabled';
  if (value == null || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

function Table({ rows, columns, query }) {
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const filtered = useMemo(() => (rows || []).filter(row => columns.some(([key]) => renderValue(row[key]).toLowerCase().includes(query.toLowerCase()))), [rows,columns,query]);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  useEffect(() => { setPage(1); }, [query, rows]);
  if (!filtered.length) return <div className="module-empty"><Database size={24}/><strong>{query ? 'No matching records' : 'No records available yet'}</strong><span>{query ? 'Try a different search.' : 'The backend has not returned any records for this section.'}</span></div>;
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize);
  return <>
    <div className="table-scroll"><table className="data-table module-table"><thead><tr>{columns.map(([key,label])=><th key={key}>{label}</th>)}</tr></thead><tbody>{visible.map((row,i)=><tr key={row.id || row.job_id || row.request_id || i}>{columns.map(([key,,type])=><td key={key} className={key==='endpoint'||key==='description'?'module-wrap':''}>{renderValue(row[key],type)}</td>)}</tr>)}</tbody></table></div>
    {filtered.length > pageSize && <div className="pagination"><span>Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filtered.length)} of {filtered.length} records</span><div><button className="button-secondary" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>Previous</button><button className="button-secondary" disabled={page >= pages} onClick={() => setPage(p => Math.min(pages, p + 1))}>Next</button></div></div>}
  </>;
}

function SettingsGrid({ data }) {
  const groups = [
    ['Runtime', [['environment','Environment'],['api_environment','API environment']]],
    ['Database', [['database.configured','Database URL configured'],['database.engine','Database engine']]],
    ['Object storage', [['object_storage.configured','Credentials configured']]],
    ['Rate limiting & sessions', [['redis.configured','Redis configured'],['operator_session.distributed_rate_limit_configured','Distributed rate limit'],['operator_session.http_only_cookie','HttpOnly session cookie'],['operator_session.secure_cookie','Secure cookie'],['operator_session.same_site','SameSite policy'],['operator_session.ttl_seconds','Session TTL (seconds)']]],
    ['Browser access', [['cors_origins','Allowed CORS origins'],['metrics_token_configured','Metrics token configured'],['secrets_exposed','Secrets exposed']]]
  ];
  const get = path => path.split('.').reduce((v,k)=>v?.[k],data);
  return <div className="settings-grid">{groups.map(([title,fields])=><section className="panel settings-card" key={title}><div className="card-heading"><div><h2>{title}</h2><p>Live runtime configuration</p></div><ShieldCheck size={18}/></div>{fields.map(([path,label])=>{const value=get(path);const safe=value;return <div className="settings-row" key={path}><span>{label}</span><strong className={typeof safe==='boolean'?(path==='secrets_exposed'?(safe?'settings-warn':'settings-good'):(safe?'settings-good':'settings-warn')):''}>{renderValue(safe,Array.isArray(safe)?'join':undefined)}</strong></div>})}</section>)}</div>;
}

export default function WorkspaceModulePage({page, searchTerm=''}) {
  const config = MODULES[page];
  const [data,setData] = useState(null), [loading,setLoading] = useState(true), [error,setError] = useState(''), [query,setQuery] = useState('');
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { const response = await api(config.endpoint); setData(await response.json()); }
    catch (e) { setError(e.message || 'Unable to load this workspace module.'); }
    finally { setLoading(false); }
  }, [config.endpoint]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setQuery(searchTerm || ''); }, [searchTerm]);
  if (!config) return null;
  const Icon = config.icon;
  return <div className="module-page">
    <div className="page-heading"><div><div className="eyebrow-label">{config.eyebrow}</div><h1>{config.title}</h1><p>{config.description}</p></div><div className="heading-actions"><button className="button-secondary" onClick={load} disabled={loading}><RefreshCw size={15} className={loading?'spin':''}/> Refresh</button></div></div>
    {error && <div className="alert-banner error"><AlertTriangle size={17}/><span>{error}</span><button onClick={()=>setError('')} aria-label="Dismiss error">×</button></div>}
    {config.note && <div className="alert-banner info"><ShieldCheck size={16}/><span>{config.note}</span></div>}
    {loading && !data ? <div className="module-metric-grid">{[1,2,3,4].map(n=><div className="metric-card" key={n}><span className="metric-skeleton" style={{display:'block',height:18,width:'65%'}}/><span className="metric-skeleton" style={{display:'block',height:32,width:'45%',marginTop:18}}/></div>)}</div> : data && <>
      {config.metrics.length>0 && <div className="module-metric-grid">{config.metrics.map(([key,label,type])=><article className="metric-card" key={key}><div className="metric-top"><span>{label}</span><span className="metric-icon green"><Icon size={17}/></span></div><div className="metric-value">{renderValue(data[key],type)}</div><div className="metric-note"><span>From persisted backend data</span></div></article>)}</div>}
      {config.settings && <SettingsGrid data={data}/>}
      {config.details?.(data).map(d=><section className="panel module-detail" key={d.label}><strong>{d.label}</strong><span>{d.value}</span></section>)}
      {config.sections?.map(section=><section className="panel module-section" key={section.key}><div className="panel-heading"><div><h2>{section.title}</h2><p>{(data[section.key]||[]).length.toLocaleString()} records returned by the backend</p></div><label className="module-search"><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Filter this table" aria-label="Filter table records"/></label></div><Table rows={data[section.key]||[]} columns={section.columns} query={query}/></section>)}
      <div className="module-source-line"><span><CheckCircle2 size={14}/> Source: {data.source || 'runtime configuration'}</span><span>Updated {fmtDate(data.generated_at)}</span></div>
    </>}
  </div>;
}
