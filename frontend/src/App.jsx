import { useState, useCallback } from "react";
import { Topbar } from "./components/Topbar";
import { NetworkMap } from "./components/NetworkMap";
import { GridView } from "./components/GridView";
import { EditModal } from "./components/EditModal";
import { NetworksModal } from "./components/NetworksModal";
import { TrashModal } from "./components/TrashModal";
import { useDevices } from "./useDevices";
import styles from "./App.module.css";

export default function App() {
  const { devices, stats, scanStatus, topology, traffic, loading, triggerScan, updateDevice, deleteDevice, refresh } =
    useDevices();
  const [view, setView] = useState("map");
  const [editing, setEditing] = useState(null);
  const [showNetworks, setShowNetworks] = useState(false);
  const [showTrash, setShowTrash] = useState(false);

  const handleMove = useCallback(
    (id, x, y) => updateDevice(id, { x, y }),
    [updateDevice]
  );

  const handleDelete = useCallback(
    async (id) => {
      if (confirm("Delete this device?")) await deleteDevice(id);
    },
    [deleteDevice]
  );

  if (loading) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner} />
        <span>Connecting to backend…</span>
      </div>
    );
  }

  return (
    <div className={styles.app}>
      <Topbar
        stats={stats}
        scanStatus={scanStatus}
        onScan={triggerScan}
        view={view}
        onViewChange={setView}
        onNetworks={() => setShowNetworks(true)}
        onTrash={() => setShowTrash(true)}
      />

      <main className={styles.main}>
        {view === "map" ? (
          <NetworkMap
            devices={devices}
            topology={topology}
            traffic={traffic}
            onEdit={setEditing}
            onDelete={handleDelete}
            onMove={handleMove}
          />
        ) : (
          <GridView
            devices={devices}
            onEdit={setEditing}
            onDelete={handleDelete}
          />
        )}
      </main>

      {editing && (
        <EditModal
          device={editing}
          devices={devices}
          onSave={updateDevice}
          onClose={() => setEditing(null)}
        />
      )}

      {showNetworks && (
        <NetworksModal onClose={() => setShowNetworks(false)} />
      )}

      {showTrash && (
        <TrashModal onClose={() => setShowTrash(false)} onRestored={refresh} />
      )}
    </div>
  );
}
