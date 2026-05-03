import { useState, useMemo } from "react";
import { Search } from "lucide-react";
import { DeviceCard } from "./DeviceCard";
import styles from "./GridView.module.css";

export function GridView({ devices, onEdit, onDelete }) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [networkFilter, setNetworkFilter] = useState("all");

  const networks = useMemo(() => {
    const nets = [...new Set(devices.map((d) => d.network).filter(Boolean))].sort();
    return nets;
  }, [devices]);

  const filtered = devices.filter((d) => {
    const matchStatus =
      filter === "all" ||
      (filter === "online" && d.is_online) ||
      (filter === "offline" && !d.is_online) ||
      (filter === "web" && d.web_port);

    const matchNetwork = networkFilter === "all" || d.network === networkFilter;

    const q = search.toLowerCase();
    const matchSearch =
      !q ||
      d.ip.includes(q) ||
      (d.label || "").toLowerCase().includes(q) ||
      (d.hostname || "").toLowerCase().includes(q) ||
      (d.vendor || "").toLowerCase().includes(q) ||
      (d.mac || "").toLowerCase().includes(q) ||
      (d.network || "").includes(q);

    return matchStatus && matchNetwork && matchSearch;
  });

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        <div className={styles.search}>
          <Search size={14} className={styles.searchIcon} />
          <input
            placeholder="Search by IP, name, vendor, subnet…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className={styles.filters}>
          {["all", "online", "offline", "web"].map((f) => (
            <button
              key={f}
              className={`${styles.filterBtn} ${filter === f ? styles.active : ""}`}
              onClick={() => setFilter(f)}
            >
              {f === "web" ? "Has web UI" : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        {networks.length > 1 && (
          <div className={styles.filters}>
            <button
              className={`${styles.filterBtn} ${styles.netBtn} ${networkFilter === "all" ? styles.active : ""}`}
              onClick={() => setNetworkFilter("all")}
            >
              All subnets
            </button>
            {networks.map((net) => (
              <button
                key={net}
                className={`${styles.filterBtn} ${styles.netBtn} ${networkFilter === net ? styles.active : ""}`}
                onClick={() => setNetworkFilter(net)}
              >
                {net}
              </button>
            ))}
          </div>
        )}

        <span className={styles.count}>{filtered.length} devices</span>
      </div>

      <div className={styles.grid}>
        {filtered.map((d) => (
          <DeviceCard key={d.id} device={d} onEdit={onEdit} onDelete={onDelete} />
        ))}
        {filtered.length === 0 && (
          <div className={styles.empty}>No devices match your filter.</div>
        )}
      </div>
    </div>
  );
}
