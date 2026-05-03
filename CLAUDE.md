# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**Dude Modern** is a self-hosted network map dashboard. It scans local subnets with nmap, builds an interactive ReactFlow topology map, shows live traffic stats, and integrates with Uptime Kuma for alerting. Think "The Dude / PRTG but self-hosted and modern".

## Running locally (development)

```bash
# Backend (requires nmap installed on host)
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8099 --reload

# Frontend
cd frontend
npm install
npm run dev        # Vite dev server on :5173, proxies /api/ to :8099
npm run build      # Production build → dist/
```

## Deployment

Deployed via **Portainer** as a Docker Compose stack. After pushing to GitHub, redeploy each service from Portainer to pick up changes.

- **Backend**: `network_mode: host` — mandatory so nmap can reach the LAN and the backend listens on the host's port 8099.
- **Frontend**: nginx container, proxies `/api/` → `http://host.docker.internal:8099`. The `nginx.conf` is the key glue between containers.
- **Database**: SQLite at `/app/data/dude.db` — the `data/` directory must be a named Docker volume so it survives redeployment.

## Architecture

### Backend (`backend/`)

| File | Role |
|------|------|
| `main.py` | All FastAPI routes + scheduler + topology logic |
| `models.py` | SQLModel ORM — `Device`, `ScanLog`, `Settings` |
| `database.py` | Engine, `create_db()`, manual ALTER TABLE migrations |
| `scanner.py` | nmap wrapper + async web-port detection + DB upsert logic |
| `mikrotik.py` | RouterOS REST API — ARP table, DHCP leases, traffic |
| `edgeswitch.py` | EdgeSwitch REST API — FDB (MAC table), traffic |
| `tplink_cpe.py` | SSH via paramiko → `/proc/net/arp` for wireless clients |
| `uptime_kuma.py` | Socket.IO wrapper around `uptime-kuma-api` for monitor CRUD |

**Topology pipeline** (`GET /api/topology`):
1. Base layer: subnet-based — `.1` of each CIDR is the gateway, all others hang from it.
2. MikroTik refinement: ARP table overrides subnet topology (same-subnet devices only).
3. EdgeSwitch refinement: FDB (MAC address table) overrides — most accurate (same-subnet only).
4. TP-Link CPE: SSH → wireless station list; no subnet restriction, matches by MAC then IP.

**Critical PATCH behaviour**: `DeviceUpdate` uses `body.model_dump(exclude_unset=True)` — NOT `exclude_none`. This allows setting fields to `null` explicitly (e.g. clearing `alias_of`).

**Database migrations**: new columns are added in `database.py → _MIGRATIONS` as raw `ALTER TABLE` statements wrapped in try/except. SQLModel `create_all` only creates new tables; it never alters existing ones.

**Alias system**: `Device.alias_of` points to the primary device ID. Aliased devices are hidden from the map and topology; their subnet connections are owned by the primary. The topology endpoint resolves aliases transitively.

**Uptime Kuma quirk**: `uptime-kuma-api==1.2.1` does not support the `conditions` field required by newer UK versions (NOT NULL constraint). `uptime_kuma.py` monkey-patches `api._build_monitor_data` to inject `conditions: []` before the socket emit. Also fetches all existing notifications and passes them as enabled in `notificationIDList`.

### Frontend (`frontend/src/`)

| File/Dir | Role |
|----------|------|
| `App.jsx` | Root — state for all modals, view switching |
| `useDevices.js` | Central data hook — polling, updateDevice, deleteDevice |
| `api.js` | All fetch calls to `/api/` |
| `components/NetworkMap.jsx` | ReactFlow canvas + type filter bar |
| `components/DeviceNode.jsx` | ReactFlow custom node — online/offline/DOWN/NEW states |
| `components/GridView.jsx` | Table/card view of all devices |
| `components/EditModal.jsx` | Edit device — label, icon, credentials, alias, UK monitor |
| `components/AddDeviceModal.jsx` | Create manual (external) device |
| `components/SettingsModal.jsx` | Uptime Kuma connection config + webhook URL |
| `components/TrashModal.jsx` | Soft-deleted device restore |
| `components/NetworksModal.jsx` | Manage scanned subnets |

**Modal scroll pattern**: All modals use `position: sticky` on `.modalHeader` (top:0) and `.modalFooter` (bottom:0) with `overflow-y: auto` on the `.modal` container itself. Do NOT use `flex:1 + overflow-y` on a child — it fails without `min-height:0` in many browsers.

**New device highlight**: `first_seen` within 10 minutes → orange `isNew` glow + NEW badge. `alert_status === "down"` → red pulse `isDown` + DOWN badge.

**Device icon types** (defined in `DeviceIcon.jsx`): `router`, `ap`, `switch`, `server`, `pc`, `phone`, `camera`, `printer`, `tv`, `unknown`.

## Key API endpoints

```
GET    /api/devices              All non-deleted devices
PATCH  /api/devices/:id          Update device fields (exclude_unset)
DELETE /api/devices/:id          Soft delete
POST   /api/devices/manual       Create external IP/domain device
POST   /api/devices/:id/monitor  Add Uptime Kuma monitor
DELETE /api/devices/:id/monitor  Remove UK monitor
GET    /api/topology             Links + aliased IDs (calls MikroTik/ES/CPE live)
GET    /api/traffic              Live Mbps per device
POST   /api/scan                 Trigger manual nmap scan (background)
GET    /api/scan/status          Whether scan is running + latest log
GET/PUT /api/uptime-kuma/settings UK credentials
POST   /api/uptime-kuma/test     Test UK connection
POST   /api/webhook              Receive UK down/up webhooks → sets alert_status
```
