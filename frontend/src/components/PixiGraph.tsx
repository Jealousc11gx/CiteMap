import { useEffect, useRef, useState } from "react";
import { Application, Container, Graphics, Text, FederatedPointerEvent } from "pixi.js";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import type { GraphData, GraphNode, GraphEdge } from "@/types";
import { cn } from "@/lib/utils";

interface PixiNodeView {
  node: GraphNode;
  forceNode: ForceNode;
  root: Container;
  body: Graphics;
  label: Text;
}

interface PixiEdgeView {
  id: string;
  sourceId: string;
  targetId: string;
  line: Graphics;
}

interface ForceNode extends SimulationNodeDatum {
  id: string;
  size: number;
}

interface ForceLink extends SimulationLinkDatum<ForceNode> {
  id: string;
}

interface ForceLayoutState {
  nodes: ForceNode[];
  links: ForceLink[];
  nodeById: Map<string, ForceNode>;
  simulation: Simulation<ForceNode, ForceLink>;
}

interface PixiGraphProps {
  data: GraphData;
  nodeColor: (node: GraphNode) => string;
  onNodeClick?: (node: GraphNode) => void;
  className?: string;
}

function colorToNumber(color: string): number {
  return Number.parseInt(color.replace("#", ""), 16);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function getNodeRadius(node: GraphNode): number {
  const base = node.group === "team" ? 14 : 10;
  return base;
}

function getInitialPosition(index: number, total: number, width: number, height: number) {
  const radius = Math.max(60, Math.min(width, height) * 0.22);
  const angle = (index / Math.max(total, 1)) * Math.PI * 2;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

function createForceLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number,
): ForceLayoutState {
  const forceNodes: ForceNode[] = nodes.map((node, index) => ({
    id: node.id,
    size: getNodeRadius(node),
    ...getInitialPosition(index, nodes.length, width, height),
  }));

  const nodeById = new Map(forceNodes.map((n) => [n.id, n]));
  const forceLinks: ForceLink[] = edges
    .filter((edge) => nodeById.has(String(edge.source)) && nodeById.has(String(edge.target)))
    .map((edge, index) => ({
      id: `edge-${index}`,
      source: String(edge.source),
      target: String(edge.target),
    }));

  const nodeCount = forceNodes.length;
  const linkDistance = nodeCount <= 18 ? 120 : nodeCount <= 48 ? 90 : 70;
  const chargeRange = Math.max(width, height) * (nodeCount <= 30 ? 1.3 : 1.0);
  const chargeStrength = nodeCount <= 18 ? -400 : nodeCount <= 60 ? -300 : -220;

  const simulation = forceSimulation<ForceNode>(forceNodes)
    .force(
      "link",
      forceLink<ForceNode, ForceLink>(forceLinks)
        .id((d) => d.id)
        .distance(linkDistance)
        .strength(0.5),
    )
    .force(
      "charge",
      forceManyBody<ForceNode>()
        .distanceMin(1)
        .distanceMax(chargeRange)
        .theta(0.5)
        .strength(chargeStrength),
    )
    .force(
      "collision",
      forceCollide<ForceNode>()
        .radius((d) => Math.max(28, d.size * 0.9))
        .iterations(2),
    )
    .force("x", forceX<ForceNode>(0).strength(0.03))
    .force("y", forceY<ForceNode>(0).strength(0.03))
    .force("center", forceCenter<ForceNode>(0, 0))
    .velocityDecay(0.5)
    .alpha(1)
    .alphaDecay(0.02)
    .alphaMin(0.01);

  simulation.stop();

  return { nodes: forceNodes, links: forceLinks, nodeById, simulation };
}

function useDarkMode() {
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  );

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  return isDark;
}

