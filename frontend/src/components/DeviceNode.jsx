import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { ExternalLink, Pencil, Trash2 } from "lucide-react";
import { DeviceIcon } from "./DeviceIcon";
import styles from "./DeviceNode.module.css";

export const DeviceNode = memo(({ data }) => {
  const { device, onEdit, onDelete } = data;
  const displayName = device.label || device.hostname || device.ip;
  const webUrl = device.web_port
    ? `${device.web_protocol}://${device.ip}:${device.web_port}`
    : null;

  return (
    <div className={`${styles.node} ${device.is_online ? styles.online : styles.offline}`}>
      <Handle type="target" position={Position.Top} className={styles.handle} />

      <div className={`${styles.iconWrap} ${device.is_online ? styles.iconOnline : styles.iconOffline}`}>
        <DeviceIcon type={device.icon || "unknown"} size={24} />
        <span className={`${styles.dot} ${device.is_online ? styles.dotOnline : styles.dotOffline}`} />
      </div>

      <div className={styles.info}>
        <div className={styles.name} title={displayName}>{displayName}</div>
        <div className={styles.ip}>{device.ip}</div>
        {device.vendor && <div className={styles.vendor}>{device.vendor}</div>}
        {device.network && <div className={styles.network}>{device.network}</div>}
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
