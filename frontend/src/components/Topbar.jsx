import { RefreshCw, Wifi, WifiOff, Activity, Network, Trash2 } from "lucide-react";
import styles from "./Topbar.module.css";

export function Topbar({ stats, scanStatus, onScan, view, onViewChange, onNetworks, onTrash }) {
  return (
    <header className={styles.topbar}>
      <div className={styles.brand}>
        <Activity size={20} color="var(--accent)" />
        <span className={styles.brandName}>Dude Modern</span>
      </div>

      <nav className={styles.nav}>
        <button
          className={`${styles.navBtn} ${view === "map" ? styles.active : ""}`}
          onClick={() => onViewChange("map")}
        >
          Map
        </button>
        <button
          className={`${styles.navBtn} ${view === "grid" ? styles.active : ""}`}
          onClick={() => onViewChange("grid")}
        >
          Devices
        </button>
      </nav>

      <div className={styles.right}>
        <div className={styles.statGroup}>
          <span className={styles.statOnline}>
            <Wifi size={13} />
            {stats.online} online
          </span>
          <span className={styles.statOffline}>
            <WifiOff size={13} />
            {stats.offline} offline
          </span>
          <span className={styles.statTotal}>{stats.total} total</span>
          {stats.networks > 0 && (
            <span className={styles.statNetworks}>
              <Network size={12} />
              {stats.networks} {stats.networks === 1 ? "subnet" : "subnets"}
            </span>
          )}
        </div>

        <button className={styles.trashBtn} onClick={onTrash} title="Deleted devices">
          <Trash2 size={14} />
        </button>

        <button className={styles.networksBtn} onClick={onNetworks} title="Manage subnets">
          <Network size={14} />
          Subnets
        </button>

        <button
          className={`${styles.scanBtn} ${scanStatus.running ? styles.scanning : ""}`}
          onClick={onScan}
          disabled={scanStatus.running}
          title={scanStatus.running ? "Scanning…" : "Scan all subnets"}
        >
          <RefreshCw size={14} className={scanStatus.running ? styles.spin : ""} />
          {scanStatus.running ? "Scanning…" : "Scan"}
        </button>
      </div>
    </header>
  );
}
