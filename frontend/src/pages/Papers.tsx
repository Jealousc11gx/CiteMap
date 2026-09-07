import { Skeleton } from "@/components/ui/skeleton";
import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  fetchPapers,
  ingestPdf,
  ingestArxiv,
  searchArxivResults,
  annotatePaper,
  downloadPdf,
  batchAnnotate,
  fetchLLMModels,
  addPaperToProject,
  removePaperFromProject,
  fetchAvailablePapers,
} from "@/services/api";
import type { Paper, ArxivSearchResult } from "@/types";
import {
  Upload,
  Search,
  Sparkles,
  Download,
  CheckCircle2,
  AlertCircle,
  Library,
  Plus,
  FolderPlus,
  FolderMinus,
  FolderInput,
} from "lucide-react";
import { ErrorAlert } from "@/components/ErrorAlert";
import { useProject } from "@/contexts/ProjectContext";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

function StatusBadge({
  annotated,
  hasPdf,
  hasNotes,
}: {
  annotated: boolean;
  hasPdf: boolean;
  hasNotes: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {annotated ? (
        <Badge
          variant="default"
          className="gap-0.5 bg-primary px-1.5 py-0.5 text-[10px] text-primary-foreground hover:bg-primary/90"
        >
          <CheckCircle2 className="h-2.5 w-2.5" />
          已标注
        </Badge>
      ) : (
        <Badge variant="outline" className="gap-0.5 px-1.5 py-0.5 text-[10px] text-muted-foreground">
          <AlertCircle className="h-2.5 w-2.5" />
          未标注
        </Badge>
      )}
      {hasPdf && (
        <Badge variant="secondary" className="px-1.5 py-0.5 text-[10px]">
          PDF
        </Badge>
      )}
      {hasNotes && (
        <Badge variant="secondary" className="px-1.5 py-0.5 text-[10px]">
          笔记
        </Badge>
      )}
    </div>
  );
}

function isAnnotated(paper: Paper) {
  return Boolean(paper.tldr && paper.core_contribution);
}

function SelectAllCheckbox({
  checked,
  indeterminate,
  disabled,
  onChange,
}: {
  checked: boolean;
  indeterminate: boolean;
  disabled: boolean;
  onChange: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      disabled={disabled}
      onChange={onChange}
      className="h-4 w-4 rounded border-input accent-primary disabled:opacity-50"
      aria-label="全选当前筛选结果"
    />
  );
}

