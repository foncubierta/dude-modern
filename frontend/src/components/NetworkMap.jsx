import { useCallback, useEffect } from "react";
import {
  ReactFlow, Background, Controls, MiniMap,
  useNodesState, useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { DeviceNode } from "./DeviceNode";
import styles from "./NetworkMap.module.css";

const nodeTypes = { device: DeviceNode };

function buildEdges(topology, traffic) {
  if (!topology?.links) return [];
  return topology.links.map(({ source, target }) => {
    const srcTraffic = traffic?.devices?.[String(source)];
    const hasFlow = srcTraffic && (srcTraffic.rx_mbps > 0.1 || srcTraffic.tx_mbps > 0.1);
    const label = hasFlow
      ? `↓${srcTraffic.rx_mbps} ↑${srcTraffic.tx_mbps} Mbps`
      : undefined;
    return {
      id: `e${source}-${target}`,
      source: String(source),
      target: String(target),
      animated: !!hasFlow,
      label,
      labelStyle: { fontSize: 9, fill: "#8b949e" },
      labelBgStyle: { fill: "#161b22", fillOpacity: 0.85 },
      labelBgPadding: [4, 2],
      style: {
        stroke: hasFlow ? "#3fb950" : "#30363d",
        strokeWidth: hasFlow ? 2 : 1.5,
        opacity: 0.8,
      },
    };
  });
}

export function NetworkMap({ devices, topology, traffic, onEdit, onDelete, onMove }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    setNodes(devices.map((d) => ({
      id: String(d.id),
      type: "device",
      position: { x: d.x, y: d.y },
      data: { device: d, traffic: traffic?.devices?.[String(d.id)], onEdit, onDelete },
      draggable: true,
    })));
  }, [devices, traffic, onEdit, onDelete]);

  useEffect(() => {
    setEdges(buildEdges(topology, traffic));
  }, [topology, traffic]);

  const onNodeDragStop = useCallback(
    (_, node) => onMove(Number(node.id), node.position.x, node.position.y),
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
