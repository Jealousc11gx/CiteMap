import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createNoteTemplate, fetchPapers } from "@/services/api";
import type { Paper } from "@/types";
import { ErrorAlert } from "@/components/ErrorAlert";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Download,
  FileText,
  Library,
  Loader2,
  Sparkles,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useProject } from "@/contexts/ProjectContext";

function isAnnotated(paper: Paper) {
  return Boolean(paper.tldr && paper.core_contribution && paper.venue_checked_at);
}

function timestampValue(value?: string) {
  if (!value) return 0;
  const normalized = value.includes("T") ? value : `${value.replace(" ", "T")}Z`;
  const timestamp = new Date(normalized).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function formatDate(value?: string) {
  const timestamp = timestampValue(value);
  if (!timestamp) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
  }).format(timestamp);
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
          从其他项目导入已有论文，或入库一篇新论文。
        </p>
        <Button className="mt-5 gap-2" size="sm" onClick={onAction}>
          <Library className="h-4 w-4" />
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
  const [openingNoteId, setOpeningNoteId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
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
          message: "加载总览数据失败",
          suggestion: err instanceof Error ? err.message : String(err),
          onRetry: () => window.location.reload(),
        });
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeProject?.id]);

  const annotated = papers.filter(isAnnotated).length;
  const withNotes = papers.filter((paper) => paper.note_edited_at).length;
  const withPdf = papers.filter((paper) => paper.pdf_path).length;
  const pendingAnnotation = papers.filter((paper) => !isAnnotated(paper)).length;
  const missingPdf = papers.filter((paper) => paper.source === "arxiv" && !paper.pdf_path).length;

  const recentNotes = useMemo(
    () => papers
      .filter((paper) => paper.note_edited_at)
      .sort((a, b) => timestampValue(b.note_edited_at) - timestampValue(a.note_edited_at))
      .slice(0, 4),
    [papers],
  );

  const recentAdded = useMemo(
    () => [...papers]
      .sort((a, b) => timestampValue(b.created_at) - timestampValue(a.created_at))
      .slice(0, 5),
    [papers],
  );

  const openNote = async (paper: Paper) => {
    setOpeningNoteId(paper.id);
    try {
      if (!paper.note_edited_at) await createNoteTemplate(paper.id);
      navigate("/notes", { state: { paperId: paper.id, paperTitle: paper.title } });
    } catch (err) {
      setToast(`创建笔记草稿失败: ${err instanceof Error ? err.message : String(err)}`);
      window.setTimeout(() => setToast(null), 3000);
    } finally {
      setOpeningNoteId(null);
    }
  };

  return (
    <div className="space-y-5">
      {toast && (
        <div className="fixed right-3 top-20 z-50 rounded-md border bg-card px-3 py-2 text-sm shadow-sm" role="status">
          {toast}
        </div>
      )}

      <div className="flex items-end justify-between gap-6">
        <div>
          <h1 className="workspace-heading">{activeProject?.name || "项目"}</h1>
          <p className="workspace-description">继续最近的研究，处理仍需整理的论文。</p>
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
        <div className="space-y-4">
          <Skeleton className="h-16 w-full" />
          <div className="grid grid-cols-3 gap-4">
            <Skeleton className="col-span-2 h-72 w-full" />
            <Skeleton className="h-72 w-full" />
          </div>
          <Skeleton className="h-72 w-full" />
        </div>
      ) : papers.length === 0 ? (
        <EmptyState onAction={() => navigate("/papers")} />
      ) : (
        <>
          <div className="flex items-center divide-x overflow-hidden rounded-lg border bg-card">
            {[
              { label: "论文", value: papers.length },
              { label: "已标注", value: annotated },
              { label: "有笔记", value: withNotes },
              { label: "有 PDF", value: withPdf },
            ].map((item) => (
              <div key={item.label} className="flex min-w-0 flex-1 items-baseline gap-2 px-4 py-3">
                <span className="font-mono text-lg font-semibold">{item.value}</span>
                <span className="text-xs text-muted-foreground">{item.label}</span>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-3 gap-4">
            <Card className="col-span-2 border-border/60">
              <CardHeader className="flex flex-row items-center justify-between pb-2 pt-4">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                  <BookOpen className="h-4 w-4 text-primary" />
                  继续研究
                </CardTitle>
                {recentNotes.length > 0 && (
                  <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={() => navigate("/notes")}>
                    全部笔记
                    <ArrowRight className="h-3 w-3" />
                  </Button>
                )}
              </CardHeader>
              <CardContent className="pb-3 pt-0">
                {recentNotes.length === 0 ? (
                  <div className="flex min-h-52 flex-col items-center justify-center text-center">
                    <BookOpen className="h-7 w-7 text-muted-foreground" />
                    <p className="mt-3 text-sm font-medium">还没有正式笔记</p>
                    <p className="mt-1 text-xs text-muted-foreground">从一篇论文开始记录观点、疑问与关联。</p>
                    <Button variant="outline" size="sm" className="mt-4" onClick={() => navigate("/papers")}>
                      选择论文
                    </Button>
                  </div>
                ) : (
                  <div className="divide-y divide-border/60">
                    {recentNotes.map((paper) => (
                      <div key={paper.id} className="flex min-h-14 items-center gap-3 py-2.5">
                        <button
                          className="min-w-0 flex-1 text-left"
                          onClick={() => void openNote(paper)}
                        >
                          <span className="block truncate text-sm font-medium">{paper.title}</span>
                          <span className="mt-0.5 block text-xs text-muted-foreground">
                            最后编辑 {formatDate(paper.note_edited_at)}
                          </span>
                        </button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 shrink-0 gap-1.5 text-xs"
                          onClick={() => void openNote(paper)}
                          disabled={openingNoteId === paper.id}
                        >
                          {openingNoteId === paper.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BookOpen className="h-3.5 w-3.5" />}
                          继续笔记
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-border/60">
              <CardHeader className="pb-2 pt-4">
                <CardTitle className="text-sm font-semibold">待处理</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 pb-4">
                <button
                  className="flex w-full items-center gap-3 rounded-md border p-3 text-left transition-colors hover:bg-muted/50 disabled:cursor-default disabled:opacity-60"
                  onClick={() => navigate("/papers?status=pending_annotation")}
                  disabled={pendingAnnotation === 0}
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Sparkles className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">待智能标注</span>
                    <span className="hidden text-xs text-muted-foreground xl:block">生成 TL;DR 与核心贡献</span>
                  </span>
                  <span className="font-mono text-lg font-semibold">{pendingAnnotation}</span>
                </button>

                <button
                  className="flex w-full items-center gap-3 rounded-md border p-3 text-left transition-colors hover:bg-muted/50 disabled:cursor-default disabled:opacity-60"
                  onClick={() => navigate("/papers?status=missing_pdf")}
                  disabled={missingPdf === 0}
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                    <Download className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">待下载 PDF</span>
                    <span className="hidden text-xs text-muted-foreground xl:block">补全可获取的 arXiv 原文</span>
                  </span>
                  <span className="font-mono text-lg font-semibold">{missingPdf}</span>
                </button>

                {pendingAnnotation === 0 && missingPdf === 0 && (
                  <div className="flex items-center gap-2 px-1 pt-2 text-xs text-muted-foreground">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    当前没有待处理项
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <Card className="border-border/60">
            <CardHeader className="flex flex-row items-center justify-between pb-2 pt-4">
              <CardTitle className="text-sm font-semibold">最近入库</CardTitle>
              <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" onClick={() => navigate("/papers")}>
                查看全部
                <ArrowRight className="h-3 w-3" />
              </Button>
            </CardHeader>
            <CardContent className="pb-3 pt-0">
              <div className="divide-y divide-border/60">
                {recentAdded.map((paper) => (
                  <div key={paper.id} className="flex items-center gap-3 py-3">
                    <button
                      className="min-w-0 flex-1 text-left"
                      onClick={() => navigate(`/papers/${paper.id}`)}
                    >
                      <span className="block truncate text-sm font-medium">{paper.title}</span>
                      <span className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                        <span>{paper.source === "arxiv" ? "arXiv" : "本地"}</span>
                        <span>入库 {formatDate(paper.created_at)}</span>
                        {paper.venue && <span className="text-foreground">{paper.venue} {paper.venue_year || ""}</span>}
                      </span>
                    </button>
                    <span className="hidden items-center gap-1 text-xs text-muted-foreground xl:flex">
                      {paper.pdf_path ? <FileText className="h-3.5 w-3.5" /> : null}
                      {isAnnotated(paper) ? <Sparkles className="h-3.5 w-3.5" /> : null}
                    </span>
                    <Button
                      variant={paper.note_edited_at ? "ghost" : "outline"}
                      size="sm"
                      className="h-8 shrink-0 gap-1.5 text-xs"
                      onClick={() => void openNote(paper)}
                      disabled={openingNoteId === paper.id}
                    >
                      {openingNoteId === paper.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BookOpen className="h-3.5 w-3.5" />}
                      {paper.note_edited_at ? "继续笔记" : "新建笔记"}
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
