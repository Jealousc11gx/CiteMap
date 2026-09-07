import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { fetchPaper, downloadPdf, createNoteTemplate } from "@/services/api";
import type { Paper } from "@/types";
import {
  ArrowLeft,
  FileText,
  Download,
  ExternalLink,
  BookOpen,
  Network,
  Calendar,
  User,
  Users,
  Sparkles,
  AlertCircle,
} from "lucide-react";

export function PaperDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    fetchPaper(id)
      .then((data) => {
        setPaper(data);
        setLoading(false);
      })
      .catch(() => {
        setError("论文加载失败");
        setLoading(false);
      });
  }, [id]);

  const handleDownloadPdf = async () => {
    if (!id) return;
    setDownloading(true);
    try {
      await downloadPdf(id);
      setToast("PDF 下载成功");
      setTimeout(() => setToast(null), 3000);
      const updated = await fetchPaper(id);
      setPaper(updated);
    } catch (err) {
      setToast("下载失败: " + err);
      setTimeout(() => setToast(null), 3000);
    } finally {
      setDownloading(false);
    }
  };

  const handleOpenNotes = async () => {
    if (!id || !paper) return;
    if (!paper.note_edited_at) {
      try {
        await createNoteTemplate(id);
      } catch (err) {
        setToast(`创建笔记草稿失败: ${err instanceof Error ? err.message : String(err)}`);
        setTimeout(() => setToast(null), 3000);
        return;
      }
    }
    navigate("/notes", { state: { paperId: id, paperTitle: paper.title } });
  };

  const handleViewGraph = () => {
    if (!id) return;
    navigate("/graph", { state: { highlightPaperId: id } });
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate("/papers")}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回论文列表
          </Button>
        </div>
        <Card className="border-border/60">
          <CardContent className="space-y-4 p-6">
            <Skeleton className="h-8 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </CardContent>
        </Card>
        <div className="grid grid-cols-2 gap-4">
          <Card className="border-border/60">
            <CardContent className="p-6">
              <Skeleton className="h-24 w-full" />
            </CardContent>
          </Card>
          <Card className="border-border/60">
            <CardContent className="p-6">
              <Skeleton className="h-24 w-full" />
            </CardContent>
          </Card>
        </div>
        <Card className="border-border/60">
          <CardContent className="p-6">
            <Skeleton className="mb-2 h-4 w-full" />
            <Skeleton className="mb-2 h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error || !paper) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate("/papers")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          返回论文列表
        </Button>
        <Card className="border-border/60">
          <CardContent className="p-6">
            <p className="text-muted-foreground">{error || "未找到该论文"}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const hasPdf = Boolean(paper.pdf_path);
  const categories = paper.categories.split(/[,\s]+/).filter(Boolean);
  const tagTypeLabels: Record<string, string> = {
    task: "任务",
    method: "方法",
    model: "模型",
    dataset: "数据集",
    modality: "模态",
    application: "应用",
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {toast && (
        <div className="fixed right-4 top-20 z-50 flex items-center gap-2 rounded-lg border border-border/60 bg-card px-4 py-2 text-sm shadow-sm">
          <Sparkles className="h-4 w-4 text-primary" />
          {toast}
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => navigate("/papers")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          返回论文列表
        </Button>
      </div>

      {/* Header */}
      <div className="space-y-4 border-b border-border pb-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="text-xs">
            {paper.source === "arxiv" ? "arXiv" : "本地"}
          </Badge>
          {paper.venue && <Badge className="text-xs">{paper.venue} {paper.venue_year || ""}</Badge>}
          {categories.map((cat, idx) => (
            <Badge key={idx} variant="outline" className="text-xs">
              {cat}
            </Badge>
          ))}
        </div>

        <h1 className="max-w-[28ch] text-3xl font-semibold leading-snug tracking-tight">
          {paper.title}
        </h1>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <Calendar className="h-4 w-4" />
            {paper.published_date}
          </span>
          {hasPdf ? (
            <span className="flex items-center gap-1 text-primary">
              <FileText className="h-4 w-4" />
              PDF 已入库
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <AlertCircle className="h-4 w-4" />
              无 PDF
            </span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {paper.source === "arxiv" && !hasPdf && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleDownloadPdf}
            disabled={downloading}
          >
            <Download className="mr-2 h-4 w-4" />
            {downloading ? "下载中..." : "下载 PDF"}
          </Button>
        )}
        {paper.arxiv_url && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => window.open(paper.arxiv_url, "_blank")}
            aria-label={`在 arXiv 上查看 ${paper.title}`}
          >
            <ExternalLink className="mr-2 h-4 w-4" />
            查看 arXiv
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={handleOpenNotes}>
          <BookOpen className="mr-2 h-4 w-4" />
          打开笔记
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleViewGraph}
          className="gap-1"
        >
          <Network className="h-4 w-4" />
          在图谱中查看
        </Button>
      </div>

      {/* TLDR */}
      {paper.tldr && (
        <Card className="border-primary/25 bg-primary/5">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base font-semibold">
              <Sparkles className="h-4 w-4 text-primary" />
              TLDR
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{paper.tldr}</p>
          </CardContent>
        </Card>
      )}

      {/* Core Contribution */}
      {paper.core_contribution && (
        <Card className="border-border/60">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base font-semibold">
              <Sparkles className="h-4 w-4 text-primary" />
              核心贡献
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed">{paper.core_contribution}</p>
          </CardContent>
        </Card>
      )}

      {(paper.primary_domain || (paper.subfields?.length ?? 0) > 0 || (paper.tags?.length ?? 0) > 0) && (
        <section className="space-y-3 border-y border-border py-4">
          <div className="flex flex-wrap items-center gap-2">
            {paper.primary_domain && <Badge>{paper.primary_domain}</Badge>}
            {paper.subfields?.map((subfield) => (
              <Badge key={subfield} variant="secondary">{subfield}</Badge>
            ))}
          </div>
          {paper.tags && paper.tags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {paper.tags.map((tag) => (
                <Badge key={`${tag.type}:${tag.name}`} variant="outline" className="gap-1">
                  <span className="text-muted-foreground">{tagTypeLabels[tag.type] || tag.type}</span>
                  {tag.name}
                </Badge>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Authors & Teams */}
      <div className="grid grid-cols-2 gap-4">
        {paper.authors && paper.authors.length > 0 && (
          <Card className="border-border/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <User className="h-4 w-4 text-muted-foreground" />
                作者
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {paper.authors.map((author, idx) => (
                  <Badge key={idx} variant="outline">
                    {author}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {paper.teams && paper.teams.length > 0 && (
          <Card className="border-border/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Users className="h-4 w-4 text-muted-foreground" />
                团队
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {paper.teams.map((team, idx) => (
                  <Badge key={idx} variant="secondary">
                    {team}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Abstract */}
      <Card className="border-border/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">摘要</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{paper.abstract}</p>
        </CardContent>
      </Card>
    </div>
  );
}
