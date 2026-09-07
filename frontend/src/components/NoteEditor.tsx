import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getNote, saveNote, createNoteTemplate, deleteNote } from "@/services/api";
import { joinMarkdownDocument, splitMarkdownDocument } from "@/lib/markdown";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCircle2, Eye, FileText, PenLine, Trash2, Sparkles, Save } from "lucide-react";

interface NoteEditorProps {
  noteId?: string;
  noteTitle?: string;
  onSelectAnother?: () => void;
  onSaved?: () => void;
}

export function NoteEditor({ noteId, noteTitle, onSelectAnother, onSaved }: NoteEditorProps) {
  const [mode, setMode] = useState<"edit" | "preview">("edit");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "unsaved" | "saving" | "saved">("idle");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const saveTimerRef = useRef<number | null>(null);
  const messageTimerRef = useRef<number | null>(null);
  const frontmatterRef = useRef("");

  useEffect(() => {
    if (!noteId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setMessage(null);
    setSaveStatus("idle");
    frontmatterRef.current = "";
    getNote(noteId)
      .then((data) => {
        if (!cancelled) {
          const document = splitMarkdownDocument(data.content || "");
          frontmatterRef.current = document.frontmatter;
          setContent(document.body);
          setLoading(false);
          setSaveStatus(data.note_edited_at ? "saved" : "unsaved");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError((err as Error).message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [noteId]);

  const showMessage = (msg: string) => {
    setMessage(msg);
    if (messageTimerRef.current) clearTimeout(messageTimerRef.current);
    messageTimerRef.current = window.setTimeout(() => setMessage(null), 2000);
  };

  const handleManualSave = async () => {
    if (!noteId) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    setSaving(true);
    setError(null);
    try {
      await saveNote(noteId, joinMarkdownDocument(frontmatterRef.current, content));
      setSaveStatus("saved");
      onSaved?.();
      showMessage("保存成功");
    } catch (err) {
      setSaveStatus("unsaved");
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleCreateTemplate = async () => {
    if (!noteId) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const draft = await createNoteTemplate(noteId);
      const document = splitMarkdownDocument(draft.content || "");
      frontmatterRef.current = document.frontmatter;
      setContent(document.body);
      setSaveStatus("unsaved");
      showMessage("模板创建成功");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const executeDelete = async () => {
    if (!noteId) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await deleteNote(noteId);
      showMessage("已删除（可刷新页面恢复）");
      setTimeout(() => {
        setMessage(null);
        onSelectAnother?.();
      }, 2000);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleteDialogOpen(true);
  };

  if (!noteId) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
        <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-muted">
          <FileText className="h-7 w-7" />
        </div>
        <p className="mt-4 font-medium">请从左侧选择一篇笔记</p>
        <p className="mt-1 text-sm">开始编辑你的 Markdown 笔记</p>
      </div>
    );
  }

  return (
    <>
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>此操作不可撤销，确定要删除这条笔记吗？</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                setDeleteDialogOpen(false);
                await executeDelete();
              }}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="flex h-full flex-col">
        <div className="flex flex-col gap-3 border-b border-border/60 pb-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{noteTitle || noteId}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">Markdown 笔记编辑</p>
          </div>
          <div className="flex w-full flex-wrap items-center justify-between gap-2">
            <div
              className="flex h-8 items-center rounded-md bg-muted p-0.5"
              role="group"
              aria-label="笔记显示模式"
            >
              <button
                type="button"
                aria-pressed={mode === "edit"}
                onClick={() => setMode("edit")}
                className={`flex h-7 items-center gap-1.5 rounded px-2.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ${
                  mode === "edit"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <PenLine className="h-3.5 w-3.5" />
                编辑
              </button>
              <button
                type="button"
                aria-pressed={mode === "preview"}
                onClick={() => setMode("preview")}
                className={`flex h-7 items-center gap-1.5 rounded px-2.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 ${
                  mode === "preview"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Eye className="h-3.5 w-3.5" />
                预览
              </button>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCreateTemplate}
                disabled={saving || loading}
                className="gap-1"
              >
                <Sparkles className="h-3.5 w-3.5" />
                生成模板
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDelete}
                disabled={saving || loading}
                className="gap-1 text-destructive hover:text-destructive"
              >
                <Trash2 className="h-3.5 w-3.5" />
                删除
              </Button>
              <Button
                size="sm"
                onClick={handleManualSave}
                disabled={saving || loading || saveStatus === "saving"}
                className="gap-1"
              >
                <Save className="h-3.5 w-3.5" />
                {saving ? "保存中..." : "保存"}
              </Button>
            </div>
          </div>
        </div>

        <div className="mt-4 flex-1 min-h-0">
          {error && (
            <Alert variant="destructive" className="mb-3">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {message && (
            <Alert className="mb-3">
              <AlertDescription>{message}</AlertDescription>
            </Alert>
          )}
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          ) : mode === "edit" ? (
            <textarea
              value={content}
              onChange={(e) => {
                setContent(e.target.value);
                setSaveStatus("unsaved");
              }}
              className="h-full w-full resize-none rounded-lg border border-border/60 bg-transparent p-4 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="开始编写笔记..."
            />
          ) : (
            <div className="h-full overflow-auto rounded-lg border border-border/60 bg-background/40">
              {content.trim() ? (
                <article className="markdown-preview mx-auto min-h-full max-w-[75ch] px-8 py-6">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    skipHtml
                    components={{
                      a: ({ children, ...props }) => (
                        <a {...props} target="_blank" rel="noreferrer noopener">
                          {children}
                        </a>
                      ),
                    }}
                  >
                    {content}
                  </ReactMarkdown>
                </article>
              ) : (
                <div className="flex h-full min-h-48 flex-col items-center justify-center px-6 text-center text-muted-foreground">
                  <FileText className="h-6 w-6" />
                  <p className="mt-3 text-sm font-medium text-foreground">暂无可预览内容</p>
                  <p className="mt-1 text-xs">切换到编辑模式开始记录</p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="mt-4 flex flex-row items-center justify-between gap-3 border-t border-border/60 pt-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            {saveStatus === "saving" && (
              <span className="flex items-center gap-1 text-primary">
                <div className="h-2 w-2 animate-spin rounded-full border border-primary border-t-transparent" />
                正在保存...
              </span>
            )}
            {saveStatus === "saved" && (
              <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="h-3 w-3" />
                已保存
              </span>
            )}
            {saveStatus === "unsaved" && (
              <span className="flex items-center gap-1">
                <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
                有未保存更改
              </span>
            )}
            <span>{content.length > 0 ? `${content.length} 个字符` : "空笔记"}</span>
          </div>
        </div>
      </div>
    </>
  );
}
