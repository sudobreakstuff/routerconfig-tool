import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { scanNetwork, testConnection, setupDevice, readDeviceConfig, openTunnel, createDevice } from '../services/api';

export default function SetupWizard() {
  const navigate = useNavigate();
  const [view, setView] = useState<'scan'|'review'|'config'|'run'>('scan');
  const [subnet, setSubnet] = useState('');
  const [devices, setDevices] = useState<any[]>([]);
  const [scanning, setScanning] = useState(false);
  const [ip, setIp] = useState('');
  const [user, setUser] = useState('admin');
  const [pass, setPass] = useState('admin');
  const [brand, setBrand] = useState('auto');
  const [testing, setTesting] = useState(false);
  const [reading, setReading] = useState(false);
  const [currentConfig, setCurrentConfig] = useState<any>(null);
  const [autoPw, setAutoPw] = useState(true);
  const [dhcpOff, setDhcpOff] = useState(true);
  const [bridgeOn, setBridgeOn] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [log, setLog] = useState<string[]>([]);
  const [testResult, setTestResult] = useState<any>(null);

  useEffect(() => { handleScan(); }, []);

  const handleScan = async () => {
    setScanning(true);
    try { setDevices(await scanNetwork(subnet || '192.168.0.0/24') || []); } catch (_) {}
    setScanning(false);
  };

  const handleTestAndRead = async () => {
    if (!ip) return;
    setTesting(true);
    setCurrentConfig(null);
    try {
      const tr = await testConnection({ host: ip, username: user, password: pass, brand, ssh_port: 22, web_port: 80 });
      if (tr.success) {
        // Save credentials to device DB so other features can use them
        try {
          await createDevice({
            name: `${brand !== 'auto' ? brand : 'device'} @ ${ip}`,
            ip_address: ip, brand: tr.brand || brand,
            admin_user: user, admin_password: pass,
          });
        } catch (_) {}
        setReading(true);
        try {
          const cfg = await readDeviceConfig({ host: ip, username: user, password: pass, brand, ssh_port: 22, web_port: 80 });
          setCurrentConfig(cfg);
        } catch (_) {}
        setReading(false);
        setView('review');
      } else {
        setTestResult(tr);
      }
    } catch (_) { setTestResult({ error: 'Connection failed', reachable: false }); }
    setTesting(false);
  };

  const handleSetup = async () => {
    setRunning(true);
    setLog([]);
    try {
      const payload: any = { ip_address: ip, brand, username: user, current_password: pass, admin_username: user, disable_dhcp: dhcpOff, enable_bridge: bridgeOn };
      const r = await setupDevice(payload);
      setResult(r);
      setLog(r.output_log || r.errors || []);
      setView('run');
    } catch (_) { setLog(['Setup failed']); }
    setRunning(false);
  };

  const handleTunnelToIp = async (targetIp: string) => {
    try {
      const res = await openTunnel({
        jump_host: ip,
        jump_username: user,
        jump_password: pass,
        jump_port: 22,
        target_ip: targetIp,
        target_port: 80,
      });
      window.open(res.local_url || `http://127.0.0.1:${res.local_port}`, '_blank');
    } catch (_) {
      window.open(`http://${targetIp}`, '_blank');
    }
  };

  return (
    <div>
      <h1>Setup Wizard</h1>
      <p style={{ color: '#6b7280', marginBottom: 16, marginTop: -2 }}>
        {view === 'scan' && 'Step 1: Discover and connect'}
        {view === 'review' && 'Step 2: Review current configuration'}
        {view === 'config' && 'Step 3: Apply new configuration'}
        {view === 'run' && 'Results'}
      </p>

      {view === 'scan' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <fieldset><legend>Network Discovery</legend>
            <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
              <input value={subnet} onChange={e => setSubnet(e.target.value)} style={{ width: 180 }} placeholder="192.168.0.0/24" />
              <button onClick={handleScan} disabled={scanning}>{scanning ? 'Scanning...' : 'Scan Network'}</button>
            </div>
            <div style={{ maxHeight: 350, overflow: 'auto' }}>
              {devices.length > 0 && (
                <table>
                  <thead><tr><th>IP</th><th>MAC</th><th>Hint</th><th>Ports</th><th></th></tr></thead>
                  <tbody>{devices.map((d, i) => (
                    <tr key={i} onClick={() => { setIp(d.ip); setBrand(d.brand_hint !== 'unknown' ? d.brand_hint : 'auto'); }}
                      style={{ cursor: 'pointer', background: ip === d.ip ? '#dbeafe' : undefined }}>
                      <td style={{ fontFamily: 'monospace', fontWeight: 500 }}>{d.ip}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{d.mac}</td>
                      <td><span className="badge badge-info">{d.brand_hint}</span></td>
                      <td style={{ fontSize: 11 }}>{(d.open_ports || []).join(', ') || '...'}</td>
                      <td><button className="btn-sm btn-primary" onClick={e => { e.stopPropagation(); setIp(d.ip); setBrand(d.brand_hint !== 'unknown' ? d.brand_hint : 'auto'); }}>Select</button></td>
                    </tr>
                  ))}</tbody>
                </table>
              )}
              {devices.length === 0 && !scanning && <div style={{ color: '#6b7280', fontSize: 12, padding: 16, textAlign: 'center' }}>No devices discovered on this subnet.</div>}
              {scanning && <div style={{ textAlign: 'center', padding: 16, color: '#6b7280' }}>Scanning network...</div>}
            </div>
          </fieldset>

          <fieldset><legend>Manual Connection</legend>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div><label>IP Address</label><br /><input value={ip} onChange={e => setIp(e.target.value)} style={{ width: '100%' }} onKeyDown={e => { if (e.key === 'Enter') handleTestAndRead(); }} placeholder="192.168.0.1" /></div>
              <div><label>Username</label><br /><input value={user} onChange={e => setUser(e.target.value)} style={{ width: '100%' }} onKeyDown={e => { if (e.key === 'Enter') handleTestAndRead(); }} /></div>
              <div><label>Password</label><br /><input type="password" value={pass} onChange={e => setPass(e.target.value)} style={{ width: '100%' }} onKeyDown={e => { if (e.key === 'Enter') handleTestAndRead(); }} /></div>
              <div style={{ fontSize: 11, color: '#6b7280', padding: '4px 8px', background: '#f9fafb', borderRadius: 4 }}>
                <b>Defaults:</b> MikroTik: admin / (blank) &middot; Ubiquiti: ubnt / ubnt &middot; TP-Link: admin / admin
              </div>
              <div><label>Brand</label><br /><select value={brand} onChange={e => setBrand(e.target.value)} style={{ width: '100%' }}>
                <option value="auto">Auto Detect</option>
                <option value="mikrotik">MikroTik</option>
                <option value="tplink">TP-Link</option>
                <option value="ubiquiti">Ubiquiti</option>
                <option value="generic">Generic</option>
              </select></div>
              <button className="btn-primary" onClick={handleTestAndRead} disabled={!ip || testing}
                style={{ alignSelf: 'flex-start', marginTop: 4 }}>
                {testing ? 'Connecting...' : reading ? 'Reading config...' : 'Connect & Read Config'}
              </button>
              {testResult && (
                <div style={{
                  padding: 10, borderRadius: 6, fontSize: 12, marginTop: 8,
                  background: testResult.success ? '#dcfce7' : testResult.reachable === false ? '#fef2f2' : '#fef9c3',
                  color: testResult.success ? '#16a34a' : testResult.reachable === false ? '#dc2626' : '#ca8a04',
                  border: `1px solid ${testResult.success ? '#86efac' : testResult.reachable === false ? '#fecaca' : '#fde047'}`,
                }}>
                  {testResult.reachable === false && 'Device not reachable. Check IP and connectivity.'}
                  {testResult.reachable && !testResult.auth && 'Reachable but authentication failed. Check credentials.'}
                  {testResult.error && !testResult.reachable && `Error: ${testResult.error}`}
                  {testResult.success && 'Connected successfully.'}
                  {testResult.ports?.length > 0 && <div style={{marginTop:4}}>Open ports: {testResult.ports.join(', ')}</div>}
                </div>
              )}
            </div>
          </fieldset>
        </div>
      )}

      {view === 'review' && currentConfig && (
        <div style={{ maxWidth: 750 }}>
          <div className="card" style={{ padding: 20, marginBottom: 16, borderColor: '#86efac' }}>
            <h2 style={{ color: '#16a34a', marginBottom: 4 }}>Connected to {currentConfig.model !== 'unknown' ? currentConfig.model : currentConfig.brand}</h2>
            <p style={{ color: '#6b7280', fontSize: 12, marginBottom: 16 }}>Review current configuration before applying changes.</p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
              <div><div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Model</div><div style={{ fontWeight: 500, wordBreak: 'break-word' }}>{currentConfig.model || 'unknown'}</div></div>
              <div><div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Firmware</div><div style={{ fontWeight: 500, wordBreak: 'break-word', fontSize: 12 }}>{currentConfig.firmware_version || 'unknown'}</div></div>
              <div><div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>MAC</div><div style={{ fontFamily: 'monospace', fontSize: 12 }}>{currentConfig.mac_address || 'unknown'}</div></div>
            </div>

            {/* Downstream devices discovered by scanning from the device */}
            {currentConfig.downstream_devices && currentConfig.downstream_devices.length > 0 && (
              <div style={{ marginBottom: 16, padding: 12, background: '#f0f9ff', borderRadius: 6, border: '1px solid #bae6fd' }}>
                <div style={{ fontSize: 11, color: '#0369a1', fontWeight: 600, marginBottom: 6 }}>
                  DEVICES FOUND ON NETWORK ({currentConfig.downstream_devices.length}) -- via SSH scan from {ip}
                </div>
                <table>
                  <thead><tr><th>IP</th><th>MAC</th><th>Source</th><th>Actions</th></tr></thead>
                  <tbody>
                    {currentConfig.downstream_devices.map((d: any, i: number) => (
                      <tr key={i}>
                        <td style={{ fontFamily: 'monospace', fontWeight: 500 }}>{d.ip}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{d.mac}</td>
                        <td><span className="badge badge-muted">{d.source}</span></td>
                        <td>
                          <div style={{ display: 'flex', gap: 4 }}>
                            <button onClick={() => handleTunnelToIp(d.ip)} className="btn-sm btn-primary">
                              Tunnel to Web UI
                            </button>
                            <button onClick={() => window.open(`http://${d.ip}`, '_blank')} className="btn-sm">
                              Direct
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Network IPs found */}
            {currentConfig.config_ips && currentConfig.config_ips.length > 0 && (
              <div style={{ marginBottom: 16, padding: 12, background: '#fefce8', borderRadius: 6, border: '1px solid #fde68a' }}>
                <div style={{ fontSize: 11, color: '#92400e', fontWeight: 600, marginBottom: 6 }}>ADDITIONAL IPs FROM CONFIG</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {currentConfig.config_ips.map((configIp: string, i: number) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 8px', background: '#fff', border: '1px solid #fde68a', borderRadius: 4, fontSize: 12 }}>
                      <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>{configIp}</span>
                      <button onClick={() => handleTunnelToIp(configIp)} className="btn-sm btn-primary" style={{ fontSize: 11 }}>
                        Tunnel
                      </button>
                      <button onClick={() => window.open(`http://${configIp}`, '_blank')} className="btn-sm" style={{ fontSize: 11 }}>
                        Direct
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
              <div><div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>DHCP Server</div>
                <span className={`badge ${currentConfig.dhcp_enabled ? 'badge-warning' : 'badge-success'}`}>
                  {currentConfig.dhcp_enabled ? 'ENABLED' : 'DISABLED'}
                </span>
              </div>
              <div><div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>WiFi Radio</div>
                <span className={`badge ${currentConfig.wifi_enabled ? 'badge-success' : 'badge-danger'}`}>
                  {currentConfig.wifi_enabled ? 'ON' : 'OFF'}
                </span>
              </div>
              <div><div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Bridge Mode</div>
                <span className={`badge ${currentConfig.bridge_mode ? 'badge-info' : 'badge-muted'}`}>
                  {currentConfig.bridge_mode ? 'YES' : 'NO'}
                </span>
              </div>
              <div><div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Connected Clients</div>
                <span style={{ fontWeight: 500 }}>{currentConfig.connected_clients ?? '--'}</span>
              </div>
            </div>

            {currentConfig.ssids && currentConfig.ssids.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600, marginBottom: 4 }}>SSIDs Found</div>
                {currentConfig.ssids.map((s: any, i: number) => (
                  <span key={i} className="badge badge-info" style={{ marginRight: 4 }}>{s.ssid || s}</span>
                ))}
              </div>
            )}

            {currentConfig.uptime && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600 }}>Uptime</div>
                <div style={{ fontFamily: 'monospace', fontSize: 12 }}>{currentConfig.uptime} seconds</div>
              </div>
            )}

            {currentConfig.running_config && Object.keys(currentConfig.running_config).length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 600, marginBottom: 4 }}>Raw Config</div>
                <pre style={{ maxHeight: 150, overflow: 'auto', fontSize: 11, padding: 8, background: '#f9fafb', borderRadius: 6, border: '1px solid #e5e7eb', lineHeight: 1.3, wordBreak: 'break-all', whiteSpace: 'pre-wrap' }}>
                  {typeof currentConfig.running_config.raw === 'string'
                    ? currentConfig.running_config.raw.slice(0, 2000)
                    : JSON.stringify(currentConfig.running_config, null, 2).slice(0, 2000)}
                </pre>
              </div>
            )}

            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn-primary" onClick={() => setView('config')}>
                Continue to Configuration
              </button>
              <button className="btn-primary" onClick={() => {
                // Save device first, then navigate to terminal
                fetch('/api/devices', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    name: `${currentConfig.model || brand} @ ${ip}`,
                    ip_address: ip, brand: brand,
                    admin_user: user, admin_password: pass,
                  }),
                }).then(r => r.json()).then(d => {
                  navigate(`/remote/${d.id || ''}`);
                }).catch(() => navigate('/remote'));
              }} style={{ background: '#059669', borderColor: '#059669' }}>
                Open Terminal Session
              </button>
              <button onClick={() => setView('scan')}>Back</button>
            </div>
          </div>
        </div>
      )}

      {view === 'review' && !currentConfig && reading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>Reading device configuration...</div>
      )}

      {view === 'config' && (
        <div style={{ maxWidth: 500 }}>
          <fieldset><legend>Security</legend>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <input type="checkbox" checked={autoPw} onChange={e => setAutoPw(e.target.checked)} />
              Auto-generate secure passwords
            </label>
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: -4, marginBottom: 8 }}>Generates cryptographically random WiFi and admin passwords.</p>
          </fieldset>

          <fieldset><legend>Network Configuration</legend>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <input type="checkbox" checked={dhcpOff} onChange={e => setDhcpOff(e.target.checked)} />
              Disable DHCP Server
            </label>
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: -4, marginBottom: 12 }}>CPE device handles DHCP. Router should not assign IPs.</p>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" checked={bridgeOn} onChange={e => setBridgeOn(e.target.checked)} />
              Enable Bridge / AP Mode
            </label>
            <p style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>Router passes traffic through from CPE without NAT.</p>
          </fieldset>

          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setView('review')}>Back</button>
            <button className="btn-primary btn-lg" onClick={handleSetup} disabled={running}>
              {running ? 'Configuring...' : 'Apply Configuration'}
            </button>
          </div>
        </div>
      )}

      {view === 'run' && (
        <div style={{ maxWidth: 600 }}>
          <div className="card" style={{ padding: 20, marginBottom: 16, borderColor: result?.success ? '#86efac' : '#fecaca' }}>
            <h2 style={{ color: result?.success ? '#16a34a' : '#dc2626' }}>{result?.success ? 'Configuration Applied' : 'Configuration Failed'}</h2>
            {result?.router_info && (
              <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
                <div><span style={{ color: '#6b7280' }}>Brand:</span> <b>{result.router_info.brand}</b></div>
                <div><span style={{ color: '#6b7280' }}>Model:</span> {result.router_info.model || '--'}</div>
                <div><span style={{ color: '#6b7280' }}>Firmware:</span> {result.router_info.firmware || '--'}</div>
                <div><span style={{ color: '#6b7280' }}>Duration:</span> {result.duration_ms ? (result.duration_ms/1000).toFixed(1)+'s' : '--'}</div>
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              {result?.device_id && <button className="btn-primary" onClick={() => navigate(`/remote/${result.device_id}`)}>Open Remote Access</button>}
              <button onClick={() => { setView('scan'); setResult(null); setLog([]); }}>Setup Another Router</button>
            </div>
          </div>
          {log.length > 0 && (
            <fieldset><legend>Output Log</legend>
              <pre style={{ maxHeight: 300, overflow: 'auto', fontSize: 12, lineHeight: 1.4, padding: 12, background: '#f9fafb', borderRadius: 6 }}>{log.join('\n')}</pre>
            </fieldset>
          )}
        </div>
      )}
    </div>
  );
}
