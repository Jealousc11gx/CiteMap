import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Building2,
  CalendarDays,
  ExternalLink,
  FileText,
  Focus,
  Library,
  Loader2,
  Network,
  GitFork,
  Quote,
  RefreshCcw,
  RotateCcw,
  Search,
  Users,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorAlert } from "@/components/ErrorAlert";
import { useProject } from "@/contexts/ProjectContext";
import {
  fetchGraphCitation,
  fetchGraphPaper,
  fetchGraphSimilarity,
  fetchGraphTeamEgo,
  syncPaperCitations,
} from "@/services/api";
import type { GraphData, GraphEdge, GraphNode } from "@/types";
import type { PixiGraphHandle } from "@/components/PixiGraph";

const PixiGraph = lazy(() =>
  import("@/components/PixiGraph").then((module) => ({ default: module.PixiGraph })),
);

type GraphView = "team" | "paper";
type PaperRelationMode = "metadata" | "citation" | "similarity";

const NODE_COLORS = {
  team: "#2563eb",
  paper: "#64748b",
  seed: "#2563eb",
  default: "#94a3b8",
};

function normalizeGraphData(data: GraphData): GraphData {
  return {
    nodes: (data.nodes || []).map((node) => ({
      ...node,
      id: String(node.id || ""),
      label: node.label || node.id || "",
      title: node.title || "",
      group: node.group || "default",
    })),
    edges: (data.edges || []).map((edge) => ({
      ...edge,
      source: String(edge.source || ""),
      target: String(edge.target || ""),
    })),
  };
}

function searchableText(node: GraphNode): string {
  return [
    node.label,
    node.title,
    node.categories,
    node.venue,
    node.core_contribution,
    node.description,
    node.institution,
    node.representative_author,
    ...(node.authors || []),
    ...(node.institutions || []),
    ...(node.members || []),
    ...(node.papers || []).map((paper) => paper.title),
  ].filter(Boolean).join(" ").toLocaleLowerCase();
}

function categoriesOf(node: GraphNode): string[] {
  return (node.categories || "").split(/[\s,]+/).map((item) => item.trim()).filter(Boolean);
}

function edgeKey(edge: Pick<GraphEdge, "source" | "target" | "directed">): string {
  return edge.directed
    ? `${String(edge.source)}->${String(edge.target)}`
    : [String(edge.source), String(edge.target)].sort().join("::");
}

function EmptyGraph({ view, onManage }: { view: GraphView; onManage: () => void }) {
  return (
    <Card className="border-border/60">
      <CardContent className="flex min-h-[360px] flex-col items-center justify-center text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-muted">
          {view === "team" ? <Network className="h-7 w-7 text-muted-foreground" /> : <Library className="h-7 w-7 text-muted-foreground" />}
        </div>
        <h3 className="mt-4 text-base font-semibold">
          {view === "team" ? "暂无团队数据" : "暂无论文数据"}
        </h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          {view === "team" ? "先对论文执行智能标注，生成团队与机构关系。" : "先向当前项目添加论文。"}
        </p>
        <Button onClick={onManage} variant="secondary" size="sm" className="mt-5">
          前往论文管理
        </Button>
      </CardContent>
    </Card>
  );
}

