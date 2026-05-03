import { useState, useEffect } from "react";
import { X, Plus, Trash2, RefreshCw, Network } from "lucide-react";
import { api } from "../api";
import styles from "./NetworksModal.module.css";

export function NetworksModal({ onClose }) {
  const [configured, setConfigured] = useState([]);
  const [detected, setDetected] = useState([]);
  const [newNet, setNewNet] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const [conf, det] = await Promise.all([
        fetch("/api/networks/configured").then((r) => r.json()),
        fetch("/api/networks/detected").then((r) => r.json()),
      ]);
      setConfigured(conf.networks);
      setDetected(det.networks);
    } finally {
      setLoading(false);
    }
  }

  async function addNetwork(cidr) {
    setError("");
    try {
      const res = await fetch("/api/networks/configured", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ network: cidr }),
      });
      if (!res.ok) {
        const t = await res.text();
        setError(t);
        return;
      }
      const data = await res.json();
      setConfigured(data.networks);
      setNewNet("");
    } catch (e) {
      setError(String(e));
    }
  }

  async function removeNetwork(cidr) {
    const encoded = encodeURIComponent(cidr);
    const res = await fetch(`/api/networks/configured/${encoded}`, { method: "DELETE" });
    if (res.ok) {
      const data = await res.json();
      setConfigured(data.networks);
    }
  }

  const undetectedButConfigured = configured.filter((n) => !detected.includes(n));

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>

        {/* ── Sticky header ── */}
        <div className={styles.modalHeader}>
          <div className={styles.header}>
            <div className={styles.titleRow}>
              <Network size={18} color="var(--accent)" />
              <h2 className={styles.title}>Network Subnets</h2>
            </div>
            <button className={styles.close} onClick={onClose}><X size={18} /></button>
          </div>
          <p className={styles.desc}>
            All configured subnets are scanned in parallel. Add as many as you need.
          </p>
        </div>

        {/* ── Scrollable body ── */}
        <div className={styles.body}>
          {/* Detected automatically */}
          {detected.length > 0 && (
            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <span>Detected on host</span>
                <button className={styles.refreshBtn} onClick={load} title="Refresh">
                  <RefreshCw size={12} />
                </button>
              </div>
              <div className={styles.chips}>
                {detected.map((net) => {
                  const isAdded = configured.includes(net);
                  return (
                    <div key={net} className={`${styles.chip} ${isAdded ? styles.chipAdded : ""}`}>
                      <span>{net}</span>
                      {!isAdded && (
                        <button className={styles.chipAdd} onClick={() => addNetwork(net)} title="Add">
                          <Plus size={11} />
                        </button>
                      )}
                      {isAdded && <span className={styles.chipCheck}>✓</span>}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* Configured list */}
          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <span>Configured networks ({configured.length})</span>
            </div>
            {loading ? (
              <div className={styles.empty}>Loading…</div>
            ) : configured.length === 0 ? (
              <div className={styles.empty}>No networks configured yet.</div>
            ) : (
              <ul className={styles.list}>
                {configured.map((net) => (
                  <li key={net} className={styles.listItem}>
                    <code className={styles.cidr}>{net}</code>
                    {detected.includes(net) && <span className={styles.badge}>local</span>}
                    <button
                      className={styles.removeBtn}
                      onClick={() => removeNetwork(net)}
                      title="Remove"
                    >
                      <Trash2 size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Manual add */}
          <section className={styles.section}>
            <div className={styles.sectionHeader}><span>Add manually</span></div>
            <div className={styles.addRow}>
              <input
                className={styles.input}
                placeholder="e.g. 10.0.0.0/24"
                value={newNet}
                onChange={(e) => setNewNet(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addNetwork(newNet)}
              />
              <button
                className={styles.addBtn}
                onClick={() => addNetwork(newNet)}
                disabled={!newNet.trim()}
              >
                <Plus size={15} /> Add
              </button>
            </div>
            {error && <div className={styles.error}>{error}</div>}
          </section>
        </div>

        {/* ── Sticky footer ── */}
        <div className={styles.modalFooter}>
          <div className={styles.footer}>
            <button className={styles.doneBtn} onClick={onClose}>Done</button>
          </div>
        </div>

      </div>
    </div>
  );
}
