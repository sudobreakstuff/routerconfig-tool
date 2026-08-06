import { Routes, Route, Outlet } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import WinBoxLayout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Devices from './pages/Devices';
import SetupWizard from './pages/SetupWizard';
import BulkSetup from './pages/BulkSetup';
import Diagnostics from './pages/Diagnostics';
import RemoteAccess from './pages/RemoteAccess';
import Templates from './pages/Templates';
import Settings from './pages/Settings';

export default function App() {
  return (
    <>
      <Toaster position="bottom-right" />
      <Routes>
        <Route element={<WinBoxLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/setup" element={<SetupWizard />} />
          <Route path="/bulk" element={<BulkSetup />} />
          <Route path="/diagnostics" element={<Diagnostics />} />
          <Route path="/remote/:deviceId?" element={<RemoteAccess />} />
          <Route path="/remote" element={<RemoteAccess />} />
          <Route path="/templates" element={<Templates />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Dashboard />} />
        </Route>
      </Routes>
    </>
  );
}