export function PixiGraph({ data, nodeColor, onNodeClick, className }: PixiGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<Application | null>(null);
  const sceneRef = useRef<Container | null>(null);
  const edgeLayerRef = useRef<Container | null>(null);
  const nodeLayerRef = useRef<Container | null>(null);
  const labelLayerRef = useRef<Container | null>(null);
  const forceLayoutRef = useRef<ForceLayoutState | null>(null);
  const nodeViewsRef = useRef<Map<string, PixiNodeView>>(new Map());
  const edgeViewsRef = useRef<Map<string, PixiEdgeView>>(new Map());
  const draggingNodeIdRef = useRef<string | null>(null);
  const nodePointerStartRef = useRef<{ x: number; y: number } | null>(null);
  const didMoveDraggedNodeRef = useRef(false);
  const isPanningRef = useRef(false);
  const panStartRef = useRef<{ x: number; y: number } | null>(null);
  const sceneStartRef = useRef<{ x: number; y: number } | null>(null);
  const sizeRef = useRef<{ width: number; height: number }>({ width: 0, height: 0 });
  const tickerHandlerRef = useRef<(() => void) | null>(null);
  const isDark = useDarkMode();

  const textColor = isDark ? 0xe2e8f0 : 0x0f172a;
  const strokeColor = isDark ? 0x334155 : 0xcbd5e1;
  const edgeColor = isDark ? 0x475569 : 0x94a3b8;

  useEffect(() => {
    if (!containerRef.current) return;

    let cancelled = false;

    async function init() {
      const app = new Application();
      await app.init({
        width: containerRef.current!.clientWidth,
        height: containerRef.current!.clientHeight,
        antialias: true,
        autoDensity: true,
        backgroundAlpha: 0,
        preference: "webgl",
        resolution: Math.min(window.devicePixelRatio || 1, 2),
        powerPreference: "high-performance",
      });

      if (cancelled) {
        app.destroy({ removeView: true }, { children: true });
        return;
      }

      app.canvas.className = "h-full w-full";
      containerRef.current!.appendChild(app.canvas);
      appRef.current = app;

      const scene = new Container();
      const edgeLayer = new Container();
      const nodeLayer = new Container();
      const labelLayer = new Container();

      scene.sortableChildren = true;
      edgeLayer.zIndex = 1;
      nodeLayer.zIndex = 2;
      labelLayer.zIndex = 3;
      scene.addChild(edgeLayer, nodeLayer, labelLayer);
      app.stage.addChild(scene);
      app.stage.eventMode = "static";
      app.stage.hitArea = app.screen;

      sceneRef.current = scene;
      edgeLayerRef.current = edgeLayer;
      nodeLayerRef.current = nodeLayer;
      labelLayerRef.current = labelLayer;

      sizeRef.current = {
        width: containerRef.current!.clientWidth,
        height: containerRef.current!.clientHeight,
      };

      rebuildGraph();
      fitToView();

      const handleWheel = (event: WheelEvent) => {
        event.preventDefault();
        const factor = Math.exp(-event.deltaY * 0.001);
        zoomAround(factor, { x: event.offsetX, y: event.offsetY });
      };

      const handleStagePointerDown = (event: FederatedPointerEvent) => {
        if (draggingNodeIdRef.current) return;
        isPanningRef.current = true;
        panStartRef.current = { x: event.global.x, y: event.global.y };
        sceneStartRef.current = { x: scene.position.x, y: scene.position.y };
      };

      const handleStagePointerMove = (event: FederatedPointerEvent) => {
        if (draggingNodeIdRef.current && forceLayoutRef.current) {
          const node = forceLayoutRef.current.nodeById.get(draggingNodeIdRef.current);
          if (!node) return;
          if (nodePointerStartRef.current) {
            const dx = event.global.x - nodePointerStartRef.current.x;
            const dy = event.global.y - nodePointerStartRef.current.y;
            if (Math.hypot(dx, dy) > 4) {
              didMoveDraggedNodeRef.current = true;
            }
          }
          const local = event.getLocalPosition(scene);
          node.fx = local.x;
          node.fy = local.y;
          forceLayoutRef.current.simulation.alphaTarget(0.2).restart();
          return;
        }

        if (!isPanningRef.current || !panStartRef.current || !sceneStartRef.current) return;
        scene.position.set(
          sceneStartRef.current.x + event.global.x - panStartRef.current.x,
          sceneStartRef.current.y + event.global.y - panStartRef.current.y,
        );
      };

      const endPointerAction = () => {
        if (draggingNodeIdRef.current && forceLayoutRef.current) {
          const node = forceLayoutRef.current.nodeById.get(draggingNodeIdRef.current);
          if (node) {
            node.fx = undefined;
            node.fy = undefined;
          }
          forceLayoutRef.current.simulation.alphaTarget(0);
        }
        draggingNodeIdRef.current = null;
        nodePointerStartRef.current = null;
        didMoveDraggedNodeRef.current = false;
        isPanningRef.current = false;
        panStartRef.current = null;
        sceneStartRef.current = null;
      };

      app.canvas.addEventListener("wheel", handleWheel, { passive: false });
      app.stage.on("pointerdown", handleStagePointerDown);
      app.stage.on("globalpointermove", handleStagePointerMove);
      app.stage.on("globalpointerup", endPointerAction);
      app.stage.on("globalpointerupoutside", endPointerAction);
      window.addEventListener("pointerup", endPointerAction);
      window.addEventListener("blur", endPointerAction);

      return () => {
        app.canvas.removeEventListener("wheel", handleWheel);
        window.removeEventListener("pointerup", endPointerAction);
        window.removeEventListener("blur", endPointerAction);
      };
    }

    const cleanupPromise = init();

    return () => {
      cancelled = true;
      cleanupPromise.then((cleanup) => cleanup?.());
      appRef.current?.destroy({ removeView: true }, { children: true });
      appRef.current = null;
    };
  }, []);

  useEffect(() => {
    rebuildGraph();
    fitToView();
  }, [data, isDark]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(() => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (width <= 0 || height <= 0) return;
      if (sizeRef.current.width === width && sizeRef.current.height === height) return;

      sizeRef.current = { width, height };
      appRef.current?.renderer.resize(width, height);
      forceLayoutRef.current?.simulation.restart();
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  function zoomAround(factor: number, point: { x: number; y: number }) {
    const scene = sceneRef.current;
    if (!scene) return;
    const currentScale = scene.scale.x || 1;
    const nextScale = clamp(currentScale * factor, 0.15, 4);
    const worldPoint = {
      x: (point.x - scene.position.x) / currentScale,
      y: (point.y - scene.position.y) / currentScale,
    };
    scene.scale.set(nextScale);
    scene.position.set(
      point.x - worldPoint.x * nextScale,
      point.y - worldPoint.y * nextScale,
    );
  }

  function fitToView() {
    const scene = sceneRef.current;
    const layout = forceLayoutRef.current;
    if (!scene || !layout || layout.nodes.length === 0) {
      scene?.scale.set(1);
      scene?.position.set(sizeRef.current.width / 2, sizeRef.current.height / 2);
      return;
    }

    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    for (const node of layout.nodes) {
      const x = typeof node.x === "number" ? node.x : 0;
      const y = typeof node.y === "number" ? node.y : 0;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }

    const padding = 80;
    const width = Math.max(1, maxX - minX);
    const height = Math.max(1, maxY - minY);
    const availableWidth = Math.max(1, sizeRef.current.width - padding * 2);
    const availableHeight = Math.max(1, sizeRef.current.height - padding * 2);
    const scale = Math.min(availableWidth / width, availableHeight / height, 1.4);
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    scene.scale.set(scale);
    scene.position.set(
      sizeRef.current.width / 2 - centerX * scale,
      sizeRef.current.height / 2 - centerY * scale,
    );
  }

  function rebuildGraph() {
    const app = appRef.current;
    const scene = sceneRef.current;
    const edgeLayer = edgeLayerRef.current;
    const nodeLayer = nodeLayerRef.current;
    const labelLayer = labelLayerRef.current;
    if (!app || !scene || !edgeLayer || !nodeLayer || !labelLayer) return;

    if (tickerHandlerRef.current) {
      app.ticker.remove(tickerHandlerRef.current);
      tickerHandlerRef.current = null;
    }
    forceLayoutRef.current?.simulation.stop();

    edgeLayer.removeChildren().forEach((child) => child.destroy());
    nodeLayer.removeChildren().forEach((child) => child.destroy());
    labelLayer.removeChildren().forEach((child) => child.destroy());
    nodeViewsRef.current.clear();
    edgeViewsRef.current.clear();

    const safeNodes = (data.nodes || []).map((node) => ({
      ...node,
      id: node.id || "",
      label: node.label || node.id || "",
      title: node.title || "",
      group: node.group || "default",
    }));

    const safeEdges = (data.edges || []).map((edge, index) => ({
      ...edge,
      id: `edge-${index}`,
      source: String((edge as any).source || ""),
      target: String((edge as any).target || ""),
    }));

    if (safeNodes.length === 0) return;

    const layout = createForceLayout(
      safeNodes,
      safeEdges,
      sizeRef.current.width,
      sizeRef.current.height,
    );
    forceLayoutRef.current = layout;

    for (const edge of safeEdges) {
      if (!layout.nodeById.has(edge.source) || !layout.nodeById.has(edge.target)) continue;
      const line = new Graphics();
      line.zIndex = 1;
      edgeLayer.addChild(line);
      edgeViewsRef.current.set(edge.id, {
        id: edge.id,
        sourceId: edge.source,
        targetId: edge.target,
        line,
      });
    }

    for (const node of safeNodes) {
      const forceNode = layout.nodeById.get(node.id);
      if (!forceNode) continue;
      const nodeView = createNodeView(node, forceNode);
      nodeViewsRef.current.set(node.id, nodeView);
      nodeLayer.addChild(nodeView.root);
      labelLayer.addChild(nodeView.label);
    }

    tickerHandlerRef.current = () => {
      layout.simulation.tick();
      renderGraph();
      const simulation = layout.simulation;
      if (simulation.alpha() <= simulation.alphaMin()) {
        simulation.alpha(0.03);
      }
    };
    app.ticker.add(tickerHandlerRef.current);
    renderGraph();
  }

  function createNodeView(node: GraphNode, forceNode: ForceNode): PixiNodeView {
    const radius = getNodeRadius(node);
    const root = new Container();
    const body = new Graphics();
    const color = colorToNumber(nodeColor(node));

    body.circle(0, 0, radius).fill({ color, alpha: 0.92 });
    body.circle(0, 0, radius + 4).stroke({ color: strokeColor, width: 1.5, alpha: 0.6 });

    const displayLabel = truncateLabel(node.label || node.id, 14);
    const label = new Text({
      text: displayLabel,
      anchor: { x: 0.5, y: 0 },
      style: {
        fontFamily: "Inter, system-ui, sans-serif",
        fontSize: 11,
        fontWeight: "600",
        fill: textColor,
        align: "center",
      },
    });
    label.visible = true;
    label.alpha = 0.92;

    root.addChild(body);
    root.eventMode = "dynamic";
    root.cursor = "grab";
    root.hitArea = { contains: (x: number, y: number) => Math.hypot(x, y) <= Math.max(18, radius + 8) } as any;

    root.on("pointerdown", (event: FederatedPointerEvent) => {
      event.stopPropagation();
      draggingNodeIdRef.current = node.id;
      nodePointerStartRef.current = { x: event.global.x, y: event.global.y };
      didMoveDraggedNodeRef.current = false;
    });
    root.on("pointerover", () => {
      body.scale.set(1.15);
      label.scale.set(1.08);
      label.alpha = 1;
    });
    root.on("pointerout", () => {
      body.scale.set(1);
      label.scale.set(1);
      label.alpha = 0.92;
    });
    root.on("pointerup", () => {
      if (draggingNodeIdRef.current === node.id && !didMoveDraggedNodeRef.current) {
        onNodeClick?.(node);
      }
    });

    return { node, forceNode, root, body, label };
  }

  function truncateLabel(label: string, maxLength: number): string {
    if (label.length <= maxLength) return label;
    return label.slice(0, maxLength - 1) + "…";
  }

  function renderGraph() {
    const layout = forceLayoutRef.current;
    if (!layout) return;

    for (const edgeView of edgeViewsRef.current.values()) {
      const source = layout.nodeById.get(edgeView.sourceId);
      const target = layout.nodeById.get(edgeView.targetId);
      if (!source || !target) continue;
      const sx = typeof source.x === "number" ? source.x : 0;
      const sy = typeof source.y === "number" ? source.y : 0;
      const tx = typeof target.x === "number" ? target.x : 0;
      const ty = typeof target.y === "number" ? target.y : 0;
      edgeView.line.clear();
      edgeView.line.moveTo(sx, sy).lineTo(tx, ty).stroke({ width: 1.2, color: edgeColor, alpha: 0.5 });
    }

    for (const nodeView of nodeViewsRef.current.values()) {
      const x = typeof nodeView.forceNode.x === "number" ? nodeView.forceNode.x : 0;
      const y = typeof nodeView.forceNode.y === "number" ? nodeView.forceNode.y : 0;
      nodeView.root.position.set(x, y);
      nodeView.label.position.set(x, y + getNodeRadius(nodeView.node) + 10);
    }
  }

  return (
    <div
      ref={containerRef}
      className={cn(
        "cursor-grab bg-card/50 active:cursor-grabbing",
        className
      )}
    />
  );
}
