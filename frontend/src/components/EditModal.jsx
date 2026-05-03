import { useState } from "react";
import { X, ChevronDown, ChevronRight } from "lucide-react";
import { DeviceIcon, ICON_TYPES } from "./DeviceIcon";
import styles from "./EditModal.module.css";

export function EditModal({ device, devices, onSave, onClose }) {
  const [form, setForm] = useState({
    label: device.label || "",
    icon: device.icon || "unknown",
    web_port: device.web_port || "",
    web_protocol: device.web_protocol || "http",
    tags: device.tags || "",
    mikrotik_user: device.mikrotik_user || "",
    mikrotik_pass: device.mikrotik_pass || "",
    edgeswitch_user: device.edgeswitch_user || "",
    edgeswitch_pass: device.edgeswitch_pass || "",
    alias_of: device.alias_of ?? "",
  });
  const [showMikrotik, setShowMikrotik] = useState(
    !!(device.mikrotik_user || device.mikrotik_pass)
  );
  const [showEdgeSwitch, setShowEdgeSwitch] = useState(
    !!(device.edgeswitch_user || device.edgeswitch_pass)
  );

  function set(key, val) {
    setForm((f) => ({ ...f, [key]: val }));
  }

  async function handleSave() {
    await onSave(device.id, {
      label: form.label || null,
      icon: form.icon,
      web_port: form.web_port ? Number(form.web_port) : null,
      web_protocol: form.web_protocol,
      tags: form.tags || null,
      mikrotik_user: form.mikrotik_user || null,
      mikrotik_pass: form.mikrotik_pass || null,
      edgeswitch_user: form.edgeswitch_user || null,
      edgeswitch_pass: form.edgeswitch_pass || null,
      alias_of: form.alias_of ? Number(form.alias_of) : null,
    });
    onClose();
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>Edit Device</h2>
          <button className={styles.close} onClick={onClose}><X size={18} /></button>
        </div>

        <div className={styles.info}>
          <span className={styles.ip}>{device.ip}</span>
          {device.mac && <span className={styles.mac}>{device.mac}</span>}
        </div>

        <div className={styles.field}>
          <label>Label</label>
          <input
            value={form.label}
            onChange={(e) => set("label", e.target.value)}
            placeholder={device.hostname || device.ip}
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
                <DeviceIcon type={type} size={18} />
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
            <label>Web port</label>
            <input
              type="number"
              value={form.web_port}
              onChange={(e) => set("web_port", e.target.value)}
              placeholder="e.g. 80"
            />
          </div>
        </div>

        <div className={styles.field}>
          <label>Tags (comma separated)</label>
          <input
            value={form.tags}
            onChange={(e) => set("tags", e.target.value)}
            placeholder="rack, main, critical"
          />
        </div>

        {devices && devices.filter((d) => d.id !== device.id).length > 0 && (
          <div className={styles.field}>
            <label>Same physical device as</label>
            <select value={form.alias_of} onChange={(e) => set("alias_of", e.target.value)}>
              <option value="">— none —</option>
              {devices
                .filter((d) => d.id !== device.id && !d.alias_of)
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label || d.hostname || d.ip}
                  </option>
                ))}
            </select>
            {form.alias_of && (
              <span className={styles.aliasHint}>
                This device will be hidden from the map. Its subnet connections will be handled by the primary device.
              </span>
            )}
          </div>
        )}

        <div className={styles.section}>
          <button className={styles.sectionToggle} onClick={() => setShowMikrotik((v) => !v)}>
            {showMikrotik ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            MikroTik API
            {(form.mikrotik_user) && <span className={styles.badge}>configured</span>}
          </button>
          {showMikrotik && (
            <div className={styles.sectionBody}>
              <p className={styles.hint}>
                Enables live topology from ARP table and real-time traffic stats.
                Uses RouterOS REST API (port 80/443).
              </p>
              <div className={styles.row}>
                <div className={styles.field}>
                  <label>Username</label>
                  <input
                    value={form.mikrotik_user}
                    onChange={(e) => set("mikrotik_user", e.target.value)}
                    placeholder="admin"
                    autoComplete="off"
                  />
                </div>
                <div className={styles.field}>
                  <label>Password</label>
                  <input
                    type="password"
                    value={form.mikrotik_pass}
                    onChange={(e) => set("mikrotik_pass", e.target.value)}
                    placeholder="••••••"
                    autoComplete="new-password"
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className={styles.section}>
          <button className={styles.sectionToggle} onClick={() => setShowEdgeSwitch((v) => !v)}>
            {showEdgeSwitch ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            Ubiquiti EdgeSwitch API
            {form.edgeswitch_user && <span className={styles.badge}>configured</span>}
          </button>
          {showEdgeSwitch && (
            <div className={styles.sectionBody}>
              <p className={styles.hint}>
                Enables precise topology from MAC address table (FDB) and real-time
                per-port traffic. Uses EdgeSwitch REST API (HTTPS port 443, falls back to HTTP 80).
              </p>
              <div className={styles.row}>
                <div className={styles.field}>
                  <label>Username</label>
                  <input
                    value={form.edgeswitch_user}
                    onChange={(e) => set("edgeswitch_user", e.target.value)}
                    placeholder="ubnt"
                    autoComplete="off"
                  />
                </div>
                <div className={styles.field}>
                  <label>Password</label>
                  <input
                    type="password"
                    value={form.edgeswitch_pass}
                    onChange={(e) => set("edgeswitch_pass", e.target.value)}
                    placeholder="••••••"
                    autoComplete="new-password"
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className={styles.footer}>
          <button className={styles.cancel} onClick={onClose}>Cancel</button>
          <button className={styles.save} onClick={handleSave}>Save</button>
        </div>
      </div>
    </div>
  );
}
