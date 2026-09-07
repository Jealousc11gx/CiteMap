import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
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
  halo: Graphics;
  label: Text;
}

interface PixiEdgeView {
  id: string;
  sourceId: string;
  targetId: string;
  edge: GraphEdge;
  line: Graphics;
}

interface ForceNode extends SimulationNodeDatum {
  id: string;
  size: number;
  linked: boolean;
  columnX: number;
  rowY: number;
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
  onEdgeClick?: (edge: GraphEdge) => void;
  onBackgroundClick?: () => void;
  matchedNodeIds?: Set<string>;
  focusedNodeIds?: Set<string>;
  selectedNodeId?: string | null;
  selectedEdgeKey?: string | null;
  className?: string;
}

export interface PixiGraphHandle {
  fitToView: () => void;
  resetLayout: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
}

function colorToNumber(color: string): number {
  return Number.parseInt(color.replace("#", ""), 16);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function getNodeRadius(node: GraphNode): number {
  const base = node.group === "team" ? 32 : node.is_seed ? 22 : 15;
  if (node.citation_count !== undefined && node.citation_count !== null) {
    return base + Math.min(10, Math.log10(node.citation_count + 1) * 2.8);
  }
  const weightedDegree = Math.max(0, node.weighted_degree || node.degree || 0);
  return base + Math.min(node.group === "team" ? 10 : 5, Math.log2(weightedDegree + 1) * 2.2);
}

export function getEdgeKey(edge: Pick<GraphEdge, "source" | "target" | "directed">): string {
  if (edge.directed) return `${String(edge.source)}->${String(edge.target)}`;
  return [String(edge.source), String(edge.target)].sort().join("::");
}

function getRelationColor(edge: GraphEdge, isDark: boolean): number {
  const types = edge.relation_types || [];
  if (types.includes("citation")) return isDark ? 0x38bdf8 : 0x0284c7;
  if (types.includes("similarity")) return isDark ? 0x2dd4bf : 0x0f766e;
  if (types.includes("collaboration")) return isDark ? 0x60a5fa : 0x2563eb;
  if (types.includes("produced")) return isDark ? 0x64748b : 0x94a3b8;
  if (types.includes("author") && types.includes("institution")) return isDark ? 0x818cf8 : 0x4f46e5;
  if (types.includes("institution")) return isDark ? 0x2dd4bf : 0x0f766e;
  if (types.includes("paper")) return isDark ? 0x818cf8 : 0x365edc;
  return isDark ? 0x64748b : 0x94a3b8;
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
  const linkedNodeIds = new Set(
    edges.flatMap((edge) => [String(edge.source), String(edge.target)]),
  );
  const isCitationLayout = nodes.some((node) => Boolean(node.citation_role));
  const roleCounts = {
    reference: nodes.filter((node) => node.citation_role === "reference").length,
    citing: nodes.filter((node) => node.citation_role === "citing").length,
  };
  const roleIndexes = { reference: 0, citing: 0 };
  const columnDistance = Math.max(145, Math.min(240, width * 0.22));
  const forceNodes: ForceNode[] = nodes.map((node, index) => {
    const position = isCitationLayout && node.citation_role
      ? (() => {
          if (node.citation_role === "seed") return { x: 0, y: 0 };
          const role = node.citation_role;
          const count = roleCounts[role];
          const roleIndex = roleIndexes[role]++;
          const spacing = Math.min(58, Math.max(34, (height * 0.72) / Math.max(count, 1)));
          return {
            x: role === "reference" ? -columnDistance : columnDistance,
            y: (roleIndex - (count - 1) / 2) * spacing,
          };
        })()
      : getInitialPosition(index, nodes.length, width, height);
    return {
      id: node.id,
      size: getNodeRadius(node),
      linked: linkedNodeIds.has(node.id),
      columnX: node.citation_role === "reference" ? -columnDistance : node.citation_role === "citing" ? columnDistance : 0,
      rowY: position.y,
      ...position,
    };
  });

  const nodeById = new Map(forceNodes.map((n) => [n.id, n]));
  const forceLinks: ForceLink[] = edges
    .filter((edge) => nodeById.has(String(edge.source)) && nodeById.has(String(edge.target)))
    .map((edge, index) => ({
      id: `edge-${index}`,
      source: String(edge.source),
      target: String(edge.target),
    }));

  const nodeCount = forceNodes.length;
  const linkDistance = isCitationLayout ? columnDistance : nodeCount <= 18 ? 120 : nodeCount <= 48 ? 90 : 70;
  const chargeRange = Math.min(700, Math.max(width, height) * 0.8);
  const linkedCharge = nodeCount <= 24 ? -190 : nodeCount <= 80 ? -140 : -100;

  const simulation = forceSimulation<ForceNode>(forceNodes)
    .force(
      "link",
      forceLink<ForceNode, ForceLink>(forceLinks)
        .id((d) => d.id)
        .distance(linkDistance)
        .strength(isCitationLayout ? 0.18 : 0.5),
    )
    .force(
      "charge",
      forceManyBody<ForceNode>()
        .distanceMin(1)
        .distanceMax(chargeRange)
        .theta(0.5)
        .strength((node) => isCitationLayout ? -70 : node.linked ? linkedCharge : linkedCharge * 0.28),
    )
    .force(
      "collision",
      forceCollide<ForceNode>()
        .radius((d) => Math.max(30, d.size + 12))
        .iterations(2),
    )
    .force("x", forceX<ForceNode>((node) => node.columnX).strength(isCitationLayout ? 0.42 : 0.075))
    .force("y", forceY<ForceNode>((node) => isCitationLayout ? node.rowY : 0).strength(isCitationLayout ? 0.38 : 0.075))
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

export const PixiGraph = forwardRef<PixiGraphHandle, PixiGraphProps>(function PixiGraph({
  data,
  nodeColor,
  onNodeClick,
  onEdgeClick,
  onBackgroundClick,
  matchedNodeIds,
  focusedNodeIds,
  selectedNodeId,
  selectedEdgeKey,
  className,
}, ref) {
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

  useEffect(() => {
    const host = containerRef.current;
    if (!host) return;

    let cancelled = false;

    async function init(hostElement: HTMLDivElement) {
      const app = new Application();
      await app.init({
        width: hostElement.clientWidth,
        height: hostElement.clientHeight,
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
      hostElement.appendChild(app.canvas);
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
        width: hostElement.clientWidth,
        height: hostElement.clientHeight,
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
            if (!didMoveDraggedNodeRef.current && Math.hypot(dx, dy) <= 6) return;
            didMoveDraggedNodeRef.current = true;
          }
          const local = event.getLocalPosition(scene);
          node.fx = local.x;
          node.fy = local.y;
          forceLayoutRef.current.simulation.alphaTarget(0.2).alpha(0.35);
          startTicker();
          return;
        }

        if (!isPanningRef.current || !panStartRef.current || !sceneStartRef.current) return;
        scene.position.set(
          sceneStartRef.current.x + event.global.x - panStartRef.current.x,
          sceneStartRef.current.y + event.global.y - panStartRef.current.y,
        );
      };

      const endPointerAction = () => {
        if (draggingNodeIdRef.current && forceLayoutRef.current && didMoveDraggedNodeRef.current) {
          const node = forceLayoutRef.current.nodeById.get(draggingNodeIdRef.current);
          if (node) {
            node.fx = undefined;
            node.fy = undefined;
          }
          forceLayoutRef.current.simulation.alphaTarget(0);
          startTicker();
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
      app.stage.on("pointertap", (event: FederatedPointerEvent) => {
        if (event.target === app.stage) onBackgroundClick?.();
      });
      app.stage.on("globalpointermove", handleStagePointerMove);
      app.stage.on("globalpointerup", endPointerAction);
      app.stage.on("globalpointerupoutside", endPointerAction);
      window.addEventListener("pointerup", endPointerAction);
      window.addEventListener("blur", endPointerAction);
      const canvas = app.canvas;

      return () => {
        canvas.removeEventListener("wheel", handleWheel);
        window.removeEventListener("pointerup", endPointerAction);
        window.removeEventListener("blur", endPointerAction);
        app.destroy({ removeView: true }, { children: true });
        if (appRef.current === app) {
          appRef.current = null;
          sceneRef.current = null;
          edgeLayerRef.current = null;
          nodeLayerRef.current = null;
          labelLayerRef.current = null;
        }
      };
    }

    const cleanupPromise = init(host);

    return () => {
      cancelled = true;
      cleanupPromise.then((cleanup) => cleanup?.());
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
      fitToView();
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    renderGraph();
  }, [matchedNodeIds, focusedNodeIds, selectedNodeId, selectedEdgeKey]);

  useImperativeHandle(ref, () => ({
    fitToView,
    resetLayout: rebuildGraph,
    zoomIn: () => zoomAtCenter(1.25),
    zoomOut: () => zoomAtCenter(0.8),
  }));

  function zoomAtCenter(factor: number) {
    zoomAround(factor, {
      x: sizeRef.current.width / 2,
      y: sizeRef.current.height / 2,
    });
  }

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

    const padding = data.nodes.some((node) => Boolean(node.citation_role)) ? 44 : 80;
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

    // d3-force 支持 stop 后手动 tick，静态图无需永久运行渲染循环。
    layout.simulation.tick(safeNodes.length > 400 ? 120 : 240);

    for (const edge of safeEdges) {
      if (!layout.nodeById.has(edge.source) || !layout.nodeById.has(edge.target)) continue;
      const line = new Graphics();
      line.zIndex = 1;
      line.eventMode = "dynamic";
      line.cursor = "pointer";
      line.on("pointerdown", (event: FederatedPointerEvent) => {
        event.stopPropagation();
        isPanningRef.current = false;
      });
      line.on("pointerup", () => onEdgeClick?.(edge));
      edgeLayer.addChild(line);
      edgeViewsRef.current.set(edge.id, {
        id: edge.id,
        sourceId: edge.source,
        targetId: edge.target,
        edge,
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

    renderGraph();
    fitToView();
  }

  function startTicker() {
    const app = appRef.current;
    const layout = forceLayoutRef.current;
    if (!app || !layout || tickerHandlerRef.current) return;

    tickerHandlerRef.current = () => {
      layout.simulation.tick();
      renderGraph();
      if (layout.simulation.alpha() <= layout.simulation.alphaMin()) {
        if (tickerHandlerRef.current) app.ticker.remove(tickerHandlerRef.current);
        tickerHandlerRef.current = null;
      }
    };
    app.ticker.add(tickerHandlerRef.current);
  }

  function createNodeView(node: GraphNode, forceNode: ForceNode): PixiNodeView {
    const radius = getNodeRadius(node);
    const root = new Container();
    const halo = new Graphics();
    const body = new Graphics();
    const isTeam = node.group === "team";
    const isSeed = Boolean(node.is_seed);
    const isCitationNode = Boolean(node.citation_role);
    const color = isTeam
      ? colorToNumber(nodeColor(node))
      : isSeed || isCitationNode ? colorToNumber(nodeColor(node))
      : isDark ? 0x1e293b : 0xffffff;

    halo.circle(0, 0, radius + 7).stroke({ color: isDark ? 0x93c5fd : 0x1d4ed8, width: 3, alpha: 0.95 });
    halo.visible = false;
    body.circle(0, 0, radius).fill({ color, alpha: isTeam || isSeed ? 0.96 : isCitationNode ? 0.12 : 1 });
    body.circle(0, 0, radius).stroke({ color: isTeam || isSeed || isCitationNode ? color : strokeColor, width: isTeam || isSeed ? 2 : 1.5, alpha: 0.9 });
    if (isTeam) body.circle(0, 0, radius + 5).stroke({ color, width: 1.5, alpha: 0.2 });
    if (isSeed) body.circle(0, 0, radius + 6).stroke({ color, width: 2, alpha: 0.28 });

    const displayLabel = truncateLabel(node.label || node.id, isTeam ? 22 : 18);
    const label = new Text({
      text: displayLabel,
      anchor: {
        x: node.citation_role === "reference" ? 1 : node.citation_role === "citing" ? 0 : 0.5,
        y: isTeam ? 0.5 : node.citation_role && node.citation_role !== "seed" ? 0.5 : 0,
      },
      style: {
        fontFamily: "Inter, system-ui, sans-serif",
        fontSize: isTeam ? 10.5 : node.citation_role ? 11.5 : 11,
        fontWeight: "600",
        fill: isTeam ? 0xffffff : textColor,
        align: "center",
        wordWrap: isTeam,
        breakWords: isTeam,
        wordWrapWidth: isTeam ? radius * 1.55 : 180,
        lineHeight: isTeam ? 14 : 15,
      },
    });
    label.visible = true;
    label.alpha = 0.92;
    label.eventMode = "none";

    root.addChild(halo, body);
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
      label.visible = true;
    });
    root.on("pointerout", () => {
      body.scale.set(1);
      label.scale.set(1);
      label.alpha = 0.92;
      renderGraph();
    });
    root.on("pointerup", () => {
      if (draggingNodeIdRef.current === node.id && !didMoveDraggedNodeRef.current) {
        onNodeClick?.(node);
      }
    });

    return { node, forceNode, root, body, halo, label };
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
      const edgeKey = getEdgeKey(edgeView.edge);
      const isSelected = selectedEdgeKey === edgeKey;
      const isFocused = !focusedNodeIds || (
        focusedNodeIds.has(edgeView.sourceId) && focusedNodeIds.has(edgeView.targetId)
      );
      const isMatched = !matchedNodeIds?.size || (
        matchedNodeIds.has(edgeView.sourceId) || matchedNodeIds.has(edgeView.targetId)
      );
      const alpha = isSelected ? 0.95 : isFocused && isMatched ? 0.55 : 0.09;
      const width = isSelected
        ? 3
        : Math.min(2.6, 1 + Math.log2((edgeView.edge.weight || 1) + 1) * 0.45);
      const relationColor = getRelationColor(edgeView.edge, isDark);
      edgeView.line.clear();
      edgeView.line.moveTo(sx, sy).lineTo(tx, ty).stroke({ width: 12, color: relationColor, alpha: 0.001 });
      edgeView.line.moveTo(sx, sy).lineTo(tx, ty).stroke({ width, color: relationColor, alpha });
      if (edgeView.edge.directed) {
        const dx = tx - sx;
        const dy = ty - sy;
        const length = Math.hypot(dx, dy) || 1;
        const ux = dx / length;
        const uy = dy / length;
        const targetView = nodeViewsRef.current.get(edgeView.targetId);
        const tipOffset = targetView ? getNodeRadius(targetView.node) + 3 : 18;
        const tipX = tx - ux * tipOffset;
        const tipY = ty - uy * tipOffset;
        const wing = 8;
        const spread = 4.5;
        edgeView.line
          .moveTo(tipX, tipY)
          .lineTo(tipX - ux * wing - uy * spread, tipY - uy * wing + ux * spread)
          .moveTo(tipX, tipY)
          .lineTo(tipX - ux * wing + uy * spread, tipY - uy * wing - ux * spread)
          .stroke({ width, color: relationColor, alpha });
      }
    }

    const occupiedLabelRects: Array<{ left: number; top: number; right: number; bottom: number }> = [];
    const orderedNodeViews = Array.from(nodeViewsRef.current.values()).sort(
      (a, b) => Number(Boolean(b.node.is_seed)) - Number(Boolean(a.node.is_seed))
        || (b.node.similarity_score || 0) - (a.node.similarity_score || 0)
        || (b.node.citation_count || 0) - (a.node.citation_count || 0)
        || (b.node.weighted_degree || b.node.degree || 0) - (a.node.weighted_degree || a.node.degree || 0),
    );
    const labelBudget = orderedNodeViews.length <= 18 ? orderedNodeViews.length : 12;
    const citationLabelIds = new Set<string>();
    if (orderedNodeViews.some((view) => Boolean(view.node.citation_role))) {
      for (const role of ["reference", "citing"] as const) {
        orderedNodeViews
          .filter((view) => view.node.citation_role === role)
          .slice(0, 6)
          .forEach((view) => citationLabelIds.add(view.node.id));
      }
    }
    for (const [nodeIndex, nodeView] of orderedNodeViews.entries()) {
      const x = typeof nodeView.forceNode.x === "number" ? nodeView.forceNode.x : 0;
      const y = typeof nodeView.forceNode.y === "number" ? nodeView.forceNode.y : 0;
      nodeView.root.position.set(x, y);
      const isTeam = nodeView.node.group === "team";
      const nodeRadius = getNodeRadius(nodeView.node);
      nodeView.label.position.set(
        nodeView.node.citation_role === "reference" ? x - nodeRadius - 8 : nodeView.node.citation_role === "citing" ? x + nodeRadius + 8 : x,
        isTeam || (nodeView.node.citation_role && nodeView.node.citation_role !== "seed") ? y : y + nodeRadius + 10,
      );
      const matchesSearch = !matchedNodeIds?.size || matchedNodeIds.has(nodeView.node.id);
      const isFocused = !focusedNodeIds || focusedNodeIds.has(nodeView.node.id);
      nodeView.root.alpha = matchesSearch && isFocused ? 1 : matchesSearch || isFocused ? 0.56 : 0.16;
      nodeView.label.alpha = matchesSearch && isFocused ? 0.95 : matchesSearch || isFocused ? 0.52 : 0.16;
      if (selectedNodeId === nodeView.node.id) {
        nodeView.label.alpha = 1;
      }
      nodeView.root.scale.set(1);
      nodeView.halo.visible = selectedNodeId === nodeView.node.id;

      const isRequiredLabel = isTeam || Boolean(nodeView.node.is_seed) || citationLabelIds.has(nodeView.node.id) || selectedNodeId === nodeView.node.id || Boolean(matchedNodeIds?.has(nodeView.node.id));
      const rect = {
        left: x - nodeView.label.width / 2 - 3,
        top: isTeam || (nodeView.node.citation_role && nodeView.node.citation_role !== "seed") ? y - nodeView.label.height / 2 - 3 : y + nodeRadius + 7,
        right: x + nodeView.label.width / 2 + 3,
        bottom: isTeam || (nodeView.node.citation_role && nodeView.node.citation_role !== "seed") ? y + nodeView.label.height / 2 + 3 : y + nodeRadius + nodeView.label.height + 13,
      };
      const overlaps = occupiedLabelRects.some((placed) => !(
        rect.right < placed.left || rect.left > placed.right || rect.bottom < placed.top || rect.top > placed.bottom
      ));
      nodeView.label.visible = isRequiredLabel || (!nodeView.node.citation_role && nodeIndex < labelBudget && !overlaps);
      if (nodeView.label.visible) occupiedLabelRects.push(rect);
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
});
