import axios from 'axios';

// In the packaged Electron app the renderer runs from file:// and must talk to
// the local backend over http://127.0.0.1:7933 with the instance bearer token,
// both supplied through the preload bridge. In dev (Vite) we use the /api proxy
// and bootstrap the token from the (public) settings endpoint.
declare global {
  interface Window {
    routerConfig?: {
      getApiToken: () => Promise<string>;
      getApiBase: () => Promise<string>;
    };
  }
}

let authToken: string | null = null;

async function resolveToken(): Promise<string> {
  if (authToken !== null) return authToken;
  if (window.routerConfig) {
    authToken = await window.routerConfig.getApiToken();
    return authToken || '';
  }
  let token = '';
  try {
    const { data } = await axios.get('/api/settings/app');
    token = data.token || '';
  } catch (_) {
    token = '';
  }
  authToken = token;
  return token;
}

async function resolveBaseURL(): Promise<string> {
  if (window.routerConfig) {
    return `${await window.routerConfig.getApiBase()}/api`;
  }
  return '/api';
}

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
});

api.interceptors.request.use(async (config) => {
  config.baseURL = await resolveBaseURL();
  const token = await resolveToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;

export async function fetchDevices() {
  const { data } = await api.get('/devices');
  return data;
}

export async function fetchDevice(id: string, secrets = false) {
  const { data } = await api.get(`/devices/${id}`, { params: { include_secrets: secrets } });
  return data;
}

export async function createDevice(deviceData: Record<string, unknown>) {
  const { data } = await api.post('/devices', deviceData);
  return data;
}

export async function updateDevice(id: string, deviceData: Record<string, unknown>) {
  const { data } = await api.put(`/devices/${id}`, deviceData);
  return data;
}

export async function deleteDevice(id: string) {
  const { data } = await api.delete(`/devices/${id}`);
  return data;
}

export async function scanNetwork(subnet = '192.168.0.0/24') {
  const { data } = await api.get('/discovery/scan', { params: { subnet } });
  return data;
}

export async function pingHost(ip: string) {
  const { data } = await api.get('/discovery/ping', { params: { ip } });
  return data;
}

export async function setupDevice(setupData: Record<string, unknown>) {
  const { data } = await api.post('/configs/setup', setupData);
  return data;
}

export async function deployDevice(deployData: Record<string, unknown>) {
  const { data } = await api.post('/configs/deploy', deployData);
  return data;
}

export async function setupBulk(bulkData: Record<string, unknown>) {
  const { data } = await api.post('/configs/setup/bulk', bulkData);
  return data;
}

export async function testConnection(connectionData: Record<string, unknown>) {
  const { data } = await api.post('/configs/test-connection', connectionData);
  return data;
}

export async function readDeviceConfig(connectionData: Record<string, unknown>) {
  const { data } = await api.post('/configs/read-config', connectionData);
  return data;
}

export async function runAction(actionData: Record<string, unknown>) {
  const { data } = await api.post('/actions/execute', actionData);
  return data;
}

export async function runBulkAction(bulkActionData: Record<string, unknown>) {
  const { data } = await api.post('/actions/execute/bulk', bulkActionData);
  return data;
}

export async function getAvailableActions() {
  const { data } = await api.get('/actions/available');
  return data;
}

export async function connectToDevice(deviceId: string, connectionData?: Record<string, unknown>) {
  const { data } = await api.post(`/remote/connect/${deviceId}`, connectionData || {});
  return data;
}

export async function takeBaseline(deviceId: string, payload?: Record<string, unknown>) {
  const { data } = await api.post(`/remote/baseline/${deviceId}`, payload || {});
  return data;
}

export async function getBaselines(deviceId: string) {
  const { data } = await api.get(`/remote/baselines/${deviceId}`);
  return data;
}

export async function getConnectionInfo(deviceId: string) {
  const { data } = await api.get(`/remote/connection/${deviceId}`);
  return data;
}

export async function saveConnection(deviceId: string, profileData: Record<string, unknown>) {
  const { data } = await api.post(`/remote/connection/${deviceId}`, profileData);
  return data;
}

export async function runDiagnostics(diagData: Record<string, unknown>) {
  const { data } = await api.post('/diagnostics/run', diagData);
  return data;
}

export async function getDiagnosticReports(deviceId: string) {
  const { data } = await api.get(`/diagnostics/reports/${deviceId}`);
  return data;
}

export async function fetchTemplates(vendor?: string) {
  const { data } = await api.get('/templates', { params: vendor ? { vendor } : {} });
  return data;
}

export async function fetchTemplate(id: string) {
  const { data } = await api.get(`/templates/${id}`);
  return data;
}

export async function createTemplate(templateData: Record<string, unknown>) {
  const { data } = await api.post('/templates', templateData);
  return data;
}

export async function updateTemplate(id: string, templateData: Record<string, unknown>) {
  const { data } = await api.put(`/templates/${id}`, templateData);
  return data;
}

export async function deleteTemplate(id: string) {
  const { data } = await api.delete(`/templates/${id}`);
  return data;
}

export async function previewTemplate(previewData: Record<string, unknown>) {
  const { data } = await api.post('/templates/preview', previewData);
  return data;
}

export async function fetchJobs() {
  const { data } = await api.get('/jobs');
  return data;
}

export async function createJob(jobData: Record<string, unknown>) {
  const { data } = await api.post('/jobs', jobData);
  return data;
}

export async function fetchISPProfiles() {
  const { data } = await api.get('/isp/profiles');
  return data;
}

export async function createISPProfile(profileData: Record<string, unknown>) {
  const { data } = await api.post('/isp/profiles', profileData);
  return data;
}

export async function uploadDeviceToISP(uploadData: Record<string, unknown>) {
  const { data } = await api.post('/isp/upload-device', uploadData);
  return data;
}

export async function getAppSettings() {
  const { data } = await api.get('/settings/app');
  return data;
}

export async function listTunnels() {
  const { data } = await api.get('/actions/tunnels');
  return data;
}

export async function closeTunnel(tunnelId: number) {
  const { data } = await api.delete(`/actions/tunnel/${tunnelId}`);
  return data;
}

export async function manageAlias(aliasData: Record<string, unknown>) {
  const { data } = await api.post('/remote/manage-alias', aliasData);
  return data;
}

export async function bandwidthTest(testData: Record<string, unknown>) {
  const { data } = await api.post('/diagnostics/bandwidth-test', testData);
  return data;
}

// Persistent SSH connection pool commands
export async function persistentConnect(connData: Record<string, unknown>) {
  const { data } = await api.post('/actions/connect', connData);
  return data;
}

export async function persistentDisconnect(connData: Record<string, unknown>) {
  const { data } = await api.post('/actions/disconnect', connData);
  return data;
}

export async function runSshCommand(cmdData: Record<string, unknown>) {
  const { data } = await api.post('/actions/cmd', cmdData);
  return data;
}

export async function scanFromDevice(scanData: Record<string, unknown>) {
  const { data } = await api.post('/actions/scan', scanData);
  return data;
}

export async function checkTunnel(tunnelData: Record<string, unknown>) {
  const { data } = await api.post('/actions/tunnel-check', tunnelData);
  return data;
}

export async function openTunnelUrl(tunnelData: Record<string, unknown>) {
  const { data } = await api.post('/actions/tunnel-open', tunnelData);
  return data;
}

export async function fetchActiveTunnels() {
  const { data } = await api.get('/actions/tunnels');
  return data;
}
