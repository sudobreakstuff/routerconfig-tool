import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { fetchDevices } from '../services/api';

function Icon({ d }: { d: string }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>;
}

const navItems = [
  { to: '/', label: 'Dashboard', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { to: '/devices', label: 'Devices', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01' },
  { to: '/setup', label: 'Setup Wizard', icon: 'M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z' },
  { to: '/bulk', label: 'Bulk Setup', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
  { to: '/diagnostics', label: 'Diagnostics', icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
  { to: '/remote', label: 'Remote Access', icon: 'M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z' },
  { to: '/templates', label: 'Templates', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
  { to: '/settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [deviceCount, setDeviceCount] = useState(0);
  const [onlineCount, setOnlineCount] = useState(0);
  const [openMenu, setOpenMenu] = useState('');

  useEffect(() => {
    fetchDevices().then(d => {
      setDeviceCount(d.length);
      setOnlineCount(d.filter((x: any) => x.is_online).length);
    }).catch(() => {});
  }, [location]);

  useEffect(() => {
    const close = () => setOpenMenu('');
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, []);

  const menuButtons = [
    {
      label: 'File', menu: 'file',
      items: [
        { label: 'New Connection Wizard', action: () => navigate('/setup') },
        { label: 'Bulk Import Devices', action: () => navigate('/bulk') },
        { label: 'Save All Configs', action: () => {} },
        { divider: true },
        { label: 'Export Device List (CSV)', action: () => {} },
        { label: 'Exit Application', action: () => window.close() },
      ],
    },
    {
      label: 'Tools', menu: 'tools',
      items: [
        { label: 'Network Scanner', action: () => navigate('/setup') },
        { label: 'Diagnostics Check', action: () => navigate('/diagnostics') },
        { divider: true },
        { label: 'Template Editor', action: () => navigate('/templates') },
        { label: 'ISP Profile Manager', action: () => navigate('/settings') },
      ],
    },
    {
      label: 'Help', menu: 'help',
      items: [
        { label: 'Documentation', action: () => window.open('https://github.com/sudobreakstuff/routerconfig-tool', '_blank') },
        { label: 'Quick Start Guide', action: () => window.open('https://github.com/sudobreakstuff/routerconfig-tool#readme', '_blank') },
        { divider: true },
        { label: 'About RouterConfig Pro v1.0', action: () => {} },
      ],
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Menu Bar */}
      <div style={{ background: '#111827', padding: '0 12px', display: 'flex', alignItems: 'center', height: 36, flexShrink: 0, gap: 4 }}>
        <span style={{ color: '#fff', fontWeight: 700, fontSize: 14, marginRight: 20, letterSpacing: '-0.01em' }}>RouterConfig Pro</span>
        {menuButtons.map(mb => (
          <div key={mb.menu} style={{ position: 'relative' }}>
            <button
              className="menu-bar-btn"
              onClick={e => { e.stopPropagation(); setOpenMenu(openMenu === mb.menu ? '' : mb.menu); }}
              style={{ color: openMenu === mb.menu ? '#fff' : '#9ca3af', background: openMenu === mb.menu ? 'rgba(255,255,255,0.1)' : undefined }}
            >
              {mb.label}
            </button>
            {openMenu === mb.menu && (
              <div className="dropdown-menu" onClick={e => e.stopPropagation()}>
                {mb.items.map((item, i) =>
                  item.divider ? <hr key={i} /> : (
                    <button key={i} onClick={() => { if (item.action) item.action(); setOpenMenu(''); }}>
                      {item.label}
                    </button>
                  )
                )}
              </div>
            )}
          </div>
        ))}
        <span style={{ marginLeft: 'auto', color: '#6b7280', fontSize: 11 }}>github.com/sudobreakstuff</span>
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <nav style={{ width: 220, flexShrink: 0, background: '#1f2937', paddingTop: 6, overflow: 'auto' }}>
          {navItems.map(item => {
            const active = location.pathname === item.to || (item.to !== '/' && location.pathname.startsWith(item.to));
            return (
              <div key={item.to} className={`nav-item${active ? ' active' : ''}`} onClick={() => navigate(item.to)}>
                <Icon d={item.icon} />
                {item.label}
              </div>
            );
          })}
        </nav>
        <main style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          <Outlet />
        </main>
      </div>

      <div className="status-bar">
        <span>Devices: {deviceCount} configured, {onlineCount} online</span>
        <span>Backend: 127.0.0.1:7933</span>
        <span style={{ marginLeft: 'auto' }}>v1.0.0</span>
      </div>
    </div>
  );
}
