import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Terminal as XTerm } from 'xterm';
import 'xterm/css/xterm.css';
import { fetchDevices, fetchDevice, updateDevice, persistentConnect, persistentDisconnect, runSshCommand, scanFromDevice, checkTunnel, openTunnelUrl } from '../services/api';

export default function RemoteAccess() {
  const { deviceId } = useParams();
  const navigate = useNavigate();
  const termRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);

  const [devices, setDevices] = useState<any[]>([]);
  const [selId, setSelId] = useState(deviceId || '');
  const [device, setDevice] = useState<any>(null);
  const [creds, setCreds] = useState<Record<string,string>>({ host:'', username:'', password:'' });
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [scanned, setScanned] = useState<any[]>([]);
  const [aliases, setAliases] = useState<any[]>([]);
  const [aliasIp, setAliasIp] = useState('');
  const [cmdInput, setCmdInput] = useState('');
  const [output, setOutput] = useState('');

  useEffect(() => { fetchDevices().then(setDevices).catch(()=>{}); }, []);
  useEffect(() => {
    if (selId) {
      fetchDevice(selId, true).then(d => {
        setDevice(d);
        setCreds({ host: d.ip_address||'', username: d.admin_username||'', password: d.admin_password||'' });
      }).catch(()=>{});
    }
  }, [selId]);

  const addOutput = (t: string) => setOutput(prev => prev + t);

  const handleConnect = async () => {
    if (!creds.host) return;
    setConnecting(true);
    addOutput('\n[Connecting...]\n');
    try {
      const res = await persistentConnect(creds);
      setConnected(res.connected);
      if (res.connected) {
        addOutput(`Connected: ${res.model} | FW: ${res.firmware} | MAC: ${res.mac || '?'}\n\n`);
        if (selId) try { await updateDevice(selId, { admin_user: creds.username, admin_password: creds.password }); } catch(_) {}
        // Load existing aliases
        try {
          const o = await runSshCommand({ ...creds, command: 'cat /tmp/system.cfg 2>/dev/null | grep alias.ip' });
          const re = /ip=(\d+\.\d+\.\d+\.\d+)/g;
          const ips: string[] = []; let m;
          while ((m = re.exec(o.output||'')) !== null) ips.push(m[1]);
          setAliases([...new Set(ips)]);
          if (ips.length) addOutput(`Existing aliases: ${ips.join(', ')}\n\n`);
        } catch(_) {}
      } else {
        addOutput(`FAILED: ${res.error || 'check credentials'}\n`);
      }
    } catch(_) { addOutput('Connection error\n'); }
    setConnecting(false);
  };

  const handleDisconnect = () => {
    persistentDisconnect(creds);
    setConnected(false); setScanned([]);
    addOutput('\n[Disconnected]\n');
  };

  const handleScan = async () => {
    addOutput('\n[Scanning for downstream devices...]\n');
    try {
      const res = await scanFromDevice(creds);
      setScanned(res.devices || []);
      addOutput(`Found ${res.count} device(s):\n`);
      (res.devices||[]).forEach((d: any) => {
        addOutput(`  ${d.ip.padEnd(16)} ${d.mac.padEnd(18)} ${d.mac_vendor||''}\n`);
      });
      addOutput('\n');
    } catch(_) { addOutput('Scan failed\n'); }
  };

  const handleTunnel = async (target: string) => {
    addOutput(`\n[Opening tunnel to ${target}...]\n`);
    try {
      const res = await openTunnelUrl({ ...creds, target });
      if (res.url) {
        addOutput(`Tunnel open: ${res.url}\n`);
        window.open(res.url, '_blank');
      } else if (res.error) {
        addOutput(`Tunnel failed: ${res.error}\n`);
      }
    } catch(_) { addOutput('Tunnel failed - check backend\n'); }
  };

  const handleAddAlias = async () => {
    if (!aliasIp.trim()) return;
    const ip = aliasIp.trim();
    const subnet = ip.split('.').slice(0,3).join('.');
    addOutput(`\n[Adding alias ${ip}...]\n`);
    const cmds = [
      `echo "netconf.2.alias.1.ip=${ip}" >> /tmp/system.cfg`,
      `echo "netconf.2.alias.1.netmask=255.255.255.0" >> /tmp/system.cfg`,
      `echo "netconf.2.alias.1.status=enabled" >> /tmp/system.cfg`,
      `cfgmtd -w -p /etc/ 2>/dev/null || true`,
      `ifconfig eth0:1 ${ip} netmask 255.255.255.0 up 2>/dev/null || true`,
      `route add -net ${subnet}.0 netmask 255.255.255.0 eth0 2>/dev/null || true`,
    ];
    for (const c of cmds) { try { await runSshCommand({ ...creds, command: c }); } catch(_) {} }
    setAliases(prev => [...new Set([...prev, ip])]);
    addOutput(`Done\n`);
    setAliasIp('');
  };

  const handleRemoveAlias = async (ip: string) => {
    await runSshCommand({ ...creds, command: `sed -i '/\\.ip=${ip}/d' /tmp/system.cfg 2>/dev/null; ifconfig eth0:1 ${ip} down 2>/dev/null; cfgmtd -w -p /etc/ 2>/dev/null || true` });
    setAliases(prev => prev.filter(a => a !== ip));
    addOutput(`\nRemoved alias ${ip}\n`);
  };

  const handleAutoAliases = async () => {
    const patterns = ['192.168.0.5', '192.168.1.5', '192.168.10.5', '192.168.110.5', '10.0.0.5'];
    addOutput('\n[Auto-adding aliases...]\n');
    for (const ip of patterns) {
      const subnet = ip.split('.').slice(0,3).join('.');
      const cmds = [
        `echo "netconf.2.alias.1.ip=${ip}" >> /tmp/system.cfg`,
        `echo "netconf.2.alias.1.netmask=255.255.255.0" >> /tmp/system.cfg`,
        `echo "netconf.2.alias.1.status=enabled" >> /tmp/system.cfg`,
        `cfgmtd -w -p /etc/ 2>/dev/null || true`,
        `ifconfig eth0:1 ${ip} netmask 255.255.255.0 up 2>/dev/null || true`,
        `route add -net ${subnet}.0 netmask 255.255.255.0 eth0 2>/dev/null || true`,
      ];
      for (const c of cmds) { try { await runSshCommand({ ...creds, command: c }); } catch(_) {} }
    }
    try {
      const o = await runSshCommand({ ...creds, command: 'cat /tmp/system.cfg 2>/dev/null | grep alias.ip' });
      const re = /ip=(\d+\.\d+\.\d+\.\d+)/g;
      const ips: string[] = []; let m;
      while ((m = re.exec(o.output||'')) !== null) ips.push(m[1]);
      setAliases([...new Set(ips)]);
    } catch(_) {}
    addOutput('Done. Scanning...\n');
    handleScan();
  };

  const handleQuickAction = async (action: string) => {
    if (!connected) return;
    const acts: Record<string,string> = {
      reboot: 'reboot',
      factory_reset: 'mca-cli-op set-default && reboot',
      wifi_on: 'ifconfig ath0 up 2>/dev/null || ifconfig wlan0 up 2>/dev/null || true',
      wifi_off: 'ifconfig ath0 down 2>/dev/null || ifconfig wlan0 down 2>/dev/null || true',
      backup_config: 'cat /tmp/system.cfg 2>/dev/null',
      show_clients: 'arp -a 2>/dev/null; ip neigh show 2>/dev/null',
    };
    addOutput(`\n[${action.replace(/_/g,' ')}]\n`);
    try {
      const res = await runSshCommand({ ...creds, command: acts[action] || 'echo unknown' });
      addOutput((res.output || res.error || 'Done') + '\n');
    } catch(_) { addOutput('Failed\n'); }
  };

  const handleCmd = async () => {
    if (!cmdInput.trim() || !connected) return;
    addOutput(`\n$ ${cmdInput}\n`);
    try {
      const res = await runSshCommand({ ...creds, command: cmdInput });
      addOutput((res.output || res.error || '') + '\n');
    } catch(_) {}
    setCmdInput('');
  };

  const ROUTERS = ['MikroTik','TP-Link','D-Link','Netgear','Tenda','Cisco','Huawei','ZTE'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 140px)' }}>
      <h1 style={{ marginBottom: 8 }}>Remote Access</h1>
      <p style={{ color: '#6b7280', fontSize: 12, marginBottom: 10, marginTop: -4 }}>SSH terminal and device management</p>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <select value={selId} onChange={e => { setSelId(e.target.value); setConnected(false); setScanned([]); setAliases([]); setOutput(''); }}
          style={{ minWidth: 200, fontSize: 12 }}>
          <option value="">Select device...</option>
          {devices.map(d => <option key={d.id} value={d.id}>{d.name} ({d.ip_address||'?'})</option>)}
        </select>
        <input value={creds.username} onChange={e => setCreds({...creds, username: e.target.value})}
          placeholder="User" style={{ width: 75, fontSize: 12 }} />
        <input type="password" value={creds.password} onChange={e => setCreds({...creds, password: e.target.value})}
          placeholder="Pass" style={{ width: 80, fontSize: 12 }} onKeyDown={e => { if (e.key === 'Enter') handleConnect(); }} />
        {!connected ? (
          <button className="btn-primary btn-sm" onClick={handleConnect} disabled={!creds.host||connecting}>
            {connecting ? '...' : 'Connect'}
          </button>
        ) : (
          <>
            <button className="btn-sm" onClick={handleDisconnect}>Disconnect</button>
            <button className="btn-sm" onClick={handleScan}>Scan Downstream</button>
          </>
        )}
        <span style={{ fontSize: 11, color: connected?'#16a34a':'#6b7280', fontWeight: 500, marginLeft: 8 }}>
          {connected ? 'Connected' : 'Not connected'}
        </span>
        <span style={{ fontSize: 11, color: '#6b7280', marginLeft: 'auto' }}>
          {device && `${device.brand} | ${device.ip_address||'?'}`}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 10, flex: 1, minHeight: 0 }}>
        {/* Side Panel */}
        <div style={{ width: 200, flexShrink: 0, overflowY: 'auto', overflowX: 'hidden' }}>
          <fieldset style={{ padding: 10, marginBottom: 8 }}>
            <legend>Quick Actions</legend>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <button className="btn-sm" onClick={() => handleQuickAction('reboot')} disabled={!connected}>Reboot</button>
              <button className="btn-sm btn-danger" onClick={() => handleQuickAction('factory_reset')} disabled={!connected}>Factory Reset</button>
              <button className="btn-sm" onClick={() => handleQuickAction('wifi_on')} disabled={!connected}>WiFi On</button>
              <button className="btn-sm" onClick={() => handleQuickAction('wifi_off')} disabled={!connected}>WiFi Off</button>
              <button className="btn-sm" onClick={() => handleQuickAction('backup_config')} disabled={!connected}>Backup Config</button>
              <button className="btn-sm" onClick={() => handleQuickAction('show_clients')} disabled={!connected}>Show Clients</button>
            </div>
          </fieldset>

          <fieldset style={{ padding: 10, marginBottom: 8 }}>
            <legend>Command</legend>
            <input value={cmdInput} onChange={e => setCmdInput(e.target.value)} style={{ width: '100%', fontFamily: 'monospace', fontSize: 11, marginBottom: 4, padding: '4px 6px' }}
              placeholder="/system identity print"
              onKeyDown={e => { if (e.key === 'Enter') handleCmd(); }} />
            <button className="btn-sm btn-primary" onClick={handleCmd} disabled={!connected||!cmdInput.trim()} style={{ width: '100%' }}>Run</button>
          </fieldset>

          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 10, marginBottom: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>IP Aliases</div>
            <button className="btn-sm" onClick={handleAutoAliases} disabled={!connected} style={{ width: '100%', marginBottom: 6, background: '#fef3c7', borderColor: '#f59e0b' }}>
              Auto-Add & Scan
            </button>
            <div style={{ display: 'flex', gap: 3, marginBottom: 6 }}>
              <input value={aliasIp} onChange={e => setAliasIp(e.target.value)} style={{ flex: 1, fontSize: 11, padding: '4px 6px' }} placeholder="192.168.0.5"
                onKeyDown={e => { if (e.key === 'Enter') handleAddAlias(); }} />
              <button className="btn-sm btn-primary" onClick={handleAddAlias} disabled={!connected||!aliasIp} style={{ flexShrink: 0 }}>Add</button>
            </div>
            {aliases.map((ip: string) => (
              <div key={ip} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, padding: '2px 0' }}>
                <span style={{ fontFamily: 'monospace' }}>{ip}</span>
                <button onClick={() => handleRemoveAlias(ip)} style={{ cursor: 'pointer', border: 'none', background: 'none', color: '#dc2626', fontWeight: 'bold', fontSize: 14 }}>x</button>
              </div>
            ))}
            {aliases.length > 1 && (
              <button className="btn-sm btn-danger" onClick={async () => { for (const ip of aliases) await handleRemoveAlias(ip); }} style={{ width: '100%', fontSize: 10, marginTop: 4 }}>Remove All</button>
            )}
          </div>
        </div>

        {/* Main area */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
          {scanned.length > 0 && (
            <div className="card" style={{ maxHeight: 200, overflow: 'auto', flexShrink: 0 }}>
              <div style={{ padding: '6px 10px', borderBottom: '1px solid #e5e7eb', background: '#f8fafc', fontSize: 11, fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
                Downstream Devices ({scanned.length})
                <button className="btn-sm" style={{ fontSize: 10 }} onClick={() => setScanned([])}>Hide</button>
              </div>
              <table>
                <thead><tr><th>IP</th><th>MAC</th><th>Vendor</th><th>Type</th><th></th></tr></thead>
                <tbody>
                  {scanned.map((d, i) => (
                    <tr key={i}>
                      <td style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 500 }}>{d.ip}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 10 }}>{d.mac}</td>
                      <td style={{ fontSize: 10 }}>{d.mac_vendor || '--'}</td>
                      <td style={{ fontSize: 10 }}>{ROUTERS.some(r => d.mac_vendor?.toLowerCase().includes(r.toLowerCase())) ? <span className="badge badge-info" style={{fontSize:9}}>Router</span> : ''}</td>
                      <td><button className="btn-sm btn-primary" onClick={() => handleTunnel(d.ip)} style={{fontSize:10,padding:'2px 6px'}}>Tunnel</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="card" style={{ flex: 1, overflow: 'auto' }}>
            <div style={{ padding: '4px 10px', borderBottom: '1px solid #e5e7eb', background: '#f8fafc', fontSize: 10, display: 'flex', justifyContent: 'space-between' }}>
              <span>Output</span>
              <button onClick={() => setOutput('')} style={{ fontSize: 10, padding: '1px 6px', border: '1px solid #d1d5db', borderRadius: 3, background: '#fff', cursor: 'pointer' }}>Clear</button>
            </div>
            <pre style={{ padding: 8, fontSize: 12, fontFamily: 'monospace', lineHeight: 1.4, whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0 }}>
              {output || 'Not connected. Enter credentials and click Connect.'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