function DetailPanel({
  node,
  edge,
  nodesById,
  onClose,
  onOpenPaper,
}: {
  node: GraphNode | null;
  edge: GraphEdge | null;
  nodesById: Map<string, GraphNode>;
  onClose: () => void;
  onOpenPaper: (paperId: string) => void;
}) {
  const [showPaperList, setShowPaperList] = useState(false);

  useEffect(() => {
    setShowPaperList(false);
  }, [node?.id, edge]);

  if (!node && !edge) {
    return (
      <aside className="flex w-[340px] shrink-0 flex-col border-l border-border bg-card" aria-label="图谱详情">
        <div className="border-b border-border px-5 py-4"><h2 className="text-sm font-semibold">节点详情</h2></div>
        <div className="flex flex-1 flex-col items-center justify-center px-8 text-center text-muted-foreground">
          <Network className="h-8 w-8" />
          <p className="mt-3 text-sm font-medium text-foreground">选择一个节点</p>
          <p className="mt-1 text-xs leading-5">查看团队成员、关联论文与关系证据</p>
        </div>
      </aside>
    );
  }

  if (edge) {
    const source = nodesById.get(String(edge.source));
    const target = nodesById.get(String(edge.target));
    return (
      <aside className="w-80 shrink-0 overflow-y-auto border-l border-border bg-card" aria-label="关系详情">
        <div className="flex items-start justify-between border-b border-border p-4">
          <div>
            <Badge variant="secondary">关系</Badge>
            <h2 className="mt-3 text-sm font-semibold leading-5">{source?.label || edge.source}</h2>
            <p className="my-1 text-xs text-muted-foreground">关联</p>
            <h2 className="text-sm font-semibold leading-5">{target?.label || edge.target}</h2>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="关闭关系详情"><X /></Button>
        </div>
        <div className="space-y-5 p-4 text-sm">
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              {edge.similarity !== undefined ? "归一化相似度" : edge.directed ? "关系类型" : "关系强度"}
            </p>
            <p className="mt-1 font-mono text-lg font-semibold">
              {edge.similarity !== undefined ? `${Math.round(edge.similarity * 100)}%` : edge.directed ? "引用" : edge.weight || 1}
            </p>
          </div>
          {edge.shared_references !== undefined && <div><p className="text-xs font-medium text-muted-foreground">共同参考文献</p><p className="mt-1 font-mono text-lg font-semibold">{edge.shared_references}</p></div>}
          {!!edge.shared_authors?.length && (
            <div><p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><Users className="h-3.5 w-3.5" />共享作者</p><p className="mt-2 leading-6">{edge.shared_authors.join("、")}</p></div>
          )}
          {!!edge.shared_institutions?.length && (
            <div><p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><Building2 className="h-3.5 w-3.5" />共享机构</p><p className="mt-2 leading-6">{edge.shared_institutions.join("、")}</p></div>
          )}
          {!!edge.papers?.length && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">共同论文</p>
              <div className="mt-2 divide-y divide-border">
                {edge.papers.map((paper) => (
                  <button key={paper.id} className="w-full py-2 text-left text-sm leading-5 hover:text-primary" onClick={() => onOpenPaper(paper.id)}>{paper.title}</button>
                ))}
              </div>
            </div>
          )}
        </div>
      </aside>
    );
  }

  const isTeam = node!.group === "team";
  const paperId = node!.paper_id || node!.id;

  if (isTeam && showPaperList) {
    return (
      <aside className="w-[340px] shrink-0 overflow-y-auto border-l border-border bg-card" aria-label="关联论文">
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-border bg-card px-4 py-3">
          <Button variant="ghost" size="icon-sm" onClick={() => setShowPaperList(false)} aria-label="返回团队详情"><ArrowLeft /></Button>
          <div className="min-w-0 flex-1"><h2 className="text-sm font-semibold">关联论文</h2><p className="truncate text-xs text-muted-foreground">{node!.title || node!.label}</p></div>
          <span className="font-mono text-xs text-muted-foreground">{node!.papers?.length || 0}</span>
        </div>
        <div className="divide-y divide-border">
          {(node!.papers || []).map((paper) => (
            <button key={paper.id} className="group w-full px-4 py-4 text-left hover:bg-muted/60" onClick={() => onOpenPaper(paper.id)}>
              <span className="block text-sm font-medium leading-5 group-hover:text-primary">{paper.title}</span>
              <span className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                {paper.venue && <strong className="text-primary">{paper.venue} {paper.venue_year || ""}</strong>}
                <span>{paper.date || "日期未知"}</span>
              </span>
            </button>
          ))}
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-[340px] shrink-0 overflow-y-auto border-l border-border bg-card" aria-label="节点详情">
      <div className="flex items-start justify-between border-b border-border p-5">
        <div className="min-w-0 pr-2">
          <Badge variant={isTeam ? "default" : "secondary"}>{isTeam ? (node!.team_type === "inferred" ? "推断团队" : "研究团队") : "论文"}</Badge>
          <h2 className="mt-3 text-lg font-semibold leading-6 text-balance">{node!.title || node!.label || node!.id}</h2>
          {node!.description && <p className="mt-2 text-sm leading-6 text-muted-foreground">{node!.description}</p>}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="关闭节点详情"><X /></Button>
      </div>
      <div className="space-y-5 p-5 text-sm">
        {isTeam ? (
          <div className="divide-y divide-border border-y border-border">
            <div className="flex items-center justify-between py-3"><span className="text-muted-foreground">关联论文</span><strong className="font-mono">{node!.paper_count || 0}</strong></div>
            <div className="flex items-center justify-between py-3"><span className="text-muted-foreground">核心成员</span><strong className="font-mono">{node!.members?.length || 0}</strong></div>
            <div className="flex items-center justify-between gap-4 py-3"><span className="text-muted-foreground">代表作者</span><strong className="text-right">{node!.representative_author || "未识别"}</strong></div>
            <div className="flex items-center justify-between gap-4 py-3"><span className="text-muted-foreground">最近论文</span><strong className="font-mono text-right">{node!.latest_paper_date || "未知"}</strong></div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {node!.similarity_score !== undefined ? <div><p className="text-xs text-muted-foreground">与种子相似度</p><p className="mt-1 font-mono text-lg font-semibold">{Math.round(node!.similarity_score * 100)}%</p></div> : <div><p className="text-xs text-muted-foreground">直接关系</p><p className="mt-1 font-mono text-lg font-semibold">{node!.degree || 0}</p></div>}
            <div><p className="text-xs text-muted-foreground">引用数</p><p className="mt-1 font-mono text-lg font-semibold">{node!.citation_count ?? "未同步"}</p></div>
            <div><p className="text-xs text-muted-foreground">参考文献</p><p className="mt-1 font-mono text-lg font-semibold">{node!.reference_count ?? "未知"}</p></div>
            {node!.weighted_degree !== undefined && <div><p className="text-xs text-muted-foreground">关系强度</p><p className="mt-1 font-mono text-lg font-semibold">{node!.weighted_degree}</p></div>}
          </div>
        )}
        {node!.published_date && <p className="flex items-center gap-2 text-muted-foreground"><CalendarDays className="h-4 w-4" />{node!.published_date}</p>}
        {node!.venue && <div><p className="text-xs font-medium text-muted-foreground">发表 venue</p><p className="mt-1 font-semibold text-primary">{node!.venue} {node!.venue_year || ""}</p></div>}
        {node!.institution && <div><p className="text-xs font-medium text-muted-foreground">主要机构</p><p className="mt-1 leading-6">{node!.institution}</p></div>}
        {!!node!.authors?.length && <div><p className="text-xs font-medium text-muted-foreground">作者</p><p className="mt-1 leading-6">{node!.authors.join("、")}</p></div>}
        {!!node!.institutions?.length && <div><p className="text-xs font-medium text-muted-foreground">机构</p><p className="mt-1 leading-6">{node!.institutions.join("、")}</p></div>}
        {!!node!.members?.length && <div><p className="text-xs font-medium text-muted-foreground">成员</p><p className="mt-1 leading-6">{node!.members.join("、")}</p></div>}
        {node!.core_contribution && <div><p className="text-xs font-medium text-muted-foreground">核心贡献</p><p className="mt-1 leading-6">{node!.core_contribution}</p></div>}
        {isTeam && !!node!.papers?.length && <Button className="w-full" onClick={() => setShowPaperList(true)}><FileText />查看关联论文</Button>}
        {!isTeam && node!.paper_id && <Button className="w-full" size="sm" onClick={() => onOpenPaper(paperId)}><ExternalLink />查看论文详情</Button>}
        {!isTeam && !node!.paper_id && node!.scholar_id && <Button className="w-full" size="sm" variant="outline" onClick={() => window.open(`https://www.semanticscholar.org/paper/${node!.scholar_id}`, "_blank", "noopener,noreferrer")}><ExternalLink />在 Semantic Scholar 查看</Button>}
      </div>
    </aside>
  );
}

