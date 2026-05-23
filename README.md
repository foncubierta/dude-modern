# Dude Modern

A self-hosted network monitoring dashboard. Scans your local subnets with nmap, builds an interactive topology map, shows live traffic stats, and integrates with Uptime Kuma for alerting.

Think **The Dude / PRTG — but self-hosted, modern, and running in Docker**.

---

## Features

- **Auto-discovery** — nmap scans your subnets every 5 minutes, detecting new devices automatically
- **Interactive topology map** — ReactFlow canvas showing how devices connect, with drag-and-drop layout
- **Device enrichment** — hostnames resolved via mDNS, SSDP, NetBIOS and MikroTik DHCP leases; MAC addresses pulled from MikroTik ARP tables for all subnets
- **Live traffic** — real-time Mbps per device via MikroTik RouterOS or Ubiquiti EdgeSwitch APIs
- **Uptime Kuma integration** — create/remove monitors directly from the dashboard; webhook receives down/up alerts and highlights devices on the map
- **Offline tracking** — shows how long each device has been offline; auto-hides devices gone 30+ days, deletes after 90 days
- **Grid view** — searchable, filterable card list with subnet, vendor, MAC, and status
- **Manual devices** — add external IPs, hostnames or domains that don't live on your LAN
- **Device icons** — router, AP, switch, server, PC, phone, camera, printer, TV, IoT, speaker, solar, HVAC, plug, VoIP and more

---

## Screenshots

> Topology map with live device status, traffic, and online/offline indicators.

---

## Quick Start with Docker

### Requirements

- Docker + Docker Compose
- `nmap` is bundled in the backend image — no host install needed
- The backend container uses `network_mode: host` so nmap can reach your LAN

### 1. Clone the repo

```bash
git clone https://github.com/foncubierta/dude-modern.git
cd dude-modern
```

### 2. Start the stack

```bash
docker compose up -d
```

The frontend will be available at **http://localhost:3000**.

The first scan starts automatically within a few seconds. Devices will appear on the map as nmap discovers them.

### 3. (Optional) Configure your subnets

By default Dude Modern detects your host's local networks. You can add or remove subnets from the **Networks** button in the top bar.

---

## Docker Compose reference

```yaml
services:
  backend:
    build: ./backend
    restart: unless-stopped
    network_mode: host          # required — nmap needs raw LAN access
    volumes:
      - dude_data:/app/data     # SQLite database persisted here
    environment:
      - DATABASE_URL=sqlite:////app/data/dude.db
      - PORT=8099

  frontend:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "3000:80"               # change left side to use a different port
    extra_hosts:
      - "host.docker.internal:host-gateway"

volumes:
  dude_data:
```

> **Note**: `network_mode: host` is required on Linux. On Docker Desktop (Mac/Windows) it is not supported — use Linux or a Linux VM for production.

---

## Integrations

### MikroTik RouterOS

Edit any MikroTik device on the map and enter its API credentials. This enables:

- Accurate topology (ARP table replaces subnet guesses)
- MAC address enrichment for all subnets the router manages
- Hostname enrichment from DHCP leases
- Live traffic (Mbps per device)

The RouterOS REST API must be enabled on the router (`/rest` endpoint, port 80).

### Ubiquiti EdgeSwitch

Enter EdgeSwitch credentials on the device to get:

- Accurate topology via the MAC address table (FDB)
- Live port traffic

### TP-Link CPE

Enter SSH credentials to pull the wireless station list and map Wi-Fi clients to their CPE.

### Uptime Kuma

Go to **Settings** (⚙ top-right) and enter your Uptime Kuma URL and credentials. Then open any device and click **Add monitor** to create a ping or HTTP monitor. Down/up alerts are received via webhook and shown as a pulsing red badge on the map.

Webhook URL to configure in Uptime Kuma:
```
http://<your-host>:8099/api/webhook
```

---

## Development setup

```bash
# Backend — requires Python 3.11+ and nmap installed on the host
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8099 --reload

# Frontend
cd frontend
npm install
npm run dev      # Vite dev server on :5173, proxies /api/ → :8099
```

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python · FastAPI · SQLModel · APScheduler |
| Scanner | nmap · python-nmap · zeroconf (mDNS) · asyncio sockets |
| Database | SQLite (single file, zero config) |
| Frontend | React · Vite · ReactFlow · Lucide icons |
| Deployment | Docker Compose · nginx (frontend proxy) |

---

## Data persistence

The SQLite database lives at `/app/data/dude.db` inside the backend container, mapped to the named volume `dude_data`. Device positions, labels, credentials and history survive container restarts and redeployments as long as the volume is kept.

---

## License

MIT
