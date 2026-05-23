import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { ExternalLink, Pencil, Trash2 } from "lucide-react";
import { DeviceIcon } from "./DeviceIcon";
import styles from "./DeviceNode.module.css";

const NEW_THRESHOLD_MS = 10 * 60 * 1000; // 10 minutes

function formatOffline(iso) {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso + "Z").getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1)   return "just now";
  if (m < 60)  return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 30)  return `${d}d`;
  return `${Math.floor(d / 30)}mo`;
}

export const DeviceNode = memo(({ data }) => {
  const { device, traffic, onEdit, onDelete } = data;
  const displayName = device.label || device.hostname || device.ip;
  const webUrl = device.web_port
    ? `${device.web_protocol}://${device.ip}:${device.web_port}`
    : null;
  const hasTraffic = traffic && (traffic.rx_mbps > 0 || traffic.tx_mbps > 0);
  const isNew  = device.first_seen &&
    (Date.now() - new Date(device.first_seen + "Z").getTime()) < NEW_THRESHOLD_MS;
  const isDown = device.alert_status === "down";
  const offlineFor = !device.is_online ? formatOffline(device.offline_since) : null;

  return (
    <div className={[
      styles.node,
      device.is_online ? styles.online : styles.offline,
      isNew  ? styles.isNew  : "",
      isDown ? styles.isDown : "",
    ].join(" ")}>
      <Handle type="target" position={Position.Top} className={styles.handle} />

      {isDown && <span className={styles.alertBadge}>DOWN</span>}
      {isNew  && <span className={styles.newBadge}>NEW</span>}

      <div className={`${styles.iconWrap} ${device.is_online ? styles.iconOnline : styles.iconOffline}`}>
        <DeviceIcon type={device.icon || "unknown"} size={24} />
        <span className={`${styles.dot} ${device.is_online ? styles.dotOnline : styles.dotOffline}`} />
      </div>

      <div className={styles.info}>
        <div className={styles.name} title={displayName}>{displayName}</div>
        {device.hostname && device.hostname !== displayName && (
          <div className={styles.hostname}>{device.hostname}</div>
        )}
        <div className={styles.ip}>{device.ip}</div>
        {offlineFor && (
          <div className={styles.offlineSince}>offline {offlineFor}</div>
        )}
        {device.vendor && <div className={styles.vendor}>{device.vendor}</div>}
        {device.network && <div className={styles.network}>{device.network}</div>}
        {hasTraffic && (
          <div className={styles.traffic}>
            <span className={styles.trafficDown}>↓{traffic.rx_mbps}</span>
            <span className={styles.trafficUp}>↑{traffic.tx_mbps}</span>
            <span className={styles.trafficUnit}>Mbps</span>
          </div>
        )}
      </div>

      <div className={styles.actions}>
        {webUrl && (
          <a href={webUrl} target="_blank" rel="noreferrer" className={styles.btn} title="Open web UI">
            <ExternalLink size={12} />
          </a>
        )}
        <button className={styles.btn} onClick={() => onEdit(device)} title="Edit">
          <Pencil size={12} />
        </button>
        <button className={`${styles.btn} ${styles.danger}`} onClick={() => onDelete(device.id)} title="Delete">
          <Trash2 size={12} />
        </button>
      </div>

      <Handle type="source" position={Position.Bottom} className={styles.handle} />
    </div>
  );
});