export function Graph() {
  const { activeProject, loading: projectLoading, error: projectError, refreshProjects } = useProject();
  const navigate = useNavigate();
  const graphRef = useRef<PixiGraphHandle>(null);
  const [view, setView] = useState<GraphView>("team");
  const [teamData, setTeamData] = useState<GraphData | null>(null);
  const [paperData, setPaperData] = useState<GraphData | null>(null);
  const [citationData, setCitationData] = useState<GraphData | null>(null);
  const [similarityData, setSimilarityData] = useState<GraphData | null>(null);
  const [paperRelationMode, setPaperRelationMode] = useState<PaperRelationMode>("metadata");
  const [seedPaperId, setSeedPaperId] = useState("");
  const [syncingCitations, setSyncingCitations] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [yearFilter, setYearFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [authorRelations, setAuthorRelations] = useState(true);
  const [institutionRelations, setInstitutionRelations] = useState(true);
  const [showIsolatedNodes, setShowIsolatedNodes] = useState(true);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  const loadGraphs = useCallback(async () => {
    if (!activeProject) return;
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    try {
      const [team, paper] = await Promise.all([
        fetchGraphTeamEgo(activeProject.id),
        fetchGraphPaper(activeProject.id),
      ]);
      const normalizedTeam = normalizeGraphData(team);
      setTeamData(normalizedTeam);
      setPaperData(normalizeGraphData(paper));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  useEffect(() => {
    setTeamData(null);
    setPaperData(null);
    setSearchQuery("");
    setYearFilter("all");
    setCategoryFilter("all");
    void loadGraphs();
  }, [loadGraphs]);

  useEffect(() => {
    const nodes = paperData?.nodes || [];
    if (!nodes.length) {
      setSeedPaperId("");
      return;
    }
    if (!nodes.some((node) => node.id === seedPaperId)) setSeedPaperId(nodes[0].id);
  }, [paperData, seedPaperId]);

  const loadPaperRelation = useCallback(async (mode: PaperRelationMode, paperId: string) => {
    if (mode === "metadata" || !paperId) return;
    setLoading(true);
    setError(null);
    try {
      const data = normalizeGraphData(
        mode === "citation" ? await fetchGraphCitation(paperId) : await fetchGraphSimilarity(paperId),
      );
      if (mode === "citation") setCitationData(data);
      else setSimilarityData(data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view === "paper" && paperRelationMode !== "metadata" && seedPaperId) {
      void loadPaperRelation(paperRelationMode, seedPaperId);
    }
  }, [view, paperRelationMode, seedPaperId, loadPaperRelation]);

  const syncCitations = async () => {
    if (!seedPaperId) return;
    setSyncingCitations(true);
    setError(null);
    try {
      await syncPaperCitations(seedPaperId);
      const [citation, similarity, paper] = await Promise.all([
        fetchGraphCitation(seedPaperId),
        fetchGraphSimilarity(seedPaperId),
        fetchGraphPaper(activeProject?.id),
      ]);
      setCitationData(normalizeGraphData(citation));
      setSimilarityData(normalizeGraphData(similarity));
      setPaperData(normalizeGraphData(paper));
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : String(syncError));
    } finally {
      setSyncingCitations(false);
    }
  };

  const rawData = view === "team"
    ? teamData
    : paperRelationMode === "citation"
      ? citationData
      : paperRelationMode === "similarity"
        ? similarityData
        : paperData;
  const years = useMemo(() => Array.from(new Set((paperData?.nodes || []).map((node) => node.published_date?.slice(0, 4)).filter(Boolean) as string[])).sort().reverse(), [paperData]);
  const categories = useMemo(() => Array.from(new Set((paperData?.nodes || []).flatMap(categoriesOf))).sort(), [paperData]);

  const visibleData = useMemo<GraphData | null>(() => {
    if (!rawData) return null;
    let nodes = rawData.nodes.filter((node) => {
      if (view !== "paper" || paperRelationMode !== "metadata") return true;
      if (yearFilter !== "all" && node.published_date?.slice(0, 4) !== yearFilter) return false;
      return categoryFilter === "all" || categoriesOf(node).includes(categoryFilter);
    });
    let nodeIds = new Set(nodes.map((node) => node.id));
    const edges = rawData.edges.filter((edge) => {
      if (!nodeIds.has(String(edge.source)) || !nodeIds.has(String(edge.target))) return false;
      if (view !== "paper" || paperRelationMode !== "metadata") return true;
      const types = edge.relation_types || [];
      return (authorRelations && types.includes("author")) || (institutionRelations && types.includes("institution"));
    });
    if (view === "paper" && paperRelationMode === "metadata" && !showIsolatedNodes) {
      nodeIds = new Set(edges.flatMap((edge) => [String(edge.source), String(edge.target)]));
      nodes = nodes.filter((node) => nodeIds.has(node.id));
    }
    return { nodes, edges };
  }, [rawData, view, paperRelationMode, yearFilter, categoryFilter, authorRelations, institutionRelations, showIsolatedNodes]);

  const nodesById = useMemo(() => new Map((visibleData?.nodes || []).map((node) => [node.id, node])), [visibleData]);
  useEffect(() => {
    if (selectedNode && !nodesById.has(selectedNode.id)) setSelectedNode(null);
    if (selectedEdge && !visibleData?.edges.some((edge) => edgeKey(edge) === edgeKey(selectedEdge))) setSelectedEdge(null);
  }, [nodesById, visibleData, selectedNode, selectedEdge]);
  const matchedNodeIds = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!query) return new Set<string>();
    return new Set((visibleData?.nodes || []).filter((node) => searchableText(node).includes(query)).map((node) => node.id));
  }, [visibleData, searchQuery]);
  const focusedNodeIds = useMemo(() => {
    if (!selectedNode || !visibleData) return undefined;
    const ids = new Set([selectedNode.id]);
    visibleData.edges.forEach((edge) => {
      if (String(edge.source) === selectedNode.id) ids.add(String(edge.target));
      if (String(edge.target) === selectedNode.id) ids.add(String(edge.source));
    });
    return ids;
  }, [selectedNode, visibleData]);

  const resetView = () => {
    setSearchQuery("");
    setYearFilter("all");
    setCategoryFilter("all");
    setAuthorRelations(true);
    setInstitutionRelations(true);
    setShowIsolatedNodes(true);
    setSelectedNode(null);
    setSelectedEdge(null);
    requestAnimationFrame(() => graphRef.current?.resetLayout());
  };

  const selectNode = (node: GraphNode) => {
    setSelectedNode((current) => current?.id === node.id ? null : node);
    setSelectedEdge(null);
  };
  const selectEdge = (edge: GraphEdge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
  };

  const graphStats = {
    nodes: visibleData?.nodes.length || 0,
    edges: visibleData?.edges.length || 0,
    isolated: visibleData ? visibleData.nodes.filter((node) => !visibleData.edges.some((edge) => String(edge.source) === node.id || String(edge.target) === node.id)).length : 0,
  };

  const renderContent = () => {
    if (loading || projectLoading) {
      return <Card><CardContent className="flex min-h-[440px] items-center justify-center text-sm text-muted-foreground"><Loader2 className="mr-2 h-4 w-4 animate-spin" />正在构建图谱...</CardContent></Card>;
    }
    if (!activeProject || !rawData) return null;
    if (view === "paper" && paperRelationMode !== "metadata" && rawData.nodes.length === 0) {
      return <Card><CardContent className="flex min-h-[440px] flex-col items-center justify-center text-center"><Quote className="h-8 w-8 text-muted-foreground" /><p className="mt-4 text-sm font-medium">尚未同步这篇论文的引用数据</p><p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">同步后生成真实引用方向、引用数及基于共同参考文献的相似网络。</p><Button size="sm" className="mt-4" onClick={() => void syncCitations()} disabled={syncingCitations}>{syncingCitations ? <Loader2 className="animate-spin" /> : <RefreshCcw />}同步引用数据</Button></CardContent></Card>;
    }
    if (rawData.nodes.length === 0) return <EmptyGraph view={view} onManage={() => navigate("/papers")} />;
    if (!visibleData?.nodes.length) {
      return <Card><CardContent className="flex min-h-[440px] flex-col items-center justify-center text-center"><p className="text-sm font-medium">当前筛选条件没有可显示的节点</p><Button variant="outline" size="sm" className="mt-4" onClick={resetView}>重置筛选</Button></CardContent></Card>;
    }
    return (
      <Card className="flex h-[calc(100vh-15rem)] min-h-[460px] flex-col overflow-hidden border-border">
        <div className="flex min-h-0 flex-1">
          <div className="relative min-w-0 flex-1 overflow-hidden bg-card/50">
            <Suspense fallback={<div className="flex h-full items-center justify-center text-sm text-muted-foreground"><Loader2 className="mr-2 h-4 w-4 animate-spin" />正在加载图引擎...</div>}>
              <PixiGraph
                ref={graphRef}
                data={visibleData!}
                nodeColor={(node) => node.is_seed ? NODE_COLORS.seed : NODE_COLORS[node.group as keyof typeof NODE_COLORS] || NODE_COLORS.default}
                onNodeClick={selectNode}
                onEdgeClick={selectEdge}
                onBackgroundClick={() => { setSelectedNode(null); setSelectedEdge(null); }}
                matchedNodeIds={matchedNodeIds}
                focusedNodeIds={focusedNodeIds}
                selectedNodeId={selectedNode?.id}
                selectedEdgeKey={selectedEdge ? edgeKey(selectedEdge) : null}
                className="h-full w-full"
              />
            </Suspense>
            <div className="absolute bottom-3 left-3 flex items-center rounded-md border border-border bg-card shadow-sm">
              <Button variant="ghost" size="icon-sm" onClick={() => graphRef.current?.zoomOut()} title="缩小" aria-label="缩小图谱"><ZoomOut /></Button>
              <Button variant="ghost" size="icon-sm" onClick={() => graphRef.current?.zoomIn()} title="放大" aria-label="放大图谱"><ZoomIn /></Button>
              <Button variant="ghost" size="icon-sm" onClick={() => graphRef.current?.fitToView()} title="适配视口" aria-label="适配视口"><Focus /></Button>
            </div>
            <div className="absolute left-3 top-3 flex items-center gap-3 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-muted-foreground shadow-sm">
              {view === "team" ? (
                <>
                  <span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded-full bg-primary" />推断团队</span>
                  <span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded-full border border-slate-300 bg-white dark:bg-slate-800" />关联论文</span>
                </>
              ) : paperRelationMode === "metadata" ? (
                <>
                  <span className="flex items-center gap-1.5"><i className="h-0.5 w-5 bg-slate-400" />共同作者</span>
                  <span className="flex items-center gap-1.5"><i className="h-0.5 w-5 bg-teal-600 dark:bg-teal-400" />共同机构</span>
                  <span className="flex items-center gap-1.5"><i className="h-0.5 w-5 bg-indigo-600 dark:bg-indigo-400" />两者均有</span>
                </>
              ) : paperRelationMode === "citation" ? (
                <><span className="flex items-center gap-1.5"><i className="h-0.5 w-5 bg-sky-600 dark:bg-sky-400" />箭头指向被引用论文</span></>
              ) : (
                <><span className="flex items-center gap-1.5"><i className="h-0.5 w-5 bg-teal-600 dark:bg-teal-400" />共享参考文献相似度</span></>
              )}
              <span>{view === "paper" && paperRelationMode === "similarity" ? "距离越近通常越相似" : view === "paper" ? "节点大小表示引用数" : "节点大小表示关系强度"}</span>
            </div>
            <div className="absolute bottom-3 right-3 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-muted-foreground shadow-sm">
              节点 {graphStats.nodes} · 关系 {graphStats.edges} · 孤立 {graphStats.isolated}
            </div>
          </div>
          <DetailPanel node={selectedNode} edge={selectedEdge} nodesById={nodesById} onClose={() => { setSelectedNode(null); setSelectedEdge(null); }} onOpenPaper={(id) => navigate(`/papers/${encodeURIComponent(id)}`)} />
        </div>
      </Card>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-6">
        <div><h1 className="workspace-heading">知识图谱</h1><p className="workspace-description">探索论文、团队、作者与机构之间的关系。</p></div>
        <Button variant="outline" size="sm" onClick={() => void loadGraphs()} disabled={loading}><RefreshCcw className={loading ? "animate-spin" : ""} />刷新数据</Button>
      </div>

      {(error || projectError) && <ErrorAlert title="图谱加载失败" message={error || projectError || "未知错误"} suggestion={error?.includes("Semantic Scholar") ? "等待限流恢复，或配置 Semantic Scholar API Key 后再同步。" : "检查后端服务后重试。"} onRetry={() => void (error?.includes("Semantic Scholar") ? syncCitations() : activeProject ? loadGraphs() : refreshProjects())} />}

      <Tabs value={view} onValueChange={(value) => {
        const nextView = value as GraphView;
        setView(nextView);
        setSelectedNode(null);
        setSelectedEdge(null);
      }} className="w-full">
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-4">
            <TabsList><TabsTrigger value="team">团队视图</TabsTrigger><TabsTrigger value="paper">论文关系</TabsTrigger></TabsList>
            {view === "paper" && <div className="flex h-8 items-center rounded-md border border-input bg-background p-0.5" aria-label="论文关系模式"><button type="button" className={`h-6 rounded px-2 text-xs ${paperRelationMode === "metadata" ? "bg-secondary text-foreground" : "text-muted-foreground"}`} onClick={() => setPaperRelationMode("metadata")}><Users className="mr-1 inline h-3 w-3" />作者/机构</button><button type="button" className={`h-6 rounded px-2 text-xs ${paperRelationMode === "citation" ? "bg-secondary text-foreground" : "text-muted-foreground"}`} onClick={() => setPaperRelationMode("citation")}><Quote className="mr-1 inline h-3 w-3" />引用网络</button><button type="button" className={`h-6 rounded px-2 text-xs ${paperRelationMode === "similarity" ? "bg-secondary text-foreground" : "text-muted-foreground"}`} onClick={() => setPaperRelationMode("similarity")}><GitFork className="mr-1 inline h-3 w-3" />相似论文</button></div>}
          </div>
          <div className="flex items-center justify-end gap-2">
            {view === "paper" && paperRelationMode !== "metadata" && <select className="h-8 max-w-56 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={seedPaperId} onChange={(event) => { setSeedPaperId(event.target.value); setSelectedNode(null); setSelectedEdge(null); }} aria-label="选择种子论文">{(paperData?.nodes || []).map((node) => <option key={node.id} value={node.id}>{node.title || node.label}</option>)}</select>}
            {view === "paper" && paperRelationMode !== "metadata" && <Button variant="outline" size="sm" className="h-8" onClick={() => void syncCitations()} disabled={!seedPaperId || syncingCitations}>{syncingCitations ? <Loader2 className="animate-spin" /> : <RefreshCcw />}同步引用</Button>}
            <div className="relative w-64"><Search className="absolute left-3 top-2 h-4 w-4 text-muted-foreground" /><Input placeholder="搜索标题、作者、机构..." value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} className="h-8 pl-9 pr-16" aria-label="搜索图谱节点" />{searchQuery && <span className="absolute right-2 top-2 text-xs tabular-nums text-muted-foreground">{matchedNodeIds.size} 项</span>}</div>
            {view === "paper" && paperRelationMode === "metadata" && <select className="h-8 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={yearFilter} onChange={(event) => setYearFilter(event.target.value)} aria-label="按年份筛选"><option value="all">全部年份</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select>}
            {view === "paper" && paperRelationMode === "metadata" && <select className="h-8 max-w-40 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} aria-label="按领域筛选"><option value="all">全部领域</option>{categories.map((category) => <option key={category} value={category}>{category}</option>)}</select>}
            {view === "paper" && paperRelationMode === "metadata" && <div className="flex h-8 shrink-0 items-center rounded-md border border-input bg-background p-0.5" aria-label="关系类型筛选"><button type="button" className={`h-6 whitespace-nowrap rounded px-2 text-xs ${authorRelations ? "bg-secondary text-foreground" : "text-muted-foreground"}`} onClick={() => setAuthorRelations((value) => !value)} aria-pressed={authorRelations}>作者</button><button type="button" className={`h-6 whitespace-nowrap rounded px-2 text-xs ${institutionRelations ? "bg-secondary text-foreground" : "text-muted-foreground"}`} onClick={() => setInstitutionRelations((value) => !value)} aria-pressed={institutionRelations}>机构</button><button type="button" className={`h-6 whitespace-nowrap rounded px-2 text-xs ${showIsolatedNodes ? "bg-secondary text-foreground" : "text-muted-foreground"}`} onClick={() => setShowIsolatedNodes((value) => !value)} aria-pressed={showIsolatedNodes}>孤立节点</button></div>}
            <Button variant="outline" size="icon-sm" onClick={resetView} title="重置图谱" aria-label="重置图谱"><RotateCcw /></Button>
          </div>
        </div>
        <TabsContent value="team" className="mt-2">{view === "team" && renderContent()}</TabsContent>
        <TabsContent value="paper" className="mt-2">{view === "paper" && renderContent()}</TabsContent>
      </Tabs>
    </div>
  );
}
