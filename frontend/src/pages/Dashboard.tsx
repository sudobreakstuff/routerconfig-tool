import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchDevices, fetchJobs, scanNetwork } from '../services/api';

export default function Dashboard() {
  const [devices, setDevices] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [nearby, setNearby] = useState<any[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    fetchDevices().then(setDevices).catch(()=>{});
    fetchJobs().then(setJobs).catch(()=>{});
    scanNetwork('192.168.0.0/24').then(d => setNearby((d||[]).slice(0, 5))).catch(()=>{});
  }, []);

  const online = devices.filter(d => d.is_online).length;

  return (
    <div>
      <h1>Dashboard</h1>
      <p style={{ color: '#6b7280', marginBottom: 20, marginTop: -2 }}>Network infrastructure overview</p>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        <div className="card" style={{ padding: '16px 20px' }}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4, fontWeight: 500 }}>Devices</div>
          <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em' }}>{devices.length}</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{online} online</div>
        </div>
        <div className="card" style={{ padding: '16px 20px' }}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4, fontWeight: 500 }}>Uptime</div>
          <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em', color: '#16a34a' }}>
            {devices.length > 0 ? Math.round((online/devices.length)*100) : 0}<span style={{fontSize:16}}>%</span>
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>online ratio</div>
        </div>
        <div className="card" style={{ padding: '16px 20px' }}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4, fontWeight: 500 }}>Jobs</div>
          <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em' }}>{jobs.length}</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{jobs.filter(j=>j.status==='completed').length} completed</div>
        </div>
        <div className="card" style={{ padding: '16px 20px' }}>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4, fontWeight: 500 }}>Nearby</div>
          <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: '-0.02em' }}>{nearby.length}</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>discovered devices</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Quick Actions */}
        <div className="card" style={{ padding: 20 }}>
          <h2>Quick Actions</h2>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}>
            <button className="btn-primary" onClick={() => navigate('/setup')} style={{justifyContent:'flex-start'}}>
              + New Connection
            </button>
            <button onClick={() => navigate('/bulk')} style={{justifyContent:'flex-start'}}>
              Bulk Setup
            </button>
            <button onClick={() => navigate('/diagnostics')} style={{justifyContent:'flex-start'}}>
              Run Diagnostics
            </button>
            <button onClick={() => navigate('/remote')} style={{justifyContent:'flex-start'}}>
              Remote Terminal
            </button>
          </div>
          {nearby.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <h3 style={{ fontSize: 13 }}>Discovered Nearby</h3>
              <table style={{ marginTop: 8 }}>
                <thead><tr><th>IP</th><th>MAC</th><th>Ports</th><th></th></tr></thead>
                <tbody>
                  {nearby.map((d: any, i) => (
                    <tr key={i}>
                      <td style={{ fontFamily: 'monospace' }}>{d.ip}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{d.mac}</td>
                      <td style={{ fontSize: 11 }}>{(d.open_ports||[]).join(', ') || '--'}</td>
                      <td><button className="btn-sm" onClick={() => navigate(`/setup`)}>Connect</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Recent Activity */}
        <div className="card" style={{ padding: 20 }}>
          <h2>Recent Devices</h2>
          {devices.length > 0 ? (
            <table style={{ marginTop: 12 }}>
              <thead><tr><th>Name</th><th>IP</th><th>Brand</th><th>Status</th></tr></thead>
              <tbody>
                {devices.slice(0, 8).map(d => (
                  <tr key={d.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/remote/${d.id}`)}>
                    <td style={{ fontWeight: 500 }}>{d.name}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{d.ip_address || '--'}</td>
                    <td><span className="badge badge-info">{d.brand}</span></td>
                    <td>
                      <span className={`indicator ${d.is_online ? 'indicator-online' : 'indicator-offline'}`} />
                      {d.is_online ? 'Online' : 'Offline'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>
              <p>No devices configured.</p>
              <button className="btn-primary" style={{ marginTop: 12 }} onClick={() => navigate('/setup')}>
                Set Up Your First Router
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
