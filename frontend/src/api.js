const BASE = "/api";

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const api = {
  devices: {
    list: () => req("/devices"),
    update: (id, body) => req(`/devices/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (id) => req(`/devices/${id}`, { method: "DELETE" }),
  },
  scan: {
    trigger: () => req("/scan", { method: "POST" }),
    status: () => req("/scan/status"),
    logs: () => req("/scan/logs"),
  },
  settings: {
    get: () => req("/settings"),
    set: (key, value) => req(`/settings/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),
  },
  networks: () => req("/networks"),
  stats: () => req("/stats"),
  topology: () => req("/topology"),
  traffic: () => req("/traffic"),
};
