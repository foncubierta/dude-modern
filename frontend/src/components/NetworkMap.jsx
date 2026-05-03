import { useCallback, useEffect } from "react";
import {
  ReactFlow, Background, Controls, MiniMap,
  useNodesState, useEdgesState, addEdge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { DeviceNode } from "./DeviceNode";
import styles from "./NetworkMap.module.css";

const nodeTypes = { device: DeviceNode };

export function NetworkMap({ devices, onEdit, onDelete, onMove }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, , onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    const newNodes = devices.map((d) => ({
      id: String(d.id),
      type: "device",
      position: { x: d.x, y: d.y },
      data: { device: d, onEdit, onDelete },
      draggable: true,
    }));
    setNodes(newNodes);
  }, [devices, onEdit, onDelete]);

  const onNodeDragStop = useCallback(
    (_, node) => {
      onMove(Number(node.id), node.position.x, node.position.y);
    },
    [onMove]
  );

  return (
    <div className={styles.wrap}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#30363d" gap={32} size={1} />
        <Controls
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
          }}
        />
        <MiniMap
          style={{
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
          }}
          nodeColor={(n) => n.data?.device?.is_online ? "#3fb950" : "#484f58"}
          maskColor="rgba(13,17,23,0.6)"
        />
      </ReactFlow>
    </div>
  );
}
