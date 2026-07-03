import { useState } from 'react';
import { setupBulk } from '../services/api';

export default function BulkSetup() {
  const [text, setText] = useState('');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('admin');
  const [concurrent, setConcurrent] = useState(5);
  const [dhcpOff, setDhcpOff] = useState(true);
  const [bridgeOn, setBridgeOn] = useState(true);
  const [autoPass, setAutoPass] = useState(true);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<any[]>([]);

  const count = text.trim().split('\n').filter(Boolean).length;

  const handleStart = async () => {
    if (!text.trim()) return;
    setRunning(true);
    setResults([]);
    try {
      const devs = text.trim().split('\n').filter(Boolean).map(line => {
        const p = line.trim().split(/\s+/);
        return { ip_address: p[0], brand: p[1] || 'generic', username: p[2] || username, current_password: p[3] || password,
          admin_username: p[2] || username, disable_dhcp: dhcpOff, enable_bridge: bridgeOn };
      });
      const res = await setupBulk({ devices: devs, max_concurrent: concurrent });
      setResults(res.results || []);
    } catch(_) {}
    setRunning(false);
  };

  return (
    <div>
      <h1>Bulk Setup</h1>
      <div style={{display:'flex',gap:8}}>
        <div style={{flex:1}}>
          <fieldset>
            <legend>Device List ({count} devices)</legend>
            <textarea value={text} onChange={e => setText(e.target.value)} rows={16}
              style={{width:'100%',fontFamily:'monospace',fontSize:12}}
              placeholder="192.168.0.10\n192.168.0.11 mikrotik\n192.168.0.12 tplink admin pass123\n\nFormat: IP [brand] [user] [pass]" />
          </fieldset>

          <fieldset>
            <legend>Settings</legend>
            <table style={{border:'none'}}><tbody>
              <tr><td style={{border:'none',padding:2}}><label>Default User:</label></td><td style={{border:'none',padding:2}}><input value={username} onChange={e=>setUsername(e.target.value)} style={{width:180}} /></td></tr>
              <tr><td style={{border:'none',padding:2}}><label>Default Pass:</label></td><td style={{border:'none',padding:2}}><input type="password" value={password} onChange={e=>setPassword(e.target.value)} style={{width:180}} /></td></tr>
              <tr><td style={{border:'none',padding:2}}><label>Max Concurrent:</label></td><td style={{border:'none',padding:2}}><input type="number" value={concurrent} onChange={e=>setConcurrent(+e.target.value)} style={{width:80}} min={1} max={20} /></td></tr>
            </tbody></table>
            <div style={{marginTop:8}}>
              <label style={{display:'flex',alignItems:'center',gap:4,marginBottom:3}}><input type="checkbox" checked={dhcpOff} onChange={e=>setDhcpOff(e.target.checked)} />Disable DHCP</label>
              <label style={{display:'flex',alignItems:'center',gap:4,marginBottom:3}}><input type="checkbox" checked={bridgeOn} onChange={e=>setBridgeOn(e.target.checked)} />Enable Bridge Mode</label>
              <label style={{display:'flex',alignItems:'center',gap:4}}><input type="checkbox" checked={autoPass} onChange={e=>setAutoPass(e.target.checked)} />Auto-generate passwords</label>
            </div>
          </fieldset>

          <button className="btn-primary btn-lg" onClick={handleStart} disabled={running || !text.trim()}
            style={{width:'100%'}}>
            {running ? `Configuring ${count} devices...` : `Configure ${count} Devices`}
          </button>
        </div>

        <div style={{flex:1}}>
          <fieldset>
            <legend>Results</legend>
            {results.length === 0 && !running && <div style={{color:'#666',fontSize:12,padding:20,textAlign:'center'}}>Results appear here</div>}
            {running && <div style={{textAlign:'center',padding:20}}>Running...</div>}
            <div style={{maxHeight:500,overflow:'auto'}}>
              {results.map((r,i) => (
                <div key={i} style={{padding:'4px 6px',borderBottom:'1px solid #ccc',fontSize:12,
                  background: r.success ? '#e8f5e8' : '#fde8e8' }}>
                  <b>{r.ip}</b> -- {r.success ? <span style={{color:'#080'}}>OK</span> : <span style={{color:'#c00'}}>FAILED</span>}
                  {r.brand && ` -- ${r.brand} ${r.model||''}`}
                  {r.errors?.length > 0 && <div style={{color:'#c00',marginTop:2}}>{r.errors[0]}</div>}
                </div>
              ))}
            </div>
          </fieldset>
        </div>
      </div>
    </div>
  );
}
