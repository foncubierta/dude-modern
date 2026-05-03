import { ExternalLink, Pencil, Trash2 } from "lucide-react";
import { DeviceIcon } from "./DeviceIcon";
import styles from "./DeviceCard.module.css";

export function DeviceCard({ device, onEdit, onDelete }) {
  const displayName = device.label || device.hostname || device.ip;
  const webUrl = device.web_port
    ? `${device.web_protocol}://${device.ip}:${device.web_port}`
    : null;

  return (
    <div className={`${styles.card} ${device.is_online ? styles.online : styles.offline}`}>
      <div className={styles.header}>
        <div className={`${styles.iconWrap} ${device.is_online ? styles.iconOnline : styles.iconOffline}`}>
          <DeviceIcon type={device.icon || "unknown"} size={22} />
        </div>
        <div className={styles.status}>
          <span className={`${styles.dot} ${device.is_online ? styles.dotOnline : styles.dotOffline}`} />
          {device.is_online ? "Online" : "Offline"}
        </div>
      </div>

      <div className={styles.body}>
        <div className={styles.name} title={displayName}>{displayName}</div>
        <div className={styles.ip}>{device.ip}</div>
        {device.vendor && <div className={styles.vendor}>{device.vendor}</div>}
        {device.mac && <div className={styles.mac}>{device.mac}</div>}
        {device.network && <div className={styles.network}>{device.network}</div>}
      </div>

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
