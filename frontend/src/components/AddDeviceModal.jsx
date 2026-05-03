import { useState } from "react";
import { X } from "lucide-react";
import { api } from "../api";
import { DeviceIcon, ICON_TYPES } from "./DeviceIcon";
import styles from "./AddDeviceModal.module.css";

export function AddDeviceModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    ip: "",
    label: "",
    icon: "unknown",
    web_port: "",
    web_protocol: "http",
    addMonitor: false,
    monitorType: "ping",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function set(key, val) { setForm((f) => ({ ...f, [key]: val })); }

  async function handleSave() {
    if (!form.ip.trim()) { setError("IP or hostname is required"); return; }
    setSaving(true);
    setError("");
    try {
      const device = await api.manualDevice.create({
        ip: form.ip.trim(),
        label: form.label.trim() || null,
        icon: form.icon,
        web_port: form.web_port ? Number(form.web_port) : null,
        web_protocol: form.web_protocol,
      });
      if (form.addMonitor) {
        try {
          await api.uptimeKuma.addMonitor(device.id);
        } catch (e) {
          // Monitor creation failed but device was created — warn user
          setError(`Device created but monitor failed: ${e.message}`);
          onCreated(device);
          return;
        }
      }
      onCreated(device);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>Add External Device</h2>
          <button className={styles.close} onClick={onClose}><X size={18} /></button>
        </div>

        <p className={styles.hint}>
          Add a standalone IP, hostname, or domain that isn't on your local network
          (e.g. a game server, cloud service, or remote host).
        </p>

        <div className={styles.field}>
          <label>IP / Hostname / Domain *</label>
          <input
            value={form.ip}
            onChange={(e) => set("ip", e.target.value)}
            placeholder="192.168.50.1  or  icarus.example.com"
            autoFocus
          />
        </div>

        <div className={styles.field}>
          <label>Label</label>
          <input
            value={form.label}
            onChange={(e) => set("label", e.target.value)}
            placeholder="Icarus Game Server"
          />
        </div>

        <div className={styles.field}>
          <label>Icon type</label>
          <div className={styles.iconGrid}>
            {ICON_TYPES.map((type) => (
              <button
                key={type}
                className={`${styles.iconBtn} ${form.icon === type ? styles.iconActive : ""}`}
                onClick={() => set("icon", type)}
                title={type}
              >
                <DeviceIcon type={type} size={16} />
                <span>{type}</span>
              </button>
            ))}
          </div>
        </div>

        <div className={styles.row}>
          <div className={styles.field}>
            <label>Protocol</label>
            <select value={form.web_protocol} onChange={(e) => set("web_protocol", e.target.value)}>
              <option value="http">http</option>
              <option value="https">https</option>
            </select>
          </div>
          <div className={styles.field}>
            <label>Web port (optional)</label>
            <input
              type="number"
              value={form.web_port}
              onChange={(e) => set("web_port", e.target.value)}
              placeholder="80"
            />
          </div>
        </div>

        <div className={styles.monitorRow}>
          <label className={styles.checkLabel}>
            <input
              type="checkbox"
              checked={form.addMonitor}
              onChange={(e) => set("addMonitor", e.target.checked)}
            />
            Add Uptime Kuma monitor after creation
          </label>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.footer}>
          <button className={styles.cancel} onClick={onClose}>Cancel</button>
          <button className={styles.save} onClick={handleSave} disabled={saving}>
            {saving ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
