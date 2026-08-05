const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('routerConfig', {
  // Returns the instance API token from the main process (which owns it).
  getApiToken: () => ipcRenderer.invoke('router-config:get-token'),
  // Returns the base URL of the local backend.
  getApiBase: () => ipcRenderer.invoke('router-config:get-api-base'),
});
