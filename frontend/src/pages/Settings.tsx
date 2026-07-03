import { useEffect, useState } from 'react';
import { fetchISPProfiles, createISPProfile, fetchDevices, uploadDeviceToISP, getAppSettings } from '../services/api';

export default function Settings() {
  const [app, setApp] = useState<any>({});
  const [profiles, setProfiles] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [np, setNp] = useState({ name:'', adapter_name:'jenny_internet', endpoint:'', api_key:'' });

  useEffect(() => {
    getAppSettings().then(setApp).catch(()=>{});
    fetchISPProfiles().then(setProfiles).catch(()=>{});
    fetchDevices().then(setDevices).catch(()=>{});
  }, []);

  const handleCreate = async () => {
    try {
      await createISPProfile({ name: np.name, adapter_name: np.adapter_name, upload_endpoint: np.endpoint||null, upload_api_key: np.api_key||null });
      setProfiles(await fetchISPProfiles());
      setShowNew(false);
    } catch(_) {}
  };

  const handleUpload = async (devId: string, profId: string) => {
    try { await uploadDeviceToISP({ device_id: devId, profile_id: profId }); } catch(_) {}
  };

  return (
    <div>
      <h1>Settings</h1>

      <fieldset>
        <legend>Application</legend>
        <div style={{fontSize:12}}>
          <div>Data Directory: <code>{app.data_dir || '~/.routerconfig'}</code></div>
          <div>Version: <b>{app.version || '1.0.0'}</b></div>
        </div>
      </fieldset>

      <fieldset>
        <legend>ISP Profiles <button onClick={()=>setShowNew(!showNew)} className="btn-sm" style={{marginLeft:8}}>Add</button></legend>

        {showNew && (
          <div style={{marginBottom:8,padding:8,background:'#ece9e1',border:'1px solid #999'}}>
            <div style={{display:'flex',gap:4,flexWrap:'wrap',alignItems:'center'}}>
              <label>Name:</label> <input value={np.name} onChange={e=>setNp({...np,name:e.target.value})} style={{width:150}} />
              <label>Adapter:</label> <select value={np.adapter_name} onChange={e=>setNp({...np,adapter_name:e.target.value})}>
                <option value="jenny_internet">Jenny Internet</option>
                <option value="custom">Custom</option>
              </select>
              <label>Endpoint:</label> <input value={np.endpoint} onChange={e=>setNp({...np,endpoint:e.target.value})} style={{width:200}} placeholder="https://api.isp.com/v1" />
              <label>API Key:</label> <input type="password" value={np.api_key} onChange={e=>setNp({...np,api_key:e.target.value})} style={{width:150}} />
              <button className="btn-primary btn-sm" onClick={handleCreate}>Save</button>
              <button className="btn-sm" onClick={()=>setShowNew(false)}>Cancel</button>
            </div>
          </div>
        )}

        {profiles.map((p:any) => (
          <div key={p.id} style={{padding:'4px 6px',borderBottom:'1px solid #ddd',display:'flex',alignItems:'center',justifyContent:'space-between',fontSize:12}}>
            <div><b>{p.name}</b> <span style={{color:'#666'}}>({p.adapter_name})</span></div>
            <select onChange={e => { if(e.target.value) handleUpload(e.target.value, p.id); e.target.value=''; }} defaultValue="" style={{fontSize:11}}>
              <option value="">Upload device...</option>
              {devices.map((d:any) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
        ))}
        {profiles.length===0 && <div style={{color:'#666',fontSize:12}}>No ISP profiles configured.</div>}
      </fieldset>

      <fieldset>
        <legend>Custom ISP Adapter</legend>
        <div style={{fontSize:12,color:'#666'}}>
          Edit <code>~/.routerconfig/isp_custom.json</code> for custom ISP integration:
        </div>
        <pre style={{background:'#fff',border:'1px solid #999',padding:8,fontSize:11,marginTop:4}}>{`{
  "upload_endpoint": "https://your-isp.com/api/devices",
  "api_key": "your-api-key",
  "dhcp": { "enabled": false },
  "wan": { "bridge_mode": true }
}`}</pre>
      </fieldset>
    </div>
  );
}
