import { create } from 'zustand';

interface Device {
  id: string;
  site_id: string | null;
  name: string;
  brand: string;
  model: string | null;
  firmware_version: string | null;
  mac_address: string | null;
  ip_address: string | null;
  dhcp_mode: string;
  bridge_mode: boolean;
  wifi_enabled: boolean;
  is_online: boolean;
  last_seen: string | null;
  created_at: string | null;
  tags: Record<string, unknown> | null;
}

interface AppState {
  devices: Device[];
  selectedDeviceId: string | null;
  sidebarCollapsed: boolean;
  terminalOutput: string;
  isLoading: boolean;
  setDevices: (devices: Device[]) => void;
  setSelectedDevice: (id: string | null) => void;
  toggleSidebar: () => void;
  appendTerminal: (text: string) => void;
  clearTerminal: () => void;
  setLoading: (loading: boolean) => void;
}

export const useStore = create<AppState>((set) => ({
  devices: [],
  selectedDeviceId: null,
  sidebarCollapsed: false,
  terminalOutput: '',
  isLoading: false,
  setDevices: (devices) => set({ devices }),
  setSelectedDevice: (id) => set({ selectedDeviceId: id }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  appendTerminal: (text) => set((s) => ({ terminalOutput: s.terminalOutput + text })),
  clearTerminal: () => set({ terminalOutput: '' }),
  setLoading: (loading) => set({ isLoading: loading }),
}));
