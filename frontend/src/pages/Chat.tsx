import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Bot,
  Plus,
  Trash2,
  Pencil,
  Send,
  ChevronRight,
  ChevronDown,
  FileText,
  ExternalLink,
  Sparkles,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatSession, ChatMessage, Paper } from "@/types";
import {
  streamChatMessage,
  listChatSessions,
  createChatSession,
  deleteChatSession,
  renameChatSession,
  getChatMessages,
} from "@/services/api";
import { useProject } from "@/contexts/ProjectContext";

const THINKING_PLACEHOLDER = "__THINKING__";

function cn(...classes: (string | false | undefined | null)[]) {
  return classes.filter(Boolean).join(" ");
}

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1">
      <span
        className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground/60"
        style={{ animationDelay: "0ms" }}
      />
      <span
        className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground/60"
        style={{ animationDelay: "120ms" }}
      />
      <span
        className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground/60"
        style={{ animationDelay: "240ms" }}
      />
    </div>
  );
}

function ToolCallCard({ toolCall }: { toolCall: any }) {
  const [open, setOpen] = useState(false);
  const [viewMode, setViewMode] = useState<"rendered" | "raw">("rendered");
  const isError = toolCall.result?.success === false;

  const renderRenderedView = () => {
    if (toolCall.status === "running" && !toolCall.result) {
      return (
        <div className="flex items-center gap-1.5 py-2 text-muted-foreground">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground/60" style={{ animationDelay: "0ms" }} />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground/60" style={{ animationDelay: "120ms" }} />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground/60" style={{ animationDelay: "240ms" }} />
          <span className="text-xs">思考中...</span>
        </div>
      );
    }

    const result = toolCall.result;
    if (!result) {
      return <div className="text-xs text-muted-foreground">等待结果...</div>;
    }

    const toolName = toolCall.tool;

    if (toolName === "search_arxiv" || toolName === "list_local_papers" || toolName === "search_local_papers") {
      const papers = result.output?.papers || result.papers || [];
      if (papers.length > 0) {
        return (
          <div className="space-y-1.5">
            {papers.slice(0, 5).map((p: any, idx: number) => (
              <div key={idx} className="rounded border border-border/60 bg-background/50 p-2">
                <div className="text-xs font-medium">{p.title || p.id}</div>
                <div className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{p.abstract || p.summary || ""}</div>
              </div>
            ))}
            {papers.length > 5 && (
              <div className="text-xs text-muted-foreground">还有 {papers.length - 5} 篇...</div>
            )}
          </div>
        );
      }
    }

    if (toolName === "get_paper_details") {
      const paper = result.output?.paper || result.paper;
      if (paper) {
        return (
          <div className="space-y-1">
            <div className="text-xs font-medium">{paper.title}</div>
            <div className="text-xs text-muted-foreground">{paper.abstract?.slice(0, 200)}...</div>
            {paper.authors && paper.authors.length > 0 && (
              <div className="text-xs text-muted-foreground">
                作者：{paper.authors.slice(0, 3).map((a: any) => a.name || a).join(", ")}
              </div>
            )}
          </div>
        );
      }
    }

    if (toolName === "get_graph_summary") {
      const stats = [
        { label: "团队数", value: result.team_count },
        { label: "论文连接", value: result.paper_connection_count },
        { label: "合作关系", value: result.team_collaboration_count },
      ].filter((s) => s.value !== undefined);

      return (
        <div className="grid grid-cols-3 gap-2">
          {stats.map((s) => (
            <div key={s.label} className="rounded border border-border/60 bg-background/50 p-2 text-center">
              <div className="text-xs text-muted-foreground">{s.label}</div>
              <div className="mt-0.5 text-sm font-medium">{s.value}</div>
            </div>
          ))}
        </div>
      );
    }

    if (toolName === "annotate_paper_tool") {
      const annotation = result.output || result.result;
      if (annotation?.tldr || annotation?.core_contribution) {
        return (
          <div className="space-y-2 text-xs">
            {annotation.tldr && (
              <div>
                <div className="font-medium">TLDR</div>
                <div className="mt-0.5 text-muted-foreground line-clamp-4">{annotation.tldr}</div>
              </div>
            )}
            {annotation.core_contribution && (
              <div>
                <div className="font-medium">核心贡献</div>
                <div className="mt-0.5 text-muted-foreground line-clamp-3">{annotation.core_contribution}</div>
              </div>
            )}
            {annotation.primary_domain && (
              <div className="text-muted-foreground">领域：{annotation.primary_domain}</div>
            )}
          </div>
        );
      }
    }

    if (result.title || result.summary) {
      return (
        <div className="space-y-1">
          {result.title && <div className="text-xs font-medium">{result.title}</div>}
          {result.summary && <div className="text-xs text-muted-foreground">{result.summary}</div>}
        </div>
      );
    }

    return (
      <div className="text-xs text-muted-foreground">
        {typeof result === "string" ? result : JSON.stringify(result)}
      </div>
    );
  };

  const renderRawView = () => {
    if (!toolCall.result) {
      return <div className="text-xs text-muted-foreground">等待结果...</div>;
    }
    return (
      <pre className="overflow-x-auto rounded bg-background p-2 font-mono text-xs">
        {typeof toolCall.result === "string" ? toolCall.result : JSON.stringify(toolCall.result, null, 2)}
      </pre>
    );
  };

  return (
    <div className="my-2 overflow-hidden rounded-lg border border-border">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 bg-muted/50 px-3 py-2 text-left text-sm hover:bg-muted"
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        <span className="font-mono text-xs">{toolCall.tool}</span>
        <span
          className={cn(
            "rounded-full px-1.5 py-0.5 text-xs",
            toolCall.status === "done" && !isError
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
              : isError
                ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
          )}
        >
          {toolCall.status === "running" ? "运行中" : isError ? "失败" : "完成"}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-border px-3 py-2">
          {toolCall.arguments && (
            <div>
              <div className="mb-1 text-xs text-muted-foreground">参数</div>
              <pre className="overflow-x-auto rounded bg-background p-2 font-mono text-xs">
                {JSON.stringify(toolCall.arguments, null, 2)}
              </pre>
            </div>
          )}
          {toolCall.result && (
            <div>
              <div className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                <span>结果</span>
                <div className="flex rounded border border-border/60 bg-muted/30 p-0.5">
                  <button
                    onClick={() => setViewMode("rendered")}
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] transition-colors",
                      viewMode === "rendered" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    渲染视图
                  </button>
                  <button
                    onClick={() => setViewMode("raw")}
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] transition-colors",
                      viewMode === "raw" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    原始结果
                  </button>
                </div>
              </div>
              {viewMode === "rendered" ? renderRenderedView() : renderRawView()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PaperCard({ paper }: { paper: Paper }) {
  return (
    <Card className="my-2 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h4 className="line-clamp-2 text-sm font-medium">{paper.title}</h4>
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{paper.abstract}</p>
          <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{paper.published_date}</span>
            <span>·</span>
            <span>{paper.categories}</span>
          </div>
        </div>
        {paper.arxiv_url && (
          <a href={paper.arxiv_url} target="_blank" rel="noreferrer" className="shrink-0">
            <ExternalLink className="h-4 w-4 text-muted-foreground hover:text-foreground" />
          </a>
        )}
      </div>
    </Card>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const papers = Array.isArray(message.papers) ? message.papers : [];
  const toolCalls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
  const isThinking = message.content === THINKING_PLACEHOLDER;
  const hasRunningTool = toolCalls.some((tc) => tc.status === "running");
  const showThinking = isThinking || (hasRunningTool && !message.content);

  return (
    <div className={cn("mb-4 flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
        )}
      >
        {isUser ? <span className="text-xs font-bold">我</span> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={cn(
          "flex max-w-[80%] flex-1 flex-col",
          isUser ? "items-end" : "items-start"
        )}
      >
        <div
          className={cn(
            "rounded-lg px-4 py-2.5 text-sm",
            isUser
              ? "rounded-tr-sm bg-primary text-primary-foreground"
              : "rounded-tl-sm bg-muted"
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : showThinking ? (
            <ThinkingIndicator />
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {toolCalls.length > 0 && (
          <div className="mt-2 w-full">
            {toolCalls.map((tc: any, i: number) => (
              <ToolCallCard key={i} toolCall={tc} />
            ))}
          </div>
        )}

        {papers.length > 0 && (
          <div className="mt-2 w-full space-y-2">
            {papers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function Chat() {
  const { activeProject } = useProject();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [sessionToRename, setSessionToRename] = useState<string | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const currentSessionIdRef = useRef<string | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const sessionsRequestRef = useRef(0);
  const activeProjectIdRef = useRef<string | null>(activeProject?.id || null);

  useEffect(() => {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() => {
    const requestId = ++sessionsRequestRef.current;
    activeProjectIdRef.current = activeProject?.id || null;
    setCurrentSessionId(null);
    currentSessionIdRef.current = null;
    setMessages([]);
    setSessions([]);
    setIsLoading(false);
    if (activeProject) void loadSessions(requestId);
  }, [activeProject?.id]);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const threshold = 120;
    const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceToBottom <= threshold) {
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    }
  }, [messages]);

  const loadSessions = async (requestId = sessionsRequestRef.current) => {
    try {
      const data = await listChatSessions(activeProject?.id);
      if (requestId !== sessionsRequestRef.current) return;
      setSessions(data);
      if (data.length > 0 && !currentSessionIdRef.current) {
        const first = data[0];
        setCurrentSessionId(first.id);
        loadMessages(first.id);
      }
    } catch (e) {
      console.error("Failed to load sessions", e);
    }
  };

  const loadMessages = async (sessionId: string) => {
    try {
      const data = await getChatMessages(sessionId);
      const normalized = (data || []).map((m: any) => {
        let toolCalls = [];
        if (Array.isArray(m.tool_calls)) {
          toolCalls = m.tool_calls;
        } else if (typeof m.tool_calls === "string" && m.tool_calls.trim()) {
          try {
            toolCalls = JSON.parse(m.tool_calls);
          } catch {
            toolCalls = [];
          }
        }
        return {
          ...m,
          papers: Array.isArray(m.papers) ? m.papers : [],
          tool_calls: Array.isArray(toolCalls) ? toolCalls : [],
        };
      });
      setMessages(normalized);
    } catch (e) {
      console.error("Failed to load messages", e);
    }
  };

  const handleNewSession = async (): Promise<ChatSession | null> => {
    if (sessions[0] && !sessions[0].title) {
      setCurrentSessionId(sessions[0].id);
      setMessages([]);
      return sessions[0];
    }

    try {
      const session = await createChatSession("", activeProject?.id);
      setSessions((prev) => [session, ...prev]);
      setCurrentSessionId(session.id);
      setMessages([]);
      return session;
    } catch (e) {
      console.error("Failed to create session", e);
      return null;
    }
  };

  const handleDeleteSession = (sessionId: string) => {
    setSessionToDelete(sessionId);
    setDeleteDialogOpen(true);
  };

  const confirmDeleteSession = async () => {
    if (!sessionToDelete) return;

    try {
      await deleteChatSession(sessionToDelete);
      const remaining = sessions.filter((s) => s.id !== sessionToDelete);
      setSessions(remaining);
      if (currentSessionIdRef.current === sessionToDelete) {
        if (remaining.length > 0) {
          setCurrentSessionId(remaining[0].id);
          setMessages([]);
          loadMessages(remaining[0].id);
        } else {
          setCurrentSessionId(null);
          setMessages([]);
        }
      }
    } catch (e) {
      console.error("Failed to delete session", e);
    } finally {
      setDeleteDialogOpen(false);
      setSessionToDelete(null);
    }
  };

  const handleRenameSession = (session: ChatSession) => {
    setSessionToRename(session.id);
    setRenameTitle(session.title || "");
    setRenameDialogOpen(true);
  };

  const confirmRenameSession = async () => {
    if (!sessionToRename || !renameTitle.trim()) return;

    try {
      const updated = await renameChatSession(sessionToRename, renameTitle.trim());
      setSessions((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    } catch (e) {
      console.error("Failed to rename session", e);
    } finally {
      setRenameDialogOpen(false);
      setSessionToRename(null);
      setRenameTitle("");
    }
  };

  const handleSend = async () => {
    const message = input.trim();
    if (!message || isLoading) return;
    const sendingProjectId = activeProject?.id;

    setInput("");
    if (inputRef.current) inputRef.current.value = "";

    let sessionId = currentSessionIdRef.current;

    if (!sessionId) {
      const newSession = await handleNewSession();
      if (!newSession) return;
      sessionId = newSession.id;
    }

    const userMsg: ChatMessage = {
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    const assistantMsg: ChatMessage = {
      role: "assistant",
      content: THINKING_PLACEHOLDER,
      tool_calls: [],
      papers: [],
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      await streamChatMessage(
        sessionId,
        message,
        (event) => {
          if (activeProjectIdRef.current !== sendingProjectId) return;
          setMessages((prev) => {
            const last = { ...prev[prev.length - 1] };
            if (event.type === "thinking" || event.type === "answer") {
              last.content = event.content || "";
            } else if (event.type === "tool_call") {
              if (!last.tool_calls) last.tool_calls = [];
              if (event.tool) {
                last.tool_calls = [
                  ...last.tool_calls,
                  {
                    tool: event.tool,
                    arguments: event.arguments,
                    result: event.result,
                    status: "running",
                  },
                ];
              }
            } else if (event.type === "tool_result") {
              if (last.tool_calls && last.tool_calls.length > 0) {
                const updated = [...last.tool_calls];
                const idx = updated.findIndex((tc: any) => tc.tool === event.tool && tc.status === "running");
                if (idx >= 0) {
                  updated[idx] = { ...updated[idx], result: event.result, status: "done" };
                  last.tool_calls = updated;
                }
              }
            }
            if (event.papers) last.papers = event.papers;
            if (event.tool_calls) last.tool_calls = event.tool_calls;
            return [...prev.slice(0, -1), last];
          });
        },
        (fullMessage) => {
          if (activeProjectIdRef.current !== sendingProjectId) return;
          setMessages((prev) => [...prev.slice(0, -1), fullMessage]);
          setIsLoading(false);
          loadSessions();
        },
        (err) => {
          if (activeProjectIdRef.current !== sendingProjectId) return;
          console.error("Stream error", err);
          setMessages((prev) => {
            const last = { ...prev[prev.length - 1] };
            last.content = `错误：${err.message}`;
            return [...prev.slice(0, -1), last];
          });
          setIsLoading(false);
        },
        sendingProjectId,
      );
    } catch (e) {
      console.error("Failed to send message", e);
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const selectSession = (session: ChatSession) => {
    setCurrentSessionId(session.id);
    setMessages([]);
    loadMessages(session.id);
  };

  const renderSidebar = () => (
    <Card className="flex h-36 min-h-0 w-full shrink-0 flex-col overflow-hidden rounded-none border-0 border-b border-border bg-muted/20 md:h-full md:w-60 md:border-b-0 md:border-r">
      <div className="border-b border-border/60 p-2.5">
        <Button onClick={handleNewSession} className="w-full gap-2" size="sm">
          <Plus className="h-4 w-4" />
          新建会话
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="space-y-0.5 p-1.5">
          {sessions.map((session) => (
            <div
              key={session.id}
              className={cn(
                "group flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-sm",
                currentSessionId === session.id
                  ? "bg-muted"
                  : "hover:bg-muted/50"
              )}
              onClick={() => selectSession(session)}
            >
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate">{session.title || "未命名会话"}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleRenameSession(session);
                }}
                className="rounded p-1 opacity-100 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
                aria-label={`重命名会话：${session.title || "未命名会话"}`}
                title="重命名"
              >
                <Pencil className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDeleteSession(session.id);
                }}
                className="rounded p-1 opacity-100 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
                aria-label={`删除会话：${session.title || "未命名会话"}`}
                title="删除"
              >
                <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" />
              </button>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );

  return (
    <div className="flex h-[calc(100dvh-7.5rem)] min-h-[520px] flex-col overflow-hidden sm:h-[calc(100dvh-8.5rem)] md:h-[calc(100dvh-5rem)]">
      <div className="mb-3">
        <h1 className="workspace-heading">研究助手</h1>
        <p className="workspace-description">围绕当前项目检索、分析、整理论文。</p>
      </div>

      <div className="relative flex min-h-0 w-full flex-1 flex-col gap-0 overflow-hidden rounded-lg border bg-card md:flex-row">
        {renderSidebar()}

        <Card className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-none border-0">
          <div ref={messagesContainerRef} className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-4">
            {messages.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                  <Sparkles className="h-6 w-6 text-primary" />
                </div>
                <p className="mt-3 text-base font-medium">开始对话</p>
                <p className="mt-1 text-xs">输入问题，Agent 会自动调用论文管理工具</p>
              </div>
            ) : (
              <div className="mx-auto w-full max-w-4xl">
                {messages.map((msg, i) => (
                  <MessageBubble key={i} message={msg} />
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-border/60 p-3 sm:p-4">
            <div className="mx-auto flex w-full max-w-4xl gap-2">
              <Textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入消息... (Shift+Enter 换行)"
                className="min-h-[48px] max-h-[200px] resize-none"
                rows={1}
                aria-label="聊天输入框"
              />
              <Button
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                size="icon"
                className="h-12 w-12 shrink-0"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {/* Delete dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除会话</DialogTitle>
            <DialogDescription>确定要删除这个会话吗？此操作无法撤销。</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              取消
            </Button>
            <Button variant="destructive" onClick={confirmDeleteSession}>
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename dialog */}
      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重命名会话</DialogTitle>
            <DialogDescription>输入新的会话名称。</DialogDescription>
          </DialogHeader>
          <Input
            value={renameTitle}
            onChange={(e) => setRenameTitle(e.target.value)}
            placeholder="会话名称"
            onKeyDown={(e) => {
              if (e.key === "Enter") confirmRenameSession();
            }}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={confirmRenameSession} disabled={!renameTitle.trim()}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
