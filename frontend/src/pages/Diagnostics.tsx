import { useEffect, useState } from 'react';
import { fetchDevices, runDiagnostics, getDiagnosticReports, bandwidthTest, fetchDevice } from '../services/api';

export default function Diagnostics() {
  const [devices, setDevices] = useState<any[]>([]);
  const [selId, setSelId] = useState('');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [reports, setReports] = useState<any[]>([]);
  const [user, setUser] = useState('admin');
  const [pass, setPass] = useState('');
  const [bwResult, setBwResult] = useState<any>(null);
  const [bwLoading, setBwLoading] = useState(false);

  useEffect(() => { fetchDevices().then(setDevices).catch(()=>{}); }, []);
  useEffect(() => {
    if (selId) {
      fetchDevice(selId, true).then((dd: any) => {
        setUser(dd.admin_username || '');
        setPass(dd.admin_password || '');
      }).catch(() => {});
      getDiagnosticReports(selId).then(setReports).catch(()=>{});
    }
  }, [selId]);

  const handleRun = async () => {
    if (!selId) return;
    setLoading(true);
    setReport(null);
    try {
      const dev = devices.find(d => d.id === selId);
      const res = await runDiagnostics({
        device_id: selId,
        host: dev?.ip_address,
        username: user,
        password: pass,
        brand: dev?.brand,
      });
      setReport(res);
      setReports(await getDiagnosticReports(selId));
    } catch(_) {}
    setLoading(false);
  };

  const handleBandwidthTest = async () => {
    if (!selId) return;
    setBwLoading(true);
    setBwResult(null);
    try {
      const dev = devices.find(d => d.id === selId);
      const res = await bandwidthTest({
        host: dev?.ip_address,
        username: user,
        password: pass,
        brand: dev?.brand,
      });
      setBwResult(res);
    } catch(_) {}
    setBwLoading(false);
  };

  return (
    <div>
      <h1>Diagnostics</h1>
      <p style={{ color: '#6b7280', fontSize: 12, marginBottom: 12 }}>Run connectivity and health checks on a device</p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <select value={selId} onChange={e => setSelId(e.target.value)} style={{ minWidth: 220 }}>
          <option value="">Select a device...</option>
          {devices.map(d => <option key={d.id} value={d.id}>{d.name} ({d.ip_address||'?'})</option>)}
        </select>
        <input value={user} onChange={e => setUser(e.target.value)} placeholder="SSH Username" style={{ width: 150 }} />
        <input type="password" value={pass} onChange={e => setPass(e.target.value)} placeholder="SSH Password" style={{ width: 160 }} />
        {(!user || !pass) && selId && (
          <span style={{ fontSize: 11, color: '#dc2626' }}>No SSH credentials stored. Run Setup Wizard first, or enter manually.</span>
        )}
        <button className="btn-primary" onClick={handleRun} disabled={!selId || loading}>
          {loading ? 'Running...' : 'Run Diagnostics'}
        </button>
        <button onClick={handleBandwidthTest} disabled={!selId || bwLoading} style={{ marginLeft: 4 }}>
          {bwLoading ? 'Testing...' : 'Bandwidth Test'}
        </button>
      </div>

      {report && (
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <div style={{ flex: 1 }}>
            {bwResult && (
              <div className="card" style={{ padding: 16, marginBottom: 12, borderColor: '#bae6fd' }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Bandwidth Test Results</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                  <div><div style={{ fontSize: 11, color: '#6b7280' }}>Download</div><div style={{ fontSize: 22, fontWeight: 800 }}>{bwResult.download_mbps || '--'}<span style={{ fontSize: 13, fontWeight: 400 }}> Mbps</span></div></div>
                  <div><div style={{ fontSize: 11, color: '#6b7280' }}>Upload</div><div style={{ fontSize: 22, fontWeight: 800 }}>{bwResult.upload_mbps || '--'}<span style={{ fontSize: 13, fontWeight: 400 }}> Mbps</span></div></div>
                  <div><div style={{ fontSize: 11, color: '#6b7280' }}>Latency</div><div style={{ fontSize: 22, fontWeight: 800 }}>{bwResult.latency_ms || '--'}<span style={{ fontSize: 13, fontWeight: 400 }}> ms</span></div></div>
                </div>
                <div style={{ fontSize: 10, color: '#6b7280', marginTop: 4 }}>Method: {bwResult.method || '--'}</div>
              </div>
            )}

            <div className="card" style={{ padding: 16, marginBottom: 12, borderColor: report.is_healthy ? '#86efac' : '#fecaca' }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: report.is_healthy ? '#16a34a' : '#dc2626' }}>
                {report.is_healthy ? 'All Tests Passed' : `${report.issues_found} Issue(s) Found`}
              </div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                {report.issues_found} critical, {report.warnings_found} warnings
              </div>
            </div>

            <div className="card" style={{ marginBottom: 12 }}>
              <div style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', fontWeight: 600, fontSize: 13 }}>Test Results</div>
              <div style={{ padding: 4 }}>
                {(report.tests || []).map((t: any, i: number) => (
                  <div key={i} style={{
                    padding: '10px 14px',
                    borderBottom: i < (report.tests||[]).length - 1 ? '1px solid #f3f4f6' : 'none',
                    background: t.passed ? 'transparent' : t.severity === 'critical' ? '#fef2f2' : '#fef9c3',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{
                        fontWeight: 700, fontSize: 12, minWidth: 42,
                        color: t.passed ? '#16a34a' : '#dc2626',
                      }}>
                        {t.passed ? 'PASS' : 'FAIL'}
                      </span>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600 }}>{t.name}</div>
                        <div style={{ fontSize: 12, color: t.passed ? '#374151' : '#991b1b', marginTop: 1 }}>{t.message}</div>
                        {t.detail && <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>{t.detail}</div>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {(report.differences || []).length > 0 && (
              <div className="card">
                <div style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', fontWeight: 600, fontSize: 13 }}>Config Differences</div>
                <div style={{ padding: 4 }}>
                  {(report.differences || []).map((d: any, i: number) => (
                    <div key={i} style={{ padding: '8px 14px', borderBottom: '1px solid #f3f4f6', fontSize: 12 }}>
                      <div style={{ fontFamily: 'monospace', fontSize: 11, color: d.severity === 'critical' ? '#dc2626' : '#ca8a04', marginBottom: 2 }}>{d.path}</div>
                      <div style={{ color: '#374151' }}>{d.current}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div style={{ width: 220, flexShrink: 0 }}>
            <div className="card">
              <div style={{ padding: '10px 14px', borderBottom: '1px solid #e5e7eb', fontWeight: 600, fontSize: 13 }}>History</div>
              <div style={{ maxHeight: 400, overflow: 'auto' }}>
                {reports.map((r: any) => (
                  <div key={r.id} style={{ padding: '8px 14px', borderBottom: '1px solid #f3f4f6', fontSize: 11 }}>
                    <div style={{ fontWeight: 600, color: r.is_healthy ? '#16a34a' : '#dc2626' }}>{r.is_healthy ? 'Healthy' : `${r.issues_found} issues`}</div>
                    <div style={{ color: '#6b7280' }}>{r.issues_found} critical, {r.warnings_found} warnings</div>
                    <div style={{ color: '#9ca3af', fontSize: 10 }}>{new Date(r.created_at).toLocaleString()}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {!report && !loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#6b7280', fontSize: 12 }}>
          Select a device, enter credentials, and click Run Diagnostics.
        </div>
      )}
    </div>
  );
}
