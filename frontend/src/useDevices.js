import { useState, useEffect, useCallback } from "react";
import { api } from "./api";

export function useDevices() {
  const [devices, setDevices] = useState([]);
  const [stats, setStats] = useState({ total: 0, online: 0, offline: 0 });
  const [scanStatus, setScanStatus] = useState({ running: false, latest: null });
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [devs, st, scan] = await Promise.all([
        api.devices.list(),
        api.stats(),
        api.scan.status(),
      ]);
      setDevices(devs);
      setStats(st);
      setScanStatus(scan);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 10000);
    return () => clearInterval(id);
  }, [refresh]);

  const triggerScan = useCallback(async () => {
    await api.scan.trigger();
    setScanStatus((s) => ({ ...s, running: true }));
    // Poll until done
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
    return updated;
  }, []);

  const deleteDevice = useCallback(async (id) => {
    await api.devices.delete(id);
    setDevices((prev) => prev.filter((d) => d.id !== id));
  }, []);

  return { devices, stats, scanStatus, loading, refresh, triggerScan, updateDevice, deleteDevice };
}