function EmptyState({
  filter,
  canImport,
  onAdd,
  onImport,
}: {
  filter: boolean;
  canImport: boolean;
  onAdd: () => void;
  onImport: () => void;
}) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-muted">
          <Library className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="mt-4 text-base font-semibold">
          {filter ? "未找到匹配的论文" : canImport ? "当前项目还没有论文" : "没有未分类论文"}
        </h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          {filter
            ? "尝试更换搜索关键词，或清空筛选条件。"
            : canImport ? "从其他项目导入已有论文，或入库一篇新论文。" : "所有论文都已归入项目，也可以继续入库新论文。"}
        </p>
        {!filter && (
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            {canImport && (
              <Button className="gap-2" size="sm" onClick={onImport}>
                <FolderInput className="h-4 w-4" />
                从其他项目导入
              </Button>
            )}
            <Button className="gap-2" size="sm" variant="outline" onClick={onAdd}>
              <Plus className="h-4 w-4" />
              入库新论文
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function Papers() {
  const { projects, activeProject, refreshProjects } = useProject();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);
  const [localFilter, setLocalFilter] = useState("");
  const [arxivId, setArxivId] = useState("");
  const [arxivSearchKeyword, setArxivSearchKeyword] = useState("");
  const [searchResults, setSearchResults] = useState<ArxivSearchResult[]>([]);
  const [ingesting, setIngesting] = useState<Record<string, boolean>>({});
  const [downloading, setDownloading] = useState<Record<string, boolean>>({});
  const [annotating, setAnnotating] = useState<Record<string, boolean>>({});
  const [batchLoading, setBatchLoading] = useState(false);
  const [llmModels, setLlmModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [projectDialogPaper, setProjectDialogPaper] = useState<Paper | null>(null);
  const [assigningProject, setAssigningProject] = useState<string | null>(null);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [availablePapers, setAvailablePapers] = useState<Paper[]>([]);
  const [selectedImports, setSelectedImports] = useState<Set<string>>(new Set());
  const [importQuery, setImportQuery] = useState("");
  const [loadingAvailable, setLoadingAvailable] = useState(false);
  const [importing, setImporting] = useState(false);
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
          message: "加载论文列表失败",
          suggestion: err instanceof Error ? err.message : String(err),
          onRetry: () => window.location.reload(),
        });
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeProject?.id]);

  useEffect(() => {
    fetchLLMModels()
      .then(({ models, default_model }) => {
        const available = models.length ? models : [default_model];
        setLlmModels(available);
        setSelectedModel(default_model || available[0] || "");
      })
      .catch((err) => {
        showToast(`模型列表获取失败: ${err instanceof Error ? err.message : String(err)}`);
      });
  }, []);

  const showToast = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(null), 3000);
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await ingestPdf(file, activeProject?.id);
      const updated = await fetchPapers(undefined, undefined, activeProject?.id);
      setPapers(updated);
      await refreshProjects();
      showToast("PDF 上传成功");
    } catch (err) {
      showToast("上传失败: " + err);
    }
  };

  const handleIngestArxiv = async () => {
    if (!arxivId.trim()) return;
    try {
      await ingestArxiv(arxivId.trim(), false, activeProject?.id);
      setArxivId("");
      const updated = await fetchPapers(undefined, undefined, activeProject?.id);
      setPapers(updated);
      await refreshProjects();
      showToast("arXiv 入库成功");
    } catch (err) {
      showToast("入库失败: " + err);
    }
  };

  const handleSearch = async () => {
    if (!arxivSearchKeyword.trim()) return;
    try {
      const result = await searchArxivResults(arxivSearchKeyword.trim(), 10);
      setSearchResults(result.results || []);
    } catch (err) {
      showToast("搜索失败: " + err);
    }
  };

  const handleIngestResult = async (result: ArxivSearchResult) => {
    setIngesting((prev) => ({ ...prev, [result.id]: true }));
    try {
      await ingestArxiv(result.id, false, activeProject?.id);
      const updated = await fetchPapers(undefined, undefined, activeProject?.id);
      setPapers(updated);
      await refreshProjects();
      setSearchResults((prev) => prev.filter((r) => r.id !== result.id));
      showToast("入库成功");
    } catch (err) {
      showToast("入库失败: " + err);
    } finally {
      setIngesting((prev) => ({ ...prev, [result.id]: false }));
    }
  };

  const handleAnnotate = async (id: string, force = false) => {
    setAnnotating((prev) => ({ ...prev, [id]: true }));
    try {
      await annotatePaper(id, selectedModel || undefined, activeProject?.id, force);
      showToast(force ? "重新标注完成" : "智能标注完成");
      const updated = await fetchPapers(undefined, undefined, activeProject?.id);
      setPapers(updated);
    } catch (err) {
      showToast(`智能标注失败: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setAnnotating((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handleBatchAnnotate = async () => {
    setBatchLoading(true);
    try {
      const result = await batchAnnotate(selectedModel || undefined, activeProject?.id);
      showToast(`批量标注完成，共 ${result.annotated_count} 篇`);
      const updated = await fetchPapers(undefined, undefined, activeProject?.id);
      setPapers(updated);
    } catch (err) {
      showToast(`批量标注失败: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBatchLoading(false);
    }
  };

  const handleDownloadPdf = async (id: string) => {
    setDownloading((prev) => ({ ...prev, [id]: true }));
    try {
      await downloadPdf(id);
      const updated = await fetchPapers(undefined, undefined, activeProject?.id);
      setPapers(updated);
      showToast("PDF 下载成功");
    } catch (err) {
      showToast("下载失败: " + err);
    } finally {
      setDownloading((prev) => ({ ...prev, [id]: false }));
    }
  };

  const handleAddToProject = async (projectId: string) => {
    if (!projectDialogPaper) return;
    setAssigningProject(projectId);
    try {
      await addPaperToProject(projectId, projectDialogPaper.id);
      showToast("论文已添加到项目");
      setProjectDialogPaper(null);
      if (activeProject?.is_system) {
        setPapers((current) => current.filter((paper) => paper.id !== projectDialogPaper.id));
      }
      await refreshProjects();
    } catch (err) {
      showToast(`添加失败: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setAssigningProject(null);
    }
  };

  const handleRemoveFromProject = async (paper: Paper) => {
    if (!activeProject || activeProject.is_system) return;
    try {
      await removePaperFromProject(activeProject.id, paper.id);
      setPapers((current) => current.filter((item) => item.id !== paper.id));
      await refreshProjects();
      showToast("论文已从当前项目移除");
    } catch (err) {
      showToast(`移除失败: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const openImportDialog = async () => {
    if (!activeProject) return;
    setImportDialogOpen(true);
    setLoadingAvailable(true);
    setSelectedImports(new Set());
    setImportQuery("");
    try {
      setAvailablePapers(await fetchAvailablePapers(activeProject.id));
    } catch (err) {
      showToast(`加载可导入论文失败: ${err instanceof Error ? err.message : String(err)}`);
      setAvailablePapers([]);
    } finally {
      setLoadingAvailable(false);
    }
  };

  const toggleImport = (paperId: string) => {
    setSelectedImports((current) => {
      const next = new Set(current);
      if (next.has(paperId)) next.delete(paperId);
      else next.add(paperId);
      return next;
    });
  };

  const handleImportPapers = async () => {
    if (!activeProject || selectedImports.size === 0) return;
    setImporting(true);
    try {
      const results = await Promise.allSettled(
        Array.from(selectedImports).map((paperId) => addPaperToProject(activeProject.id, paperId)),
      );
      const importedCount = results.filter((result) => result.status === "fulfilled").length;
      const failedCount = results.length - importedCount;
      const updated = await fetchPapers(undefined, undefined, activeProject.id);
      setPapers(updated);
      await refreshProjects();
      if (failedCount === 0) setImportDialogOpen(false);
      showToast(failedCount ? `已导入 ${importedCount} 篇，失败 ${failedCount} 篇` : `已导入 ${importedCount} 篇论文`);
    } catch (err) {
      showToast(`导入失败: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setImporting(false);
    }
  };

  const pendingAnnotate = papers.filter((paper) => !isAnnotated(paper)).length;
  const withNotes = papers.filter((p) => p.note_edited_at).length;
  const withPdf = papers.filter((p) => p.pdf_path).length;

  const normalizedFilter = localFilter.toLowerCase();
  const filtered = papers.filter((paper) =>
    [
      paper.title,
      paper.abstract,
      paper.tldr,
      paper.core_contribution,
      paper.primary_domain,
      ...(paper.subfields || []),
      ...(paper.tags || []).map((tag) => tag.name),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(normalizedFilter)
  );
  const filteredAvailable = availablePapers.filter((paper) => {
    const query = importQuery.trim().toLowerCase();
    if (!query) return true;
    return paper.title.toLowerCase().includes(query)
      || paper.abstract.toLowerCase().includes(query)
      || paper.projects?.some((project) => project.name.toLowerCase().includes(query));
  });
  const selectedFilteredCount = filteredAvailable.filter((paper) => selectedImports.has(paper.id)).length;
  const allFilteredSelected = filteredAvailable.length > 0 && selectedFilteredCount === filteredAvailable.length;
  const someFilteredSelected = selectedFilteredCount > 0 && !allFilteredSelected;

  const toggleAllFilteredImports = () => {
    setSelectedImports((current) => {
      const next = new Set(current);
      if (allFilteredSelected) filteredAvailable.forEach((paper) => next.delete(paper.id));
      else filteredAvailable.forEach((paper) => next.add(paper.id));
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-row items-center justify-between gap-3">
        <div>
          <h1 className="workspace-heading">论文</h1>
          <p className="workspace-description">入库、检索、标注当前项目中的研究文献。</p>
        </div>
        {activeProject && !activeProject.is_system && (
          <Button variant="outline" size="sm" className="self-start gap-2" onClick={() => void openImportDialog()}>
            <FolderInput className="h-4 w-4" />
            从其他项目导入
          </Button>
        )}
      </div>

      {pageError && (
        <ErrorAlert
          title="加载失败"
          message={pageError.message}
          suggestion={pageError.suggestion}
          onRetry={pageError.onRetry}
        />
      )}

      {toast && (
        <div className="fixed right-3 top-20 z-50 flex items-center gap-2 rounded-lg border border-border/60 bg-card px-3 py-2 text-sm shadow-sm">
          <Sparkles className="h-4 w-4 text-primary" />
          {toast}
        </div>
      )}

      {/* Ingest Section */}
      <div className="grid grid-cols-2 gap-3">
        <Card className="border-border/60">
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Upload className="h-3.5 w-3.5" />
              </div>
              <h3 className="text-sm font-semibold">上传本地 PDF</h3>
            </div>
            <label className="flex cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-border bg-muted/20 py-6 transition-colors hover:border-primary/45 hover:bg-primary/5 active:translate-y-px">
              <Upload className="mb-1.5 h-6 w-6 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">点击上传 PDF</p>
              <input type="file" accept=".pdf" className="hidden" onChange={handleUpload} />
            </label>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Plus className="h-3.5 w-3.5" />
              </div>
              <h3 className="text-sm font-semibold">arXiv 入库</h3>
            </div>
            <div className="flex gap-2">
              <Input
                placeholder="输入 arXiv ID，如 2402.09199"
                value={arxivId}
                onChange={(e) => setArxivId(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleIngestArxiv()}
                className="h-9 text-sm"
              />
              <Button size="sm" onClick={handleIngestArxiv}>
                入库
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search */}
      <Card className="border-border/60">
        <CardContent className="flex gap-2 p-3">
          <Input
            placeholder="搜索 arXiv 论文..."
            value={arxivSearchKeyword}
            onChange={(e) => setArxivSearchKeyword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="h-9 text-sm"
          />
          <Button onClick={handleSearch} variant="secondary" size="sm">
            <Search className="mr-1.5 h-4 w-4" />
            搜索
          </Button>
        </CardContent>
      </Card>

      {/* Search Results */}
      {searchResults.length > 0 && (
        <div className="space-y-2">
          <div>
            <h3 className="text-base font-semibold">arXiv 搜索结果</h3>
            <p className="text-xs text-muted-foreground">点击「入库」将论文添加到本地知识库</p>
          </div>
          <Card className="border-border/60">
            <CardContent className="divide-y p-0">
              {searchResults.map((result) => (
                <div
                  key={result.id}
                  className="flex flex-row items-start justify-between gap-2 p-3 transition-colors hover:bg-muted/40"
                >
                  <div className="flex-1">
                    <h4 className="text-sm font-medium line-clamp-2">{result.title}</h4>
                    <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                      {result.abstract}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                      <span>{result.published_date}</span>
                      <span>·</span>
                      <span>{result.categories}</span>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    className="shrink-0 self-start"
                    onClick={() => handleIngestResult(result)}
                    disabled={ingesting[result.id]}
                  >
                    {ingesting[result.id] ? "入库中..." : "入库"}
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Library List */}
      <div className="space-y-3">
        <div className="flex flex-row items-center justify-between gap-2">
          <div className="flex flex-row items-center gap-2">
            <Input
              placeholder="筛选已入库论文..."
              value={localFilter}
              onChange={(e) => setLocalFilter(e.target.value)}
              className="h-9 max-w-sm text-sm"
            />
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <span>共 {papers.length} 篇</span>
              <span>·</span>
              <span>待标注 {pendingAnnotate}</span>
              <span>·</span>
              <span>有笔记 {withNotes}</span>
              <span>·</span>
              <span>有 PDF {withPdf}</span>
            </div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleBatchAnnotate}
            disabled={batchLoading || pendingAnnotate === 0}
            className="gap-1 self-start"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {batchLoading ? "标注中..." : `批量标注 (${pendingAnnotate})`}
          </Button>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>模型</span>
            <select
              aria-label="标注模型"
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={batchLoading || Object.values(annotating).some(Boolean)}
              className="h-8 max-w-[220px] rounded-md border border-input bg-background px-2 text-xs text-foreground"
            >
              {!selectedModel && <option value="">后端默认模型</option>}
              {llmModels.map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
          </label>
        </div>

        {loading ? (
          <div className="divide-y overflow-hidden rounded-lg border bg-card">
            {Array.from({ length: 3 }).map((_, i) => (
              <Card key={i} className="rounded-none border-0">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-2/3" />
                    </div>
                    <div className="flex flex-col gap-2">
                      <Skeleton className="h-7 w-20" />
                      <Skeleton className="h-7 w-20" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            filter={Boolean(localFilter)}
            canImport={Boolean(activeProject && !activeProject.is_system)}
            onImport={() => void openImportDialog()}
            onAdd={() => {
              const input = document.querySelector('input[placeholder="输入 arXiv ID，如 2402.09199"]');
              (input as HTMLElement)?.focus();
            }}
          />
        ) : (
          <div className="divide-y overflow-hidden rounded-lg border bg-card">
            {filtered.map((paper) => (
              <Card
                key={paper.id}
                className="cursor-pointer rounded-none border-0 transition-colors hover:bg-muted/50"
                onClick={() => navigate(`/papers/${paper.id}`)}
              >
                <CardContent className="p-4">
                  <div className="flex flex-row items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <h3 className="text-sm font-medium line-clamp-2">{paper.title}</h3>
                      <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                        {paper.tldr || paper.abstract}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                        <StatusBadge
                          annotated={isAnnotated(paper)}
                          hasPdf={Boolean(paper.pdf_path)}
                          hasNotes={Boolean(paper.note_edited_at)}
                        />
                        <span>·</span>
                        <span className="capitalize">{paper.source}</span>
                        <span>·</span>
                        <span>{paper.published_date}</span>
                      </div>
                    </div>
                    <div
                      className="flex flex-row flex-wrap gap-2"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {!paper.pdf_path && paper.source === "arxiv" && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 text-xs"
                          onClick={() => handleDownloadPdf(paper.id)}
                          disabled={downloading[paper.id]}
                        >
                          <Download className="mr-1 h-3.5 w-3.5" />
                          {downloading[paper.id] ? "下载中..." : "下载 PDF"}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant={isAnnotated(paper) ? "outline" : "default"}
                        className="h-8 text-xs"
                        onClick={() => handleAnnotate(paper.id, isAnnotated(paper))}
                        disabled={annotating[paper.id]}
                      >
                        <Sparkles className="mr-1 h-3.5 w-3.5" />
                        {annotating[paper.id]
                          ? "标注中..."
                          : isAnnotated(paper) ? "重新标注" : "智能标注"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 text-xs"
                        onClick={() => setProjectDialogPaper(paper)}
                        title="添加到其他项目"
                      >
                        <FolderPlus className="mr-1 h-3.5 w-3.5" />
                        添加到项目
                      </Button>
                      {activeProject && !activeProject.is_system && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 text-xs text-muted-foreground hover:text-destructive"
                          onClick={() => void handleRemoveFromProject(paper)}
                          title="从当前项目移除"
                        >
                          <FolderMinus className="mr-1 h-3.5 w-3.5" />
                          移除
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Dialog open={Boolean(projectDialogPaper)} onOpenChange={(open) => !open && setProjectDialogPaper(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>添加到项目</DialogTitle>
            <DialogDescription className="line-clamp-2">{projectDialogPaper?.title}</DialogDescription>
          </DialogHeader>
          <div className="max-h-72 space-y-1 overflow-y-auto">
            {projects.filter((project) => project.id !== activeProject?.id && !project.is_system).length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">请先在顶部项目菜单中新建项目</p>
            ) : (
              projects
                .filter((project) => project.id !== activeProject?.id && !project.is_system)
                .map((project) => (
                  <button
                    key={project.id}
                    className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left hover:bg-muted disabled:opacity-50"
                    disabled={Boolean(assigningProject)}
                    onClick={() => void handleAddToProject(project.id)}
                  >
                    <FolderPlus className="h-4 w-4 text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{project.name}</span>
                    <span className="text-xs text-muted-foreground">{project.paper_count} 篇</span>
                  </button>
                ))
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
        <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col gap-3">
          <DialogHeader>
            <DialogTitle>从其他项目导入论文</DialogTitle>
            <DialogDescription>选择尚未加入“{activeProject?.name}”的论文。导入不会从原项目移除论文。</DialogDescription>
          </DialogHeader>
          <Input
            value={importQuery}
            onChange={(event) => setImportQuery(event.target.value)}
            placeholder="搜索标题、摘要或来源项目..."
            aria-label="搜索可导入论文"
          />
          <div className="flex min-h-9 items-center justify-between rounded-md bg-muted/50 px-3 text-sm">
            <label className="flex cursor-pointer items-center gap-2 font-medium">
              <SelectAllCheckbox
                checked={allFilteredSelected}
                indeterminate={someFilteredSelected}
                disabled={filteredAvailable.length === 0 || loadingAvailable}
                onChange={toggleAllFilteredImports}
              />
              <span>全选当前结果</span>
            </label>
            <span className="text-xs tabular-nums text-muted-foreground">
              已选 {selectedImports.size} 篇
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border">
            {loadingAvailable ? (
              <div className="space-y-3 p-4">
                {Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-14 w-full" />)}
              </div>
            ) : filteredAvailable.length === 0 ? (
              <p className="px-4 py-10 text-center text-sm text-muted-foreground">
                {availablePapers.length === 0 ? "没有可导入的论文" : "没有匹配的论文"}
              </p>
            ) : (
              filteredAvailable.map((paper) => (
                <label key={paper.id} className="flex cursor-pointer items-start gap-3 border-b border-border px-3 py-3 last:border-b-0 hover:bg-muted/50">
                  <input
                    type="checkbox"
                    checked={selectedImports.has(paper.id)}
                    onChange={() => toggleImport(paper.id)}
                    className="mt-1 h-4 w-4 rounded border-input accent-primary"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{paper.title}</span>
                    <span className="mt-1 block truncate text-xs text-muted-foreground">
                      来自 {paper.projects?.map((project) => project.name).join("、") || "其他论文库"}
                    </span>
                  </span>
                </label>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportDialogOpen(false)}>取消</Button>
            <Button disabled={selectedImports.size === 0 || importing} onClick={() => void handleImportPapers()}>
              {importing ? "导入中..." : `导入 ${selectedImports.size} 篇论文`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
