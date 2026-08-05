# RouterConfig Pro

Multi-vendor router auto-configuration and remote management for ISP deployments.
Discover, configure, diagnose, and tunnel into Ubiquiti, MikroTik, TP-Link and generic
routers over SSH/HTTP. Built around the Jenny Internet CPE workflow.

## Stack

- **Backend**: Python / FastAPI / SQLAlchemy (async) / SQLite (aiosqlite) / paramiko
- **Frontend**: React 18 / TypeScript / Vite / Tailwind / xterm.js / d3
- **Desktop**: Electron wrapper (spawns the backend, bridges the API token via IPC)
- **Migrations**: Alembic (baseline included)

## Quick start (dev)

```bash
# Backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e .
uvicorn main:app --port 7933        # or: python main.py

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173, proxies /api -> :7933
```

Dev URL: `http://localhost:5173` · Backend: `http://127.0.0.1:7933` (bind to localhost only).

## Desktop app (production)

```bash
./scripts/build.sh                 # bundles backend (PyInstaller) + builds Electron app
```

- Bundles the Python backend into a self-contained binary (no system Python needed),
  then packages the Electron shell. Output: `frontend/dist/`.
- Linux: `RouterConfigPro-<ver>-x86_64.AppImage` + `RouterConfigPro-<ver>-amd64.deb`
- Windows: `RouterConfigPro-<ver>-win64-Setup.exe`
- CI: pushing a `v*` tag runs `.github/workflows/build.yml` on native Linux + Windows
  runners and attaches both sets of installers to the GitHub release.

In the packaged app the renderer runs from `file://`, so it talks to the backend at
`http://127.0.0.1:7933` directly. The instance API token is delivered through the
Electron preload/IPC bridge (`electron/preload.js`) — it never lives in browser storage.

## Data & security

- All data lives in `RC_DATA_DIR` (default `~/.routerconfig/`, or the Electron
  `userData` dir when packaged): `routerconfig.db`, `encryption.key`, `api_token.txt`.
- Device credentials, connection profiles, and ISP API keys are stored Fernet-encrypted
  (`backend/core/encryption.py`).
- **API auth**: every endpoint except `GET /api/settings/app` and `/api/health` requires
  `Authorization: Bearer <token>`. The token is generated on first run and returned by
  `settings/app` (safe because CORS only allows the local app origins).
- CORS is restricted to `http://localhost:5173`, `http://127.0.0.1:5173`, and `file://`/`null`.

## Architecture

```
backend/
  main.py               FastAPI app, CORS, auth wiring, /api/health
  api/                  routers: devices, configs, discovery, diagnostics,
                        templates, remote, actions, jobs, isp, settings
  core/                 engine, drivers (ubiquiti/tplink/mikrotik/generic),
                        discovery, diagnostics, connection pool, tunnel manager,
                        encryption, auth, mac vendor lookup, password gen
  services/             config/device/remote orchestration
  isp_adapters/         jenny_internet + custom upload adapters
  models/               SQLAlchemy models (all re-exported in models/__init__.py)
  alembic/              schema migrations
frontend/
  src/pages/            Dashboard, Devices, SetupWizard, BulkSetup, NetworkMap,
                        Diagnostics, RemoteAccess, Templates, Settings
  src/services/api.ts   axios client (token + base URL resolution)
  electron/             main.js + preload.js
```

## Key endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/devices` | list devices |
| POST | `/api/configs/setup` | run full config apply on one device |
| POST | `/api/configs/setup/bulk` | concurrent multi-device setup |
| POST | `/api/configs/deploy` | **setup + ISP upload in one action** |
| POST | `/api/configs/read-config` | read live config + scan downstream |
| POST | `/api/diagnostics/run` | health checks + baseline diff |
| POST | `/api/actions/execute` | run a named action on a device |
| POST | `/api/actions/execute/bulk` | run an action across many devices |
| POST | `/api/actions/tunnel-open` | open live SSH tunnel to downstream device |
| GET | `/api/actions/tunnels` | list open tunnels |
| DELETE | `/api/actions/tunnel/{id}` | close an open tunnel |
| POST | `/api/isp/upload-device` | push device info to ISP inventory |

## Actions

`reboot`, `factory_reset`, `backup_config`, `restore_config`, `firmware_upgrade`,
`get_connected_clients`, `wifi_on`, `wifi_off`, `set_wifi`, `set_admin_password`,
`set_dhcp`, `run_command`.

- `restore_config` accepts the structure returned by `backup_config`.
- `firmware_upgrade` (Ubiquiti) takes a local `.bin` path, uploads over SFTP, then triggers `mca-sysupgrade`.

## Vendor matrix

| Capability | Ubiquiti | MikroTik | TP-Link | Generic |
|---|---|---|---|---|
| SSH | yes | yes | yes | yes |
| Config read/backup | system.cfg + config.boot | /export | LUCI/forms | partial |
| Config apply | yes | yes | yes | via commands |
| Restore config | yes (files) | CLI replay | partial | no |
| Firmware upgrade | yes (SFTP) | no | no | no |
| Discovery (downstream) | ARP/mca-dump/DHCP | ARP/DHCP | partial | ARP |
| IP aliases | netconf aliases | IP addresses | no | no |

## Deploy CPE (Jenny workflow)

`POST /api/configs/deploy` runs the full deployment in one call:
1. read stored device credentials (or the supplied config payload),
2. apply the config via `ConfigService.setup_device`,
3. if a Jenny Internet ISP profile is configured, upload the device to the ISP inventory.

The **Deploy** button on the Devices page triggers this end-to-end flow.

## Migrations

```bash
cd backend
alembic upgrade head        # apply baseline + any later revisions
alembic revision --autogenerate -m "describe change"   # create a new revision
```

The app still runs `create_all` on startup for schema-safe first-run; use Alembic for
any schema change after the baseline so existing installs upgrade without data loss.

## Tests

The `backend/tests/` and `scripts/` directories are scaffolding for future work.
Planned: unit tests for the connection pool, tunnel manager, encryption, and the
drivers; a packaging script for one-command AppImage builds.
