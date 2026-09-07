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
import * as PopoverPrimitive from "@radix-ui/react-popover";
import {
  ArrowLeft,
  Building2,
  CalendarDays,
  Check,
  ChevronsUpDown,
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
  syncCitationMetrics,
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
  team: "#315fba",
  paper: "#55779f",
  seed: "#315fba",
  reference: "#66788f",
  citing: "#3f7899",
  default: "#657b96",
};

const YEAR_COLORS = ["#9aaabd", "#829bb8", "#698bb5", "#5078ae", "#315fa8"];

function paperYear(node: GraphNode): number | null {
  const value = Number(node.venue_year || node.published_date?.slice(0, 4));
  return Number.isFinite(value) && value > 0 ? value : null;
}

function interpolateHex(left: string, right: string, amount: number): string {
  const channels = [1, 3, 5].map((index) => {
    const start = Number.parseInt(left.slice(index, index + 2), 16);
    const end = Number.parseInt(right.slice(index, index + 2), 16);
    return Math.round(start + (end - start) * amount).toString(16).padStart(2, "0");
  });
  return `#${channels.join("")}`;
}

function yearColor(node: GraphNode, minYear: number, maxYear: number): string {
  const year = paperYear(node);
  if (year === null || minYear === maxYear) return YEAR_COLORS[2];
  const position = Math.max(0, Math.min(1, (year - minYear) / (maxYear - minYear))) * (YEAR_COLORS.length - 1);
  const index = Math.min(YEAR_COLORS.length - 2, Math.floor(position));
  return interpolateHex(YEAR_COLORS[index], YEAR_COLORS[index + 1], position - index);
}

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

