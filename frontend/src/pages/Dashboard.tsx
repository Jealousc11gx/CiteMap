import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchPapers } from "@/services/api";
import type { Paper } from "@/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import {
  Library,
  Sparkles,
  BookOpen,
  FileText,
  TrendingUp,
  ArrowRight,
  Zap,
  Network,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useProject } from "@/contexts/ProjectContext";

function StatCard({
  label,
  value,
  icon: Icon,
  onClick,
  children,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  onClick: () => void;
  children?: React.ReactNode;
}) {
  return (
    <Card
      className="group cursor-pointer rounded-none border-0 bg-transparent transition-colors hover:bg-muted/55"
      onClick={onClick}
    >
      <CardContent className="flex min-h-24 items-start gap-3 p-4">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-1 font-mono text-2xl font-semibold tracking-tight">{value}</p>
          {children}
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyState({ onAction }: { onAction: () => void }) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-muted">
          <Library className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="mt-4 text-base font-semibold">当前项目还没有论文</h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          前往论文管理，从其他项目导入已有论文或入库新论文。
        </p>
        <Button className="mt-5 gap-2" size="sm" onClick={onAction}>
          <Zap className="h-4 w-4" />
          管理项目论文
        </Button>
      </CardContent>
    </Card>
  );
}

export function Dashboard() {
  const { activeProject } = useProject();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<{
    message: string;
    suggestion?: string;
    onRetry?: () => void;
  } | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!activeProject) return;
    let cancelled = false;
    setLoading(true);
    setPageError(null);
    fetchPapers(undefined, undefined, activeProject.id)
      .then((data) => {
        if (cancelled) return;
        setPapers(data);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setPageError({
          message: "加载仪表盘数据失败",
          suggestion: err instanceof Error ? err.message : String(err),
          onRetry: () => window.location.reload(),
        });
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeProject?.id]);

  const stats = {
    total: papers.length,
    arxiv: papers.filter((p) => p.source === "arxiv").length,
    local: papers.filter((p) => p.source === "local").length,
    annotated: papers.filter((p) => p.tldr && p.core_contribution).length,
    pending: papers.filter((p) => !p.tldr || !p.core_contribution).length,
    withNotes: papers.filter((p) => p.note_edited_at).length,
    withPdf: papers.filter((p) => p.pdf_path).length,
  };

  const annotationRate =
    stats.total > 0 ? Math.round((stats.annotated / stats.total) * 100) : 0;
  const notesRate =
    stats.total > 0 ? Math.round((stats.withNotes / stats.total) * 100) : 0;
  const pdfRate =
    stats.total > 0 ? Math.round((stats.withPdf / stats.total) * 100) : 0;

  const recent = papers.slice(0, 5);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-6">
        <div>
          <h1 className="workspace-heading">{activeProject?.name || "项目"}</h1>
          <p className="workspace-description">论文状态、知识关系、研究笔记集中概览。</p>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => navigate("/papers")}>
          <Library className="h-3.5 w-3.5" />
          管理论文
        </Button>
      </div>

      {pageError && (
        <ErrorAlert
          title="加载失败"
          message={pageError.message}
          suggestion={pageError.suggestion}
          onRetry={pageError.onRetry}
        />
      )}

      {loading ? (
        <div className="grid grid-cols-4 divide-x overflow-hidden rounded-lg border bg-card">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="rounded-none border-0">
              <CardContent className="p-5">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="mt-2 h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : stats.total === 0 ? (
        <EmptyState onAction={() => navigate("/papers")} />
      ) : (
        <>
          {/* Stats Grid */}
          <div className="grid grid-cols-4 divide-x overflow-hidden rounded-lg border bg-card">
            <StatCard
              label="总论文数"
              value={stats.total}
              icon={Library}
              onClick={() => navigate("/papers")}
            />
            <StatCard
              label="已标注"
              value={stats.annotated}
              icon={Sparkles}
              onClick={() => navigate("/papers")}
            >
              <div className="mt-1.5">
                <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>标注率</span>
                  <span className="font-medium text-foreground">{annotationRate}%</span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-500"
                    style={{ width: `${annotationRate}%` }}
                  />
                </div>
              </div>
            </StatCard>
            <StatCard
              label="有笔记"
              value={stats.withNotes}
              icon={BookOpen}
              onClick={() => navigate("/notes")}
            >
              <p className="mt-1 text-[11px] text-muted-foreground">覆盖率 {notesRate}%</p>
            </StatCard>
            <StatCard
              label="有 PDF"
              value={stats.withPdf}
              icon={FileText}
              onClick={() => navigate("/papers")}
            >
              <p className="mt-1 text-[11px] text-muted-foreground">覆盖率 {pdfRate}%</p>
            </StatCard>
          </div>

          {/* Main Content Grid */}
          <div className="grid grid-cols-3 gap-4">
            {/* Library Health */}
            <Card className="col-span-1 border-border/60">
              <CardHeader className="pb-2 pt-4">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  知识库健康度
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 pb-4">
                <div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">论文标注率</span>
                    <span className="font-medium text-foreground">{annotationRate}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-all duration-700"
                      style={{ width: `${annotationRate}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">笔记覆盖率</span>
                    <span className="font-medium text-foreground">{notesRate}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-slate-400 transition-all duration-700 dark:bg-slate-500"
                      style={{ width: `${notesRate}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">PDF 完整率</span>
                    <span className="font-medium text-foreground">{pdfRate}%</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-slate-300 transition-all duration-700 dark:bg-slate-600"
                      style={{ width: `${pdfRate}%` }}
                    />
                  </div>
                </div>

                <div className="rounded-md bg-muted/50 p-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                      <Sparkles className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">待标注论文</p>
                      <p className="text-xl font-semibold">{stats.pending}</p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Recent Papers */}
            <Card className="col-span-2 border-border/60">
              <CardHeader className="flex flex-row items-center justify-between pb-2 pt-4">
                <CardTitle className="text-sm font-semibold">最近入库</CardTitle>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => navigate("/papers")}
                >
                  查看全部
                  <ArrowRight className="h-3 w-3" />
                </Button>
              </CardHeader>
              <CardContent className="pb-3 pt-0">
                {loading ? (
                  <div className="space-y-3">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <div key={i} className="space-y-2">
                        <Skeleton className="h-4 w-3/4" />
                        <Skeleton className="h-3 w-1/3" />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="divide-y divide-border/60">
                    {recent.map((paper) => (
                      <button
                        key={paper.id}
                        onClick={() => navigate(`/papers/${paper.id}`)}
                        className="flex w-full items-start justify-between gap-3 py-3 text-left transition-colors hover:bg-muted/40"
                      >
                        <div className="min-w-0 flex-1">
                          <h3 className="line-clamp-1 text-sm font-medium text-foreground">
                            {paper.title}
                          </h3>
                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                            <span className="rounded bg-muted px-1.5 py-0.5 font-medium">
                              {paper.source === "arxiv" ? "arXiv" : "本地"}
                            </span>
                            <span>{paper.published_date}</span>
                            {paper.authors && paper.authors.length > 0 && (
                              <>
                                <span>·</span>
                                <span className="max-w-[120px] truncate">
                                  {paper.authors.slice(0, 2).join(", ")}
                                  {paper.authors.length > 2 && " et al."}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                        {paper.tldr && paper.core_contribution ? (
                          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400">
                            <Sparkles className="h-3 w-3" />
                            已标注
                          </span>
                        ) : (
                          <span className="inline-flex shrink-0 items-center rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                            未标注
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-3 divide-x overflow-hidden rounded-lg border bg-card">
            {[
              {
                icon: Library,
                label: "管理论文",
                desc: "入库、标注、搜索",
                path: "/papers",
                accent: true,
              },
              {
                icon: Network,
                label: "查看图谱",
                desc: "团队与论文关系",
                path: "/graph",
                accent: false,
              },
              {
                icon: Sparkles,
                label: "智能聊天",
                desc: "向 AI 提问论文内容",
                path: "/chat",
                accent: false,
              },
            ].map((item) => (
              <Card
                key={item.label}
                className="group cursor-pointer rounded-none border-0 transition-colors hover:bg-muted/55"
                onClick={() => navigate(item.path)}
              >
                <CardContent className="flex items-center gap-3 p-4">
                  <div
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors ${
                      item.accent
                        ? "bg-primary/10 text-primary group-hover:bg-primary/15"
                        : "bg-muted text-muted-foreground group-hover:bg-muted/80"
                    }`}
                  >
                    <item.icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{item.label}</p>
                    <p className="text-[11px] text-muted-foreground">{item.desc}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-all group-hover:translate-x-1 group-hover:opacity-100" />
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
