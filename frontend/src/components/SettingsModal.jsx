import { useState, useEffect } from "react";
import { X, CheckCircle, XCircle, Loader } from "lucide-react";
import { api } from "../api";
import styles from "./SettingsModal.module.css";

export function SettingsModal({ onClose }) {
  const [form, setForm] = useState({ url: "", user: "", password: "" });
  const [cleanup, setCleanup] = useState({ soft: "30", hard: "90" });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null); // null | "ok" | "fail"

  useEffect(() => {
    Promise.all([
      api.uptimeKuma.getSettings(),
      api.settings.get(),
    ]).then(([uk, all]) => {
      setForm({
        url:      uk.uptime_kuma_url  || "",
        user:     uk.uptime_kuma_user || "",
        password: uk.uptime_kuma_pass || "",
      });
      setCleanup({
        soft: all.stale_soft_days ?? "30",
        hard: all.stale_hard_days ?? "90",
      });
    }).catch(() => {});
  }, []);

  function set(key, val) { setForm((f) => ({ ...f, [key]: val })); }
  function setC(key, val) { setCleanup((f) => ({ ...f, [key]: val })); }

  async function handleSave() {
    setSaving(true);
    try {
      await Promise.all([
        api.uptimeKuma.saveSettings(form),
        api.settings.set("stale_soft_days", String(parseInt(cleanup.soft) || 30)),
        api.settings.set("stale_hard_days", String(parseInt(cleanup.hard) || 90)),
      ]);
      onClose();
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await api.uptimeKuma.test();
      setTestResult(r.ok ? "ok" : "fail");
    } catch {
      setTestResult("fail");
    } finally {
      setTesting(false);
    }
  }

  // Webhook URL hint
  const webhookUrl = form.url
    ? `${window.location.origin}/api/webhook`
    : "Configure the URL above first";

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>

        {/* ── Sticky header ── */}
        <div className={styles.modalHeader}>
          <div className={styles.header}>
            <h2 className={styles.title}>Settings</h2>
            <button className={styles.close} onClick={onClose}><X size={18} /></button>
          </div>
        </div>

        {/* ── Scrollable body ── */}
        <div className={styles.body}>
          <h3 className={styles.sectionTitle}>Uptime Kuma</h3>
          <p className={styles.hint}>
            Connect to Uptime Kuma to add/remove monitors from the device editor
            and receive status alerts on the map.
          </p>

          <div className={styles.field}>
            <label>URL</label>
            <input
              value={form.url}
              onChange={(e) => set("url", e.target.value)}
              placeholder="http://192.168.20.199:3001"
            />
          </div>
          <div className={styles.row}>
            <div className={styles.field}>
              <label>Username</label>
              <input
                value={form.user}
                onChange={(e) => set("user", e.target.value)}
                placeholder="admin"
                autoComplete="off"
              />
            </div>
            <div className={styles.field}>
              <label>Password</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => set("password", e.target.value)}
                placeholder="••••••"
                autoComplete="new-password"
              />
            </div>
          </div>

          <div className={styles.testRow}>
            <button className={styles.testBtn} onClick={handleTest} disabled={testing || !form.url}>
              {testing ? <Loader size={13} className={styles.spin} /> : null}
              Test connection
            </button>
            {testResult === "ok"   && <span className={styles.ok}><CheckCircle size={14}/> Connected</span>}
            {testResult === "fail" && <span className={styles.fail}><XCircle size={14}/> Failed</span>}
          </div>

          <h3 className={styles.sectionTitle}>Device Cleanup</h3>
          <p className={styles.hint}>
            Devices that have been offline for a long time are removed automatically.
            Set to <strong>0</strong> to disable a threshold.
          </p>
          <div className={styles.row}>
            <div className={styles.field}>
              <label>Hide after (days offline)</label>
              <div className={styles.inputUnit}>
                <input
                  type="number" min="0" max="365"
                  value={cleanup.soft}
                  onChange={(e) => setC("soft", e.target.value)}
                />
                <span>days</span>
              </div>
              <span className={styles.fieldHint}>Moved to trash, restorable</span>
            </div>
            <div className={styles.field}>
              <label>Delete after (days offline)</label>
              <div className={styles.inputUnit}>
                <input
                  type="number" min="0" max="3650"
                  value={cleanup.hard}
                  onChange={(e) => setC("hard", e.target.value)}
                />
                <span>days</span>
              </div>
              <span className={styles.fieldHint}>Permanently deleted</span>
            </div>
          </div>

          <h3 className={styles.sectionTitle}>Webhook (Option B)</h3>
          <p className={styles.hint}>
            In Uptime Kuma, add a <strong>Webhook</strong> notification pointing to this URL.
            When a monitor goes down or recovers, the device on the map will change color.
          </p>
          <div className={styles.webhookBox}>
            <code>{webhookUrl}</code>
          </div>
        </div>

        {/* ── Sticky footer ── */}
        <div className={styles.modalFooter}>
          <div className={styles.footer}>
            <button className={styles.cancel} onClick={onClose}>Cancel</button>
            <button className={styles.save} onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
