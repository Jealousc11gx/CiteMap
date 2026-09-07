import { useState, useEffect, lazy, Suspense, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { fetchGraphTeam, fetchGraphPaper } from "@/services/api";
import type { GraphData } from "@/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Search, RotateCcw, Loader2, X, Network, Library } from "lucide-react";
import { useProject } from "@/contexts/ProjectContext";

const PixiGraph = lazy(() =>
  import("@/components/PixiGraph").then((module) => ({ default: module.PixiGraph })),
);

const NODE_COLORS = {
  team: "#365edc", // CiteMap primary
  paper: "#64748b", // slate-500
  default: "#94a3b8", // slate-400
};

function prepareGraphData(data: GraphData | null, searchQuery: string): GraphData | null {
  if (!data) return null;

  const safeData: GraphData = {
    nodes: (data.nodes || []).map((node) => ({
      ...node,
      id: node.id || "",
      label: node.label || node.id || "",
      title: node.title || "",
      group: node.group || "default",
    })),
    edges: (data.edges || []).map((edge) => ({
      ...edge,
      source: String((edge as any).source || ""),
      target: String((edge as any).target || ""),
    })),
  };

  const normalizedQuery = searchQuery.trim().toLowerCase();
  if (!normalizedQuery) return safeData;

  const nodes = safeData.nodes.filter(
    (node) =>
      node.label?.toLowerCase().includes(normalizedQuery) ||
      node.title?.toLowerCase().includes(normalizedQuery),
  );
  const nodeIds = new Set(nodes.map((node) => node.id));

  return {
    nodes,
    edges: safeData.edges.filter(
      (edge) => nodeIds.has(String(edge.source)) && nodeIds.has(String(edge.target)),
    ),
  };
}

function Legend() {
  return (
    <div className="absolute bottom-4 left-4 z-10 rounded-lg border border-border bg-card/95 p-3 shadow-sm backdrop-blur-sm">
      <p className="mb-2 text-xs font-medium text-muted-foreground">图例</p>
      <div className="space-y-1.5">
        <div className="flex items-center gap-2 text-xs">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: NODE_COLORS.team }}
          />
          <span>团队</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: NODE_COLORS.paper }}
          />
          <span>论文</span>
        </div>
      </div>
    </div>
  );
}

export function Graph() {
  const { activeProject } = useProject();
  const navigate = useNavigate();
  const [teamData, setTeamData] = useState<GraphData | null>(null);
  const [paperData, setPaperData] = useState<GraphData | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const filteredTeamData = useMemo(
    () => prepareGraphData(teamData, searchQuery),
    [teamData, searchQuery],
  );
  const filteredPaperData = useMemo(
    () => prepareGraphData(paperData, searchQuery),
    [paperData, searchQuery],
  );

  useEffect(() => {
    if (!activeProject) return;
    let cancelled = false;
    setTeamData(null);
    setPaperData(null);
    setSelectedNode(null);
    setSearchQuery("");
    Promise.all([fetchGraphTeam(activeProject.id), fetchGraphPaper(activeProject.id)]).then(([team, paper]) => {
      if (cancelled) return;
      setTeamData(team);
      setPaperData(paper);
    });
    return () => {
      cancelled = true;
    };
  }, [activeProject?.id]);

  const handleReset = () => {
    setSearchQuery("");
    setSelectedNode(null);
  };

  const getNodeColor = (node: any) => {
    if (node.group === "team") return NODE_COLORS.team;
    if (node.group === "paper") return NODE_COLORS.paper;
    return NODE_COLORS.default;
  };

  const renderGraph = (data: GraphData | null, filteredData: GraphData | null, view: string) => {
    if (!data || !data.nodes || data.nodes.length === 0) {
      return (
        <Card className="border-border/60">
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-muted">
              {view === "team" ? (
                <Network className="h-7 w-7 text-muted-foreground" />
              ) : (
                <Library className="h-7 w-7 text-muted-foreground" />
              )}
            </div>
            <h3 className="mt-4 text-base font-semibold">
              {view === "team" ? "暂无团队数据" : "暂无论文数据"}
            </h3>
            <p className="mt-1 max-w-sm text-xs text-muted-foreground">
              {view === "team"
                ? "请先对论文执行智能标注以生成团队信息。"
                : "请先入库一些论文。"}
            </p>
            <Button
              onClick={() => navigate("/papers")}
              variant="secondary"
              size="sm"
              className="mt-5"
            >
              前往论文管理
            </Button>
          </CardContent>
        </Card>
      );
    }

    return (
      <Card className="flex h-[calc(100vh-14.75rem)] min-h-[440px] flex-col border-border">
        <CardContent className="relative flex flex-1 flex-col p-0">
          <div className="flex items-center gap-2 border-b border-border/60 p-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="搜索节点..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
                aria-label="搜索图谱节点"
              />
            </div>
            <Button variant="outline" size="icon" onClick={handleReset} title="重置" aria-label="重置搜索">
              <RotateCcw className="h-4 w-4" />
            </Button>
          </div>

          <div className="relative min-h-0 flex-1 overflow-hidden rounded-b-lg">
            <Suspense
              fallback={(
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载图引擎...
                </div>
              )}
            >
              <PixiGraph
                data={filteredData!}
                nodeColor={getNodeColor}
                onNodeClick={(node) => setSelectedNode(node)}
                className="h-full w-full rounded-b-lg"
              />
            </Suspense>

            <Legend />

            {selectedNode && (
              <div className="absolute right-3 top-3 z-10 w-72 max-w-[calc(100vw-1.5rem)]">
                <Card className="border-border/60 shadow-sm">
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={selectedNode.group === "team" ? "default" : "secondary"}
                          className={
                            selectedNode.group === "team"
                              ? "bg-primary text-primary-foreground hover:bg-primary/90"
                              : ""
                          }
                        >
                          {selectedNode.group === "team" ? "团队" : "论文"}
                        </Badge>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="-mr-2 -mt-2 h-7 w-7"
                        onClick={() => setSelectedNode(null)}
                        aria-label="关闭节点详情"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                    <h4 className="mt-3 font-medium line-clamp-2">
                      {selectedNode.label || selectedNode.id}
                    </h4>
                    {selectedNode.title && (
                      <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">
                        {selectedNode.title}
                      </p>
                    )}
                    <p className="mt-3 text-xs text-muted-foreground">ID: {selectedNode.id}</p>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="workspace-heading">知识图谱</h1>
        <p className="workspace-description">交互式探索论文与团队关系。</p>
      </div>

      <Tabs defaultValue="team" className="w-full">
        <TabsList>
          <TabsTrigger value="team">团队视图</TabsTrigger>
          <TabsTrigger value="paper">论文视图</TabsTrigger>
        </TabsList>
        <TabsContent value="team" className="mt-4">
          {renderGraph(teamData, filteredTeamData, "team")}
        </TabsContent>
        <TabsContent value="paper" className="mt-4">
          {renderGraph(paperData, filteredPaperData, "paper")}
        </TabsContent>
      </Tabs>
    </div>
  );
}
