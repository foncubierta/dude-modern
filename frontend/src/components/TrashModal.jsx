import { useState, useEffect } from "react";
import { X, RotateCcw, Trash2 } from "lucide-react";
import { api } from "../api";
import { DeviceIcon } from "./DeviceIcon";
import styles from "./TrashModal.module.css";

export function TrashModal({ onClose, onRestored }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirmId, setConfirmId] = useState(null); // id pending hard-delete confirmation

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

  async function hardDelete(id) {
    await api.devices.hardDelete(id);
    setDevices((prev) => prev.filter((d) => d.id !== id));
    setConfirmId(null);
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>

        {/* ── Sticky header ── */}
        <div className={styles.modalHeader}>
          <div className={styles.header}>
            <h2 className={styles.title}>Deleted Devices</h2>
            <button className={styles.close} onClick={onClose}><X size={18} /></button>
          </div>
          <p className={styles.desc}>
            Deleted devices are hidden from the map. Restore to bring them back,
            or delete permanently to remove from the database.
          </p>
        </div>

        {/* ── Scrollable body ── */}
        <div className={styles.body}>
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

                  {confirmId === d.id ? (
                    <div className={styles.confirmRow}>
                      <span className={styles.confirmText}>Delete forever?</span>
                      <button className={styles.confirmYes} onClick={() => hardDelete(d.id)}>Yes</button>
                      <button className={styles.confirmNo} onClick={() => setConfirmId(null)}>No</button>
                    </div>
                  ) : (
                    <div className={styles.btnRow}>
                      <button className={styles.restoreBtn} onClick={() => restore(d.id)} title="Restore">
                        <RotateCcw size={13} /> Restore
                      </button>
                      <button className={styles.deleteBtn} onClick={() => setConfirmId(d.id)} title="Delete permanently">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* ── Sticky footer ── */}
        <div className={styles.modalFooter}>
          <button className={styles.doneBtn} onClick={onClose}>Close</button>
        </div>

      </div>
    </div>
  );
}
