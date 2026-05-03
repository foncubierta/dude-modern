import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { ExternalLink, Pencil, Trash2 } from "lucide-react";
import { DeviceIcon } from "./DeviceIcon";
import styles from "./DeviceNode.module.css";

const NEW_THRESHOLD_MS = 10 * 60 * 1000; // 10 minutes

export const DeviceNode = memo(({ data }) => {
  const { device, traffic, onEdit, onDelete } = data;
  const displayName = device.label || device.hostname || device.ip;
  const webUrl = device.web_port
    ? `${device.web_protocol}://${device.ip}:${device.web_port}`
    : null;
  const hasTraffic = traffic && (traffic.rx_mbps > 0 || traffic.tx_mbps > 0);
  const isNew = device.first_seen &&
    (Date.now() - new Date(device.first_seen + "Z").getTime()) < NEW_THRESHOLD_MS;

  return (
    <div className={`${styles.node} ${device.is_online ? styles.online : styles.offline} ${isNew ? styles.isNew : ""}`}>
      <Handle type="target" position={Position.Top} className={styles.handle} />

      {isNew && <span className={styles.newBadge}>NEW</span>}
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
