import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchDevices, deleteDevice, deployDevice } from '../services/api';

export default function Devices() {
  const [devices, setDevices] = useState<any[]>([]);
  const [filter, setFilter] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [menu, setMenu] = useState<{x:number,y:number,id:string}|null>(null);
  const [deploying, setDeploying] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = async () => { try { setDevices(await fetchDevices()); } catch(_){} };
  useEffect(() => { load(); }, []);
  useEffect(() => { const h = setInterval(load, 15000); return () => clearInterval(h); }, []);
  useEffect(() => { const h = () => setMenu(null); window.addEventListener('click', h); return () => window.removeEventListener('click', h); }, []);

  const handleDeploy = async (d: any) => {
    if (!confirm(`Deploy ${d.name}? This applies the ISP config and uploads it to the ISP inventory.`)) return;
    setDeploying(d.id);
    try {
      const res = await deployDevice({ device_id: d.id });
      const setupOk = res.setup?.success;
      const upload = res.isp_upload;
      const uploadOk = upload ? (upload.success ? 'ISP upload OK' : `ISP upload FAILED: ${upload.error || 'see logs'}`) : 'ISP upload skipped';
      alert(`${setupOk ? 'Deploy succeeded' : 'Deploy failed'} (${res.setup?.errors?.length || 0} errors)\n${uploadOk}`);
    } catch (e: any) {
      alert(`Deploy error: ${e?.response?.data?.detail || e.message}`);
    }
    setDeploying(null);
    await load();
  };

  const filtered = devices.filter(d =>
    !filter || d.name.toLowerCase().includes(filter.toLowerCase()) || (d.ip_address||'').includes(filter) || d.brand.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div>
      <h1>Devices</h1>
      <div style={{ marginBottom: 8, display: 'flex', gap: 6, alignItems: 'center' }}>
        <input placeholder="Search..." value={filter} onChange={e => setFilter(e.target.value)} style={{ width: 250 }} />
        <span style={{ color: '#666', fontSize: 11 }}>{devices.length} device{devices.length!==1?'s':''}</span>
        <button style={{ marginLeft: 'auto' }} onClick={() => navigate('/setup')}>Add Device</button>
      </div>

      <table>
        <thead>
          <tr><th>Name</th><th>Brand</th><th>IP Address</th><th>MAC</th><th>DHCP</th><th>Status</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {filtered.map(d => (
            <tr key={d.id} className={selected === d.id ? 'selected' : ''} onClick={() => setSelected(d.id)}
              onContextMenu={e => { e.preventDefault(); setMenu({x:e.clientX, y:e.clientY, id:d.id}); }}>
              <td><a href={`/remote/${d.id}`} onClick={e => e.stopPropagation()}>{d.name}</a></td>
              <td>{d.brand}</td>
              <td style={{ fontFamily: 'monospace' }}>{d.ip_address || '--'}</td>
              <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{d.mac_address || '--'}</td>
              <td><span className={`badge ${d.dhcp_mode==='disabled'?'badge-success':'badge-warning'}`}>{d.dhcp_mode}</span></td>
              <td><span className={`indicator ${d.is_online ? 'indicator-online' : 'indicator-offline'}`}/>{d.is_online?'Online':'Offline'}</td>
              <td onClick={e => e.stopPropagation()}>
                <button className="btn-sm" onClick={() => navigate(`/remote/${d.id}`)}>Connect</button>
                <button className="btn-sm" onClick={() => navigate(`/diagnostics`)} style={{marginLeft:4}}>Diagnose</button>
                <button className="btn-sm" onClick={() => handleDeploy(d)} disabled={deploying===d.id} style={{marginLeft:4}}>
                  {deploying===d.id ? 'Deploying...' : 'Deploy'}
                </button>
                <button className="btn-sm btn-danger" onClick={async () => { if (confirm(`Delete ${d.name}?`)) { await deleteDevice(d.id); await load(); } }} style={{marginLeft:4}}>Delete</button>
              </td>
            </tr>
          ))}
          {filtered.length === 0 && <tr><td colSpan={7} style={{textAlign:'center',padding:20,color:'#666'}}>No devices found</td></tr>}
        </tbody>
      </table>

      {menu && (
        <div className="context-menu" style={{ left: menu.x, top: menu.y, position: 'fixed' }}
          onClick={e => e.stopPropagation()}>
          <button onClick={() => { navigate(`/remote/${menu.id}`); setMenu(null); }}>Connect / Remote Access</button>
          <button onClick={() => { navigate('/diagnostics'); setMenu(null); }}>Run Diagnostics</button>
          <button onClick={async () => { const d = devices.find(x => x.id === menu.id); setMenu(null); if (d) await handleDeploy(d); }}>Deploy CPE</button>
          <hr />
          <button onClick={async () => { await deleteDevice(menu.id); await load(); setMenu(null); }} style={{color:'#c00'}}>Delete Device</button>
        </div>
      )}
    </div>
  );
}
