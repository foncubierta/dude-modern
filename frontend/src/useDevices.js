import { useState, useEffect, useCallback } from "react";
import { api } from "./api";

export function useDevices() {
  const [devices, setDevices] = useState([]);
  const [stats, setStats] = useState({ total: 0, online: 0, offline: 0 });
  const [scanStatus, setScanStatus] = useState({ running: false, latest: null });
  const [topology, setTopology] = useState({ links: [] });
  const [traffic, setTraffic] = useState({ devices: {} });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [devs, st, scan, topo] = await Promise.all([
        api.devices.list(),
        api.stats(),
        api.scan.status(),
        api.topology(),
      ]);
      setDevices(devs);
      setStats(st);
      setScanStatus(scan);
      setTopology(topo);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshTraffic = useCallback(async () => {
    try {
      const t = await api.traffic();
      setTraffic(t);
    } catch (e) {
      // silently ignore if no MikroTik devices configured
    }
  }, []);

  useEffect(() => {
    refresh();
    const devicesTimer = setInterval(refresh, 10000);
    const trafficTimer = setInterval(refreshTraffic, 5000);
    refreshTraffic();
    return () => {
      clearInterval(devicesTimer);
      clearInterval(trafficTimer);
    };
  }, [refresh, refreshTraffic]);

  const triggerScan = useCallback(async () => {
    await api.scan.trigger();
    setScanStatus((s) => ({ ...s, running: true }));
    const poll = setInterval(async () => {
      const s = await api.scan.status();
      setScanStatus(s);
      if (!s.running) {
        clearInterval(poll);
        refresh();
      }
    }, 2000);
  }, [refresh]);

  const updateDevice = useCallback(async (id, body) => {
    const updated = await api.devices.update(id, body);
    setDevices((prev) => prev.map((d) => (d.id === id ? updated : d)));
    // Refresh topology in case alias_of or icon changed
    api.topology().then(setTopology).catch(() => {});
    return updated;
  }, []);

  const deleteDevice = useCallback(async (id) => {
    await api.devices.delete(id);
    setDevices((prev) => prev.filter((d) => d.id !== id));
  }, []);

  return {
    devices, stats, scanStatus, topology, traffic,
    loading, refresh, triggerScan, updateDevice, deleteDevice,
  };
}
