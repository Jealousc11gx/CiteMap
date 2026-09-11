import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { FileTree } from "@/components/FileTree";
import { NoteEditor } from "@/components/NoteEditor";
import type { NoteItem } from "@/types";
import { useProject } from "@/contexts/ProjectContext";

export function Notes() {
  const { activeProject } = useProject();
  const location = useLocation();
  const requestedNote = location.state as { paperId?: string; paperTitle?: string } | null;
  const [activeNote, setActiveNote] = useState<NoteItem | undefined>(undefined);
  const [notesRefreshKey, setNotesRefreshKey] = useState(0);

  useEffect(() => {
    setActiveNote(requestedNote?.paperId ? {
      paper_id: requestedNote.paperId,
      title: requestedNote.paperTitle || requestedNote.paperId,
      updated_at: "",
    } : undefined);
  }, [activeProject?.id, requestedNote?.paperId, requestedNote?.paperTitle]);

  const handleSelectNote = (note: NoteItem) => {
    setActiveNote(note);
  };

  return (
    <div className="flex h-[calc(100dvh-7.5rem)] min-h-[520px] flex-col sm:h-[calc(100dvh-8.5rem)] md:h-[calc(100dvh-5rem)]">
      <div className="mb-3">
        <h1 className="workspace-heading">笔记</h1>
        <p className="workspace-description">浏览、编辑、预览当前项目中的 Markdown 笔记。</p>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border bg-card md:flex-row">
        <div className="h-44 w-full shrink-0 overflow-hidden border-b border-border bg-muted/20 md:h-full md:w-72 md:border-b-0 md:border-r">
          <FileTree
            activeNoteId={activeNote?.paper_id}
            onSelectNote={handleSelectNote}
            refreshKey={notesRefreshKey}
          />
        </div>

        <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-card p-3 sm:p-5">
          <NoteEditor
            noteId={activeNote?.paper_id}
            noteTitle={activeNote?.title}
            onSelectAnother={() => {
              setActiveNote(undefined);
            }}
            onSaved={() => setNotesRefreshKey((current) => current + 1)}
          />
        </div>
      </div>
    </div>
  );
}