function PaperSeedPicker({
  nodes,
  value,
  open,
  onOpenChange,
  onChange,
}: {
  nodes: GraphNode[];
  value: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChange: (paperId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const selectedPaper = nodes.find((node) => node.id === value);
  const orderedPapers = useMemo(() => [...nodes].sort((left, right) => (
    (right.citation_count || 0) - (left.citation_count || 0)
    || (paperYear(right) || 0) - (paperYear(left) || 0)
    || (right.title || right.label || "").localeCompare(left.title || left.label || "")
  )), [nodes]);
  const filteredPapers = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (!normalizedQuery) return orderedPapers;
    return orderedPapers.filter((node) => searchableText(node).includes(normalizedQuery));
  }, [orderedPapers, query]);

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={(nextOpen) => {
      onOpenChange(nextOpen);
      if (!nextOpen) setQuery("");
    }}>
      <PopoverPrimitive.Trigger asChild>
        <Button variant="outline" size="sm" className="h-8 w-56 min-w-0 justify-between px-2.5 font-normal" aria-label="选择种子论文">
          <span className={selectedPaper ? "truncate" : "text-muted-foreground"}>
            {selectedPaper?.title || selectedPaper?.label || "选择种子论文"}
          </span>
          <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          align="end"
          sideOffset={6}
          className="z-50 w-[420px] overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-md outline-none"
        >
          <div className="border-b border-border p-2">
            <div className="relative">
              <Search className="absolute left-3 top-2 h-4 w-4 text-muted-foreground" />
              <Input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索标题、作者或 venue"
                className="h-8 border-0 bg-muted/70 pl-9 shadow-none focus-visible:ring-1"
                aria-label="搜索种子论文"
              />
            </div>
          </div>
          <div className="max-h-80 overflow-y-auto p-1.5" role="listbox" aria-label="种子论文列表">
            {filteredPapers.length ? filteredPapers.map((paper) => {
              const isSelected = paper.id === value;
              const year = paperYear(paper);
              return (
                <button
                  key={paper.id}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className="flex w-full items-start gap-3 rounded px-2.5 py-2.5 text-left outline-none transition-colors hover:bg-accent focus-visible:bg-accent"
                  onClick={() => onChange(paper.id)}
                >
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 text-sm font-medium leading-5">{paper.title || paper.label}</span>
                    <span className="mt-1 block truncate text-xs text-muted-foreground">
                      {[paper.venue, year, paper.citation_count != null ? `引用 ${paper.citation_count}` : null].filter(Boolean).join(" · ") || "暂无发表信息"}
                    </span>
                  </span>
                  <Check className={`mt-1 h-4 w-4 shrink-0 text-primary ${isSelected ? "opacity-100" : "opacity-0"}`} />
                </button>
              );
            }) : (
              <p className="px-3 py-8 text-center text-sm text-muted-foreground">没有匹配的论文</p>
            )}
          </div>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
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
  onSyncPaper,
  syncingPaperId,
}: {
  node: GraphNode | null;
  edge: GraphEdge | null;
  nodesById: Map<string, GraphNode>;
  onClose: () => void;
  onOpenPaper: (paperId: string) => void;
  onSyncPaper: (paperId: string) => void;
  syncingPaperId: string | null;
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
            <p className="my-1 text-xs text-muted-foreground">{edge.directed ? "引用" : "关联"}</p>
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
              <span className="mt-1.5 block text-xs text-muted-foreground">
                {paper.citation_count != null || paper.reference_count != null
                  ? `引用 ${paper.citation_count ?? 0} · 参考文献 ${paper.reference_count ?? 0}`
                  : "引用数据未同步"}
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
          <Badge variant={isTeam || node!.is_seed ? "default" : "secondary"}>{isTeam ? (node!.team_type === "inferred" ? "推断团队" : "研究团队") : node!.paper_id ? "我的论文" : "外部论文"}</Badge>
          <h2 className="mt-3 text-lg font-semibold leading-6 text-balance">{node!.title || node!.label || node!.id}</h2>
          {node!.description && <p className="mt-2 text-sm leading-6 text-muted-foreground">{node!.description}</p>}
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="关闭节点详情"><X /></Button>
      </div>
      <div className="space-y-5 p-5 text-sm">
        {isTeam ? (
          <div className="divide-y divide-border border-y border-border">
            <div className="flex items-center justify-between py-3"><span className="text-muted-foreground">关联论文</span><strong className="font-mono">{node!.paper_count || 0}</strong></div>
            <div className="flex items-center justify-between py-3"><span className="text-muted-foreground">累计引用</span><strong className="font-mono">{node!.citation_count ?? "未同步"}</strong></div>
            <div className="flex items-center justify-between py-3"><span className="text-muted-foreground">已同步论文</span><strong className="font-mono">{node!.citation_synced_paper_count || 0}/{node!.paper_count || 0}</strong></div>
            <div className="flex items-center justify-between py-3"><span className="text-muted-foreground">核心成员</span><strong className="font-mono">{node!.members?.length || 0}</strong></div>
            <div className="flex items-center justify-between gap-4 py-3"><span className="text-muted-foreground">代表作者</span><strong className="text-right">{node!.representative_author || "未识别"}</strong></div>
            <div className="flex items-center justify-between gap-4 py-3"><span className="text-muted-foreground">最近论文</span><strong className="font-mono text-right">{node!.latest_paper_date || "未知"}</strong></div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {node!.similarity_score !== undefined ? <div><p className="text-xs text-muted-foreground">与种子相似度</p><p className="mt-1 font-mono text-lg font-semibold">{Math.round(node!.similarity_score * 100)}%</p></div> : <div><p className="text-xs text-muted-foreground">直接关系</p><p className="mt-1 font-mono text-lg font-semibold">{node!.degree || 0}</p></div>}
            <div><p className="text-xs text-muted-foreground">引用数</p><p className="mt-1 font-mono text-lg font-semibold">{node!.citation_count ?? "未同步"}</p></div>
            <div><p className="text-xs text-muted-foreground">参考文献</p><p className="mt-1 font-mono text-lg font-semibold">{node!.reference_count ?? "未同步"}</p></div>
            {node!.similarity_score === undefined && node!.weighted_degree !== undefined && <div><p className="text-xs text-muted-foreground">关系强度</p><p className="mt-1 font-mono text-lg font-semibold">{node!.weighted_degree}</p></div>}
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
        {!isTeam && node!.paper_id && (
          <Button className="w-full" variant="outline" size="sm" onClick={() => onSyncPaper(paperId)} disabled={syncingPaperId === paperId}>
            {syncingPaperId === paperId ? <Loader2 className="animate-spin" /> : <RefreshCcw />}
            {node!.citation_synced_at || node!.citation_count != null ? "更新引用数据" : "同步引用数据"}
          </Button>
        )}
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
  const [seedPickerOpen, setSeedPickerOpen] = useState(false);
  const [syncingCitations, setSyncingCitations] = useState(false);
  const [syncingMetrics, setSyncingMetrics] = useState(false);
  const [syncingPaperId, setSyncingPaperId] = useState<string | null>(null);
  const [citationLimit, setCitationLimit] = useState(12);
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
    setCitationData(null);
    setSimilarityData(null);
    setSeedPaperId("");
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
    setSeedPaperId((current) => {
      if (nodes.some((node) => node.id === current)) return current;
      const saved = activeProject ? window.localStorage.getItem(`citemap.graph.seed.${activeProject.id}`) : null;
      return saved && nodes.some((node) => node.id === saved) ? saved : "";
    });
  }, [paperData, activeProject]);

  const selectSeedPaper = (paperId: string) => {
    setSeedPaperId(paperId);
    setCitationData(null);
    setSimilarityData(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    setSeedPickerOpen(false);
    if (activeProject) window.localStorage.setItem(`citemap.graph.seed.${activeProject.id}`, paperId);
  };

  const selectPaperRelationMode = (mode: PaperRelationMode) => {
    setPaperRelationMode(mode);
    setSelectedNode(null);
    setSelectedEdge(null);
    if (mode !== "metadata" && !seedPaperId) setSeedPickerOpen(true);
  };

  const loadPaperRelation = useCallback(async (mode: PaperRelationMode, paperId: string) => {
    if (mode === "metadata" || !paperId) return;
    setLoading(true);
    setError(null);
    try {
      const data = normalizeGraphData(
        mode === "citation" ? await fetchGraphCitation(paperId, citationLimit) : await fetchGraphSimilarity(paperId),
      );
      if (mode === "citation") setCitationData(data);
      else setSimilarityData(data);
      setSelectedNode(data.nodes.find((node) => node.is_seed) || null);
      setSelectedEdge(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError));
    } finally {
      setLoading(false);
    }
  }, [citationLimit]);

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
        fetchGraphCitation(seedPaperId, citationLimit),
        fetchGraphSimilarity(seedPaperId),
        fetchGraphPaper(activeProject?.id),
      ]);
      const normalizedCitation = normalizeGraphData(citation);
      const normalizedSimilarity = normalizeGraphData(similarity);
      setCitationData(normalizedCitation);
      setSimilarityData(normalizedSimilarity);
      setPaperData(normalizeGraphData(paper));
      const activeData = paperRelationMode === "citation" ? normalizedCitation : normalizedSimilarity;
      setSelectedNode(activeData.nodes.find((node) => node.is_seed) || null);
      setSelectedEdge(null);
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : String(syncError));
    } finally {
      setSyncingCitations(false);
    }
  };

  const syncNodeCitations = async (paperId: string) => {
    setSyncingPaperId(paperId);
    setError(null);
    try {
      await syncPaperCitations(paperId);
      await loadGraphs();
      if (view === "paper" && paperRelationMode !== "metadata" && paperId === seedPaperId) {
        await loadPaperRelation(paperRelationMode, paperId);
      }
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : String(syncError));
    } finally {
      setSyncingPaperId(null);
    }
  };

  const syncProjectMetrics = async () => {
    if (!activeProject) return;
    setSyncingMetrics(true);
    setError(null);
    try {
      await syncCitationMetrics(activeProject.id);
      await loadGraphs();
    } catch (syncError) {
      setError(syncError instanceof Error ? syncError.message : String(syncError));
    } finally {
      setSyncingMetrics(false);
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
  const similarityYearRange = useMemo(() => {
    const yearValues = (visibleData?.nodes || []).map(paperYear).filter((year): year is number => year !== null);
    return {
      min: yearValues.length ? Math.min(...yearValues) : new Date().getFullYear(),
      max: yearValues.length ? Math.max(...yearValues) : new Date().getFullYear(),
    };
  }, [visibleData]);
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
    if (!activeProject) return null;
    if (view === "paper" && paperRelationMode !== "metadata" && !seedPaperId) {
      return <Card><CardContent className="flex min-h-[440px] flex-col items-center justify-center text-center"><Search className="h-8 w-8 text-muted-foreground" /><p className="mt-4 text-sm font-medium">选择一篇种子论文</p><p className="mt-1 text-xs text-muted-foreground">引用脉络和相似地图将围绕这篇论文生成。</p><Button size="sm" className="mt-4" onClick={() => setSeedPickerOpen(true)}>选择种子论文</Button></CardContent></Card>;
    }
    if (!rawData) return null;
    if (view === "paper" && paperRelationMode !== "metadata" && rawData.nodes.length === 0) {
      return <Card><CardContent className="flex min-h-[440px] flex-col items-center justify-center text-center"><Quote className="h-8 w-8 text-muted-foreground" /><p className="mt-4 text-sm font-medium">尚未同步这篇论文的引用数据</p><p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">同步后生成真实引用方向、引用数及基于共同参考文献的相似网络。</p><Button size="sm" className="mt-4" onClick={() => void syncCitations()} disabled={syncingCitations}>{syncingCitations ? <Loader2 className="animate-spin" /> : <RefreshCcw />}同步引用数据</Button></CardContent></Card>;
    }
    if (rawData.nodes.length === 0) return <EmptyGraph view={view} onManage={() => navigate("/papers")} />;
    if (!visibleData?.nodes.length) {
      return <Card><CardContent className="flex min-h-[440px] flex-col items-center justify-center text-center"><p className="text-sm font-medium">当前筛选条件没有可显示的节点</p><Button variant="outline" size="sm" className="mt-4" onClick={resetView}>重置筛选</Button></CardContent></Card>;
    }
    return (
      <Card className="flex h-[calc(100vh-13.5rem)] min-h-[500px] flex-col overflow-hidden border-border/70 shadow-sm">
        <div className="flex min-h-0 flex-1">
          <div className="relative min-w-0 flex-1 overflow-hidden bg-card/50">
            <Suspense fallback={<div className="flex h-full items-center justify-center text-sm text-muted-foreground"><Loader2 className="mr-2 h-4 w-4 animate-spin" />正在加载图引擎...</div>}>
              <PixiGraph
                ref={graphRef}
                data={visibleData!}
                nodeColor={(node) => node.is_seed
                  ? NODE_COLORS.seed
                  : paperRelationMode === "similarity" && view === "paper"
                    ? yearColor(node, similarityYearRange.min, similarityYearRange.max)
                  : node.citation_role === "reference"
                    ? NODE_COLORS.reference
                    : node.citation_role === "citing"
                      ? NODE_COLORS.citing
                      : NODE_COLORS[node.group as keyof typeof NODE_COLORS] || NODE_COLORS.default}
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
            <div className="absolute bottom-3 left-3 flex items-center rounded-md bg-background/95 shadow-sm ring-1 ring-foreground/10 backdrop-blur">
              <Button variant="ghost" size="icon-sm" onClick={() => graphRef.current?.zoomOut()} title="缩小" aria-label="缩小图谱"><ZoomOut /></Button>
              <Button variant="ghost" size="icon-sm" onClick={() => graphRef.current?.zoomIn()} title="放大" aria-label="放大图谱"><ZoomIn /></Button>
              <Button variant="ghost" size="icon-sm" onClick={() => graphRef.current?.fitToView()} title="适配视口" aria-label="适配视口"><Focus /></Button>
            </div>
            <div className="absolute left-3 top-3 flex items-center gap-3 rounded-md bg-background/95 px-3 py-2 text-xs text-muted-foreground shadow-sm ring-1 ring-foreground/10 backdrop-blur">
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
                <>
                  <span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded-full bg-primary" />我的论文</span>
                  <span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded-full bg-slate-500" />参考文献</span>
                  <span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded-full bg-sky-600" />引用该文</span>
                  <span>箭头指向被引用论文</span>
                </>
              ) : (
                <>
                  <span className="font-mono">{similarityYearRange.min}</span>
                  <i className="h-2 w-24 rounded-sm" style={{ background: `linear-gradient(90deg, ${YEAR_COLORS.join(", ")})` }} />
                  <span className="font-mono">{similarityYearRange.max}</span>
                  <span>线条越深，相似度越高</span>
                </>
              )}
              <span>{view === "paper" ? "节点大小表示引用数" : "团队累计引用，论文为单篇引用"}</span>
            </div>
            <div className="absolute bottom-3 right-3 rounded-md bg-background/95 px-2.5 py-1.5 text-xs text-muted-foreground shadow-sm ring-1 ring-foreground/10 backdrop-blur">
              节点 {graphStats.nodes} · 关系 {graphStats.edges} · 孤立 {graphStats.isolated}
            </div>
          </div>
          <DetailPanel node={selectedNode} edge={selectedEdge} nodesById={nodesById} onClose={() => { setSelectedNode(null); setSelectedEdge(null); }} onOpenPaper={(id) => navigate(`/papers/${encodeURIComponent(id)}`)} onSyncPaper={(id) => void syncNodeCitations(id)} syncingPaperId={syncingPaperId} />
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

      {(error || projectError) && <ErrorAlert title="图谱加载失败" message={error || projectError || "未知错误"} suggestion={error?.includes("Semantic Scholar") ? "等待限流恢复，或配置 Semantic Scholar API Key 后再同步。" : "检查后端服务后重试。"} onRetry={() => void (error?.includes("Semantic Scholar") ? (view === "team" ? syncProjectMetrics() : syncCitations()) : activeProject ? loadGraphs() : refreshProjects())} />}

      <Tabs value={view} onValueChange={(value) => {
        const nextView = value as GraphView;
        setView(nextView);
        setSelectedNode(null);
        setSelectedEdge(null);
      }} className="w-full">
        <div className="flex min-h-11 items-center gap-2 border-y border-border/70 py-2">
          <TabsList className="h-8 shrink-0"><TabsTrigger className="h-7 px-3 text-xs" value="team"><Users className="mr-1.5 h-3.5 w-3.5" />团队</TabsTrigger><TabsTrigger className="h-7 px-3 text-xs" value="paper"><Library className="mr-1.5 h-3.5 w-3.5" />论文</TabsTrigger></TabsList>
          {view === "paper" && <div className="flex h-8 shrink-0 items-center rounded-md bg-muted/70 p-0.5" aria-label="论文关系模式"><button type="button" title="按共同作者与机构连接收藏论文" className={`h-7 rounded px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${paperRelationMode === "metadata" ? "bg-background font-medium text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`} onClick={() => selectPaperRelationMode("metadata")}><Users className="mr-1 inline h-3.5 w-3.5" />收藏关系</button><button type="button" title="查看直接参考文献与被引论文" className={`h-7 rounded px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${paperRelationMode === "citation" ? "bg-background font-medium text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`} onClick={() => selectPaperRelationMode("citation")}><Quote className="mr-1 inline h-3.5 w-3.5" />引用脉络</button><button type="button" title="按共同参考文献计算论文相似度" className={`h-7 rounded px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${paperRelationMode === "similarity" ? "bg-background font-medium text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`} onClick={() => selectPaperRelationMode("similarity")}><GitFork className="mr-1 inline h-3.5 w-3.5" />相似地图</button></div>}
          <div className="ml-auto flex min-w-0 items-center justify-end gap-2">
            {view === "team" && <Button variant="ghost" size="sm" className="h-8" title="批量更新项目论文的引用数与参考文献数" onClick={() => void syncProjectMetrics()} disabled={syncingMetrics}>{syncingMetrics ? <Loader2 className="animate-spin" /> : <Quote />}更新引用指标</Button>}
            {view === "paper" && paperRelationMode !== "metadata" && <PaperSeedPicker nodes={paperData?.nodes || []} value={seedPaperId} open={seedPickerOpen} onOpenChange={setSeedPickerOpen} onChange={selectSeedPaper} />}
            {view === "paper" && paperRelationMode !== "metadata" && <Button variant="ghost" size="sm" className="h-8" title="从 Semantic Scholar 更新引用数据" onClick={() => void syncCitations()} disabled={!seedPaperId || syncingCitations}>{syncingCitations ? <Loader2 className="animate-spin" /> : <RefreshCcw />}同步</Button>}
            {view === "paper" && paperRelationMode === "citation" && <select className="h-8 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={citationLimit} onChange={(event) => setCitationLimit(Number(event.target.value))} aria-label="引用节点数量"><option value={8}>每侧 8 篇</option><option value={12}>每侧 12 篇</option><option value={20}>每侧 20 篇</option><option value={30}>每侧 30 篇</option></select>}
            <div className="relative w-48"><Search className="absolute left-3 top-2 h-4 w-4 text-muted-foreground" /><Input placeholder="搜索图谱节点..." value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} className="h-8 pl-9 pr-14" aria-label="搜索图谱节点" />{searchQuery && <span className="absolute right-2 top-2 text-xs tabular-nums text-muted-foreground">{matchedNodeIds.size} 项</span>}</div>
            {view === "paper" && paperRelationMode === "metadata" && <select className="h-8 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={yearFilter} onChange={(event) => setYearFilter(event.target.value)} aria-label="按年份筛选"><option value="all">全部年份</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select>}
            {view === "paper" && paperRelationMode === "metadata" && <select className="h-8 max-w-40 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} aria-label="按领域筛选"><option value="all">全部领域</option>{categories.map((category) => <option key={category} value={category}>{category}</option>)}</select>}
            {view === "paper" && paperRelationMode === "metadata" && <div className="flex h-8 shrink-0 items-center rounded-md border border-input bg-background p-0.5" aria-label="关系类型筛选"><button type="button" className={`h-6 whitespace-nowrap rounded px-2 text-xs ${authorRelations ? "bg-secondary text-foreground" : "text-muted-foreground"}`} onClick={() => setAuthorRelations((value) => !value)} aria-pressed={authorRelations}>作者</button><button type="button" className={`h-6 whitespace-nowrap rounded px-2 text-xs ${institutionRelations ? "bg-secondary text-foreground" : "text-muted-foreground"}`} onClick={() => setInstitutionRelations((value) => !value)} aria-pressed={institutionRelations}>机构</button><button type="button" className={`h-6 whitespace-nowrap rounded px-2 text-xs ${showIsolatedNodes ? "bg-secondary text-foreground" : "text-muted-foreground"}`} onClick={() => setShowIsolatedNodes((value) => !value)} aria-pressed={showIsolatedNodes}>孤立节点</button></div>}
            <Button variant="outline" size="icon-sm" onClick={resetView} title="重置图谱" aria-label="重置图谱"><RotateCcw /></Button>
          </div>
        </div>
        <TabsContent value="team" className="mt-3">{view === "team" && renderContent()}</TabsContent>
        <TabsContent value="paper" className="mt-3">{view === "paper" && renderContent()}</TabsContent>
      </Tabs>
    </div>
  );
}
