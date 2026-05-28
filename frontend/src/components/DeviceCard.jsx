import { ExternalLink, Pencil, Trash2, Terminal, Globe, Activity } from "lucide-react";
import { DeviceIcon } from "./DeviceIcon";
import styles from "./DeviceCard.module.css";

function formatOffline(iso) {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso + "Z").getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d`;
  return `${Math.floor(d / 30)}mo`;
}

export function DeviceCard({ device, onEdit, onDelete }) {
  const displayName = device.label || device.hostname || device.ip;
  const webUrl = device.web_port
    ? `${device.web_protocol}://${device.ip}:${device.web_port}`
    : null;
  const offlineFor = !device.is_online ? formatOffline(device.offline_since) : null;

  return (
    <div className={`${styles.card} ${device.is_online ? styles.online : styles.offline}`}>
      <div className={styles.header}>
        <div className={`${styles.iconWrap} ${device.is_online ? styles.iconOnline : styles.iconOffline}`}>
          <DeviceIcon type={device.icon || "unknown"} size={22} />
        </div>
        <div className={styles.status}>
          <span className={`${styles.dot} ${device.is_online ? styles.dotOnline : styles.dotOffline}`} />
          {device.is_online ? "Online" : (
            <span>
              Offline{offlineFor && <span className={styles.offlineDuration}> · {offlineFor}</span>}
            </span>
          )}
        </div>
      </div>

      <div className={styles.body}>
        <div className={styles.name} title={displayName}>{displayName}</div>
        {device.hostname && device.hostname !== displayName && (
          <div className={styles.hostname}>{device.hostname}</div>
        )}
        <div className={styles.ip}>{device.ip}</div>
        {device.vendor && <div className={styles.vendor}>{device.vendor}</div>}
        {device.mac && <div className={styles.mac}>{device.mac}</div>}
        {device.network && <div className={styles.network}>{device.network}</div>}
      </div>

      {/* ── Capability chips ── */}
      {(device.ssh_banner || device.web_port || device.monitor_id) && (
        <div className={styles.chips}>
          {device.ssh_banner && (
            <span className={styles.chip} title={device.ssh_banner}>
              <Terminal size={11} /> SSH
            </span>
          )}
          {device.web_port && (
            <span className={styles.chip} title={`${device.web_protocol}://${device.ip}:${device.web_port}`}>
              <Globe size={11} /> Web
            </span>
          )}
          {device.monitor_id && (
            <span className={`${styles.chip} ${styles.chipMonitor}`} title="Uptime Kuma monitor active">
              <Activity size={11} /> Monitor
            </span>
          )}
        </div>
      )}

      <div className={styles.actions}>
        {webUrl && (
          <a href={webUrl} target="_blank" rel="noreferrer" className={styles.actionBtn} title="Open web UI">
            <ExternalLink size={14} />
          </a>
        )}
        <button className={styles.actionBtn} onClick={() => onEdit(device)} title="Edit">
          <Pencil size={14} />
        </button>
        <button className={`${styles.actionBtn} ${styles.danger}`} onClick={() => onDelete(device.id)} title="Delete">
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}
