import { useState } from "react";
import { X, ChevronDown, ChevronRight, BellPlus, BellOff, Loader } from "lucide-react";
import { DeviceIcon, ICON_TYPES } from "./DeviceIcon";
import { api } from "../api";
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
    tplink_user: device.tplink_user || "",
    tplink_pass: device.tplink_pass || "",
    alias_of: device.alias_of ?? "",
  });
  const [showMikrotik, setShowMikrotik] = useState(
    !!(device.mikrotik_user || device.mikrotik_pass)
  );
  const [showEdgeSwitch, setShowEdgeSwitch] = useState(
    !!(device.edgeswitch_user || device.edgeswitch_pass)
  );
  const [showTplink, setShowTplink] = useState(
    !!(device.tplink_user || device.tplink_pass)
  );
  const [monitorLoading, setMonitorLoading] = useState(false);
  const [monitorId, setMonitorId] = useState(device.monitor_id ?? null);
  const [monitorError, setMonitorError] = useState("");

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
      tplink_user: form.tplink_user || null,
      tplink_pass: form.tplink_pass || null,
      alias_of: form.alias_of ? Number(form.alias_of) : null,
    });
    onClose();
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>

        {/* ── Sticky header ── */}
        <div className={styles.modalHeader}>
          <div className={styles.header}>
            <h2 className={styles.title}>Edit Device</h2>
            <button className={styles.close} onClick={onClose}><X size={18} /></button>
          </div>
          <div className={styles.info}>
            <span className={styles.ip}>{device.ip}</span>
            {device.mac && <span className={styles.mac}>{device.mac}</span>}
          </div>
        </div>

        {/* ── Scrollable body ── */}
        <div className={styles.body}>

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

        <div className={styles.section}>
          <button className={styles.sectionToggle} onClick={() => setShowTplink((v) => !v)}>
            {showTplink ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            TP-Link CPE API
            {form.tplink_user && <span className={styles.badge}>configured</span>}
          </button>
          {showTplink && (
            <div className={styles.sectionBody}>
              <p className={styles.hint}>
                Enables topology from wireless station list via SSH (port 22).
                Uses the same credentials as the web interface.
              </p>
              <div className={styles.row}>
                <div className={styles.field}>
                  <label>Username</label>
                  <input
                    value={form.tplink_user}
                    onChange={(e) => set("tplink_user", e.target.value)}
                    placeholder="admin"
                    autoComplete="off"
                  />
                </div>
                <div className={styles.field}>
                  <label>Password</label>
                  <input
                    type="password"
                    value={form.tplink_pass}
                    onChange={(e) => set("tplink_pass", e.target.value)}
                    placeholder="••••••"
                    autoComplete="new-password"
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className={styles.section}>
          <button className={styles.sectionToggle} onClick={() => {}}>
            <BellPlus size={13} />
            Uptime Kuma
            {monitorId && <span className={styles.badge}>monitoring</span>}
            {device.alert_status === "down" && <span className={styles.badgeDown}>DOWN</span>}
          </button>
          <div className={styles.sectionBody}>
            <p className={styles.hint}>
              Add or remove this device from Uptime Kuma monitoring.
              Configure the Uptime Kuma connection in Settings first.
            </p>
            {monitorError && <p className={styles.monitorError}>{monitorError}</p>}
            {monitorId ? (
              <button
                className={styles.monitorRemoveBtn}
                disabled={monitorLoading}
                onClick={async () => {
                  setMonitorLoading(true);
                  setMonitorError("");
                  try {
                    await api.uptimeKuma.removeMonitor(device.id);
                    setMonitorId(null);
                  } catch (e) {
                    setMonitorError(e.message);
                  } finally {
                    setMonitorLoading(false);
                  }
                }}
              >
                {monitorLoading ? <Loader size={13} className={styles.spin} /> : <BellOff size={13} />}
                Remove monitor
              </button>
            ) : (
              <button
                className={styles.monitorAddBtn}
                disabled={monitorLoading}
                onClick={async () => {
                  setMonitorLoading(true);
                  setMonitorError("");
                  try {
                    const r = await api.uptimeKuma.addMonitor(device.id);
                    setMonitorId(r.monitor_id ?? true);
                  } catch (e) {
                    setMonitorError(e.message);
                  } finally {
                    setMonitorLoading(false);
                  }
                }}
              >
                {monitorLoading ? <Loader size={13} className={styles.spin} /> : <BellPlus size={13} />}
                Add monitor
              </button>
            )}
          </div>
        </div>

        </div>{/* end .body */}

        {/* ── Sticky footer ── */}
        <div className={styles.modalFooter}>
          <div className={styles.footer}>
            <button className={styles.cancel} onClick={onClose}>Cancel</button>
            <button className={styles.save} onClick={handleSave}>Save</button>
          </div>
        </div>

      </div>
    </div>
  );
}
