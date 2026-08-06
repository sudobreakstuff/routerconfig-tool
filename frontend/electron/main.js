const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

app.disableHardwareAcceleration();

let mainWindow;
let pythonProcess;

function startPythonBackend() {
  // Packaged: spawn the bundled backend binary (no system Python needed).
  // Dev: fall back to `python3 backend/main.py`.
  const isPackaged = app.isPackaged;
  const exeName = process.platform === 'win32' ? 'routerconfig-backend.exe' : 'routerconfig-backend';
  const backendPath = isPackaged
    ? path.join(process.resourcesPath, 'backend', exeName)
    : path.join(__dirname, '..', '..', 'backend', 'main.py');

  let args;
  if (isPackaged) {
    args = [];
  } else {
    const pythonPath = process.platform === 'win32' ? 'python' : 'python3';
    pythonProcess = spawn(pythonPath, [backendPath], {
      env: { ...process.env, RC_DATA_DIR: app.getPath('userData') },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return;
  }

  pythonProcess = spawn(backendPath, args, {
    env: { ...process.env, RC_DATA_DIR: app.getPath('userData') },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[backend:err] ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`[backend] exited with code ${code}`);
  });
}

function stopPythonBackend() {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    title: 'RouterConfig Pro',
    backgroundColor: '#0c0c0d',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  const isDev = process.argv.includes('--dev');

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'renderer', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function readApiToken() {
  // Same RC_DATA_DIR the backend uses so the token file matches.
  const dataDir = app.getPath('userData');
  const tokenPath = path.join(dataDir, 'api_token.txt');
  try {
    if (fs.existsSync(tokenPath)) {
      const token = fs.readFileSync(tokenPath, 'utf8').trim();
      if (token) return token;
    }
  } catch (_) {}
  return null;
}

function registerIpcHandlers() {
  ipcMain.handle('router-config:get-token', () => readApiToken() || '');
  ipcMain.handle('router-config:get-api-base', () => 'http://127.0.0.1:7933');
}

app.whenReady().then(() => {
  registerIpcHandlers();
  startPythonBackend();
  setTimeout(createWindow, 1500);
});

app.on('window-all-closed', () => {
  stopPythonBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  stopPythonBackend();
});
