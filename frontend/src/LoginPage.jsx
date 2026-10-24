import React,{useState} from 'react';
import {ArrowRight,Database,Eye,EyeOff,LockKeyhole,ShieldCheck,Activity} from 'lucide-react';
export default function LoginPage({password,setPassword,onSubmit,error,busy=false}){
 const [visible,setVisible]=useState(false);
 return <main className="login-screen">
  <section className="login-story"><div className="login-brand"><img className="login-logo" src="/pesaguard-logo.svg" alt="PesaGuard" /></div>
   <div className="login-story-main"><div className="login-eyebrow"><i/> FINANCIAL DATA INFRASTRUCTURE</div><h1>Reliable data.<br/><em>Clear decisions.</em></h1><p>Ingest, validate and inspect registry data from one operational workspace.</p>
    <div className="login-benefits"><div><span><ShieldCheck size={17}/></span><div><strong>Controlled access</strong><small>Server-managed session and CSRF protection</small></div></div><div><span><Database size={17}/></span><div><strong>Traceable data operations</strong><small>Inspect persisted sources and ingestion outcomes</small></div></div><div><span><Activity size={17}/></span><div><strong>Operational visibility</strong><small>See actual backend status, never fabricated activity</small></div></div></div>
   </div><footer><span>© {new Date().getFullYear()} PesaGuard</span><span><i/> Secure workspace</span></footer>
  </section>
  <section className="login-form-side"><div className="login-form-wrap"><div className="login-mobile-brand"><img className="login-logo" src="/pesaguard-logo.svg" alt="PesaGuard" /></div>
   <div className="login-heading"><span className="login-lock"><LockKeyhole size={20}/></span><div className="login-form-eyebrow">WORKSPACE ACCESS</div><h2>Welcome back</h2><p>Sign in to continue to your datasource workspace.</p></div>
   {error&&<div className="login-error" role="alert"><ShieldCheck size={16}/><span>{error}</span></div>}
   <form className="login-form" onSubmit={onSubmit}><label htmlFor="admin-password">Admin password</label><div className="login-password"><LockKeyhole size={16}/><input id="admin-password" type={visible?'text':'password'} value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" placeholder="Enter your admin password" required autoFocus/><button type="button" aria-label={visible?'Hide password':'Show password'} onClick={()=>setVisible(v=>!v)}>{visible?<EyeOff size={17}/>:<Eye size={17}/>}</button></div>
    <p className="login-hint"><ShieldCheck size={14}/> Password is verified by the backend. Session cookies are HttpOnly.</p><button className="login-submit" disabled={busy||!password}>{busy?'Signing in…':<>Sign in to workspace <ArrowRight size={17}/></>}</button>
   </form><div className="login-help"><strong>Need access?</strong><p>Contact your PesaGuard workspace administrator to obtain an authorized admin credential.</p></div><div className="login-legal">Access is monitored. Sign in only if you are authorized to use this workspace.</div>
  </div></section>
 </main>;
}
