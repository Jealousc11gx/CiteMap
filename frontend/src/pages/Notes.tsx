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
    <div className="flex h-[calc(100vh-9.5rem)] min-h-[600px] flex-col">
      <div className="mb-3">
        <h1 className="workspace-heading">笔记</h1>
        <p className="workspace-description">浏览、编辑、预览当前项目中的 Markdown 笔记。</p>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-row overflow-hidden rounded-lg border bg-card">
        <div className="h-full w-72 shrink-0 overflow-hidden border-r border-border bg-muted/20">
          <FileTree
            activeNoteId={activeNote?.paper_id}
            onSelectNote={handleSelectNote}
            refreshKey={notesRefreshKey}
          />
        </div>

        <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-card p-5">
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
