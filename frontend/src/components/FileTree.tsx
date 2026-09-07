import { useState, useEffect } from "react";
import { FileText, Folder, Search } from "lucide-react";
import { listNotes } from "@/services/api";
import type { NoteItem } from "@/types";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { useProject } from "@/contexts/ProjectContext";

function formatDate(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function NoteItemRow({
  note,
  active,
  onClick,
}: {
  note: NoteItem;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full rounded-md px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        active
          ? "bg-primary/10 text-primary"
          : "hover:bg-muted"
      )}
      aria-label={`选择笔记：${note.title || note.paper_id}`}
    >
      <div className="flex items-center gap-2">
        <FileText
          className={cn(
            "h-4 w-4 shrink-0",
            active ? "text-primary" : "text-muted-foreground"
          )}
        />
        <span className="truncate text-sm font-medium">{note.title || note.paper_id}</span>
      </div>
      <div className="ml-6 mt-1 flex items-center gap-2">
        <span className="font-mono text-[11px] text-muted-foreground">{note.paper_id}</span>
      </div>
      {note.updated_at && (
        <div className="ml-6 mt-1 text-xs text-muted-foreground">{formatDate(note.updated_at)}</div>
      )}
    </button>
  );
}

export function FileTree({
  activeNoteId,
  onSelectNote,
  refreshKey = 0,
}: {
  activeNoteId?: string;
  onSelectNote?: (note: NoteItem) => void;
  refreshKey?: number;
}) {
  const { activeProject } = useProject();
  const [notes, setNotes] = useState<NoteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    if (!activeProject) return;
    listNotes(activeProject.id)
      .then((data) => {
        if (!cancelled) {
          setNotes(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载笔记列表失败");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeProject?.id, refreshKey]);

  const filteredNotes = notes.filter((note) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return note.title?.toLowerCase().includes(q) || note.paper_id?.toLowerCase().includes(q);
  });

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 border-b border-border/60 px-3 py-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Folder className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <span>笔记列表</span>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <Input
            placeholder="搜索笔记..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-9 pl-9 text-xs"
            aria-label="搜索笔记"
          />
        </div>
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto p-2">
        {error && !loading && (
          <div className="px-3 py-2 text-sm text-destructive">{error}</div>
        )}
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="space-y-2 px-3 py-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          ))
        ) : filteredNotes.length === 0 ? (
          <p className="px-3 py-2 text-sm text-muted-foreground">
            {searchQuery ? "未找到匹配的笔记" : "暂无笔记"}
          </p>
        ) : (
          filteredNotes.map((note) => (
            <NoteItemRow
              key={note.paper_id}
              note={note}
              active={activeNoteId === note.paper_id}
              onClick={() => onSelectNote?.(note)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function cn(...classes: (string | false | undefined | null)[]) {
  return classes.filter(Boolean).join(" ");
}
