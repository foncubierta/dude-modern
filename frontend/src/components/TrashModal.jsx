import { useState, useEffect } from "react";
import { X, RotateCcw } from "lucide-react";
import { api } from "../api";
import { DeviceIcon } from "./DeviceIcon";
import styles from "./TrashModal.module.css";

export function TrashModal({ onClose, onRestored }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const data = await api.devices.deleted();
      setDevices(data);
    } finally {
      setLoading(false);
    }
  }

  async function restore(id) {
    await api.devices.restore(id);
    setDevices((prev) => prev.filter((d) => d.id !== id));
    onRestored();
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>Deleted Devices</h2>
          <button className={styles.close} onClick={onClose}><X size={18} /></button>
        </div>

        <p className={styles.desc}>
          Deleted devices are hidden from the map and ignored by the scanner.
          Restore a device to bring it back.
        </p>

        {loading ? (
          <div className={styles.empty}>Loading…</div>
        ) : devices.length === 0 ? (
          <div className={styles.empty}>No deleted devices.</div>
        ) : (
          <ul className={styles.list}>
            {devices.map((d) => (
              <li key={d.id} className={styles.item}>
                <div className={styles.icon}>
                  <DeviceIcon type={d.icon || "unknown"} size={16} />
                </div>
                <div className={styles.info}>
                  <span className={styles.name}>{d.label || d.hostname || d.ip}</span>
                  <span className={styles.ip}>{d.ip}</span>
                  {d.network && <span className={styles.net}>{d.network}</span>}
                </div>
                <button className={styles.restoreBtn} onClick={() => restore(d.id)} title="Restore">
                  <RotateCcw size={14} />
                  Restore
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className={styles.footer}>
          <button className={styles.doneBtn} onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
