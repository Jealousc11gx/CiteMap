import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useProject } from "@/contexts/ProjectContext";
import {
  LayoutDashboard,
  Files,
  Network,
  NotebookPen,
  MessageSquareText,
  Moon,
  Sun,
  Waypoints,
  FolderKanban,
  Radar as RadarIcon,
  Compass,
  Settings,
  ChevronDown,
  Check,
  Plus,
  Pencil,
  Trash2,
  Menu,
  X,
} from "lucide-react";

const NAV_ITEMS = [
  { path: "/", label: "总览", icon: LayoutDashboard },
  { path: "/papers", label: "论文", icon: Files },
  { path: "/graph", label: "图谱", icon: Network },
  { path: "/chat", label: "助手", icon: MessageSquareText },
  { path: "/notes", label: "笔记", icon: NotebookPen },
  { path: "/explore", label: "探索", icon: Compass },
  { path: "/radar", label: "雷达", icon: RadarIcon },
];

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8 shrink-0 text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
      onClick={() => mounted && setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      aria-label={resolvedTheme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
      title={resolvedTheme === "dark" ? "浅色模式" : "深色模式"}
    >
      {mounted && resolvedTheme === "dark" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
    </Button>
  );
}

function ProjectSwitcher() {
  const { projects, activeProject, loading, selectProject, createProject, renameProject, deleteProject } = useProject();
  const [open, setOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<"create" | "rename" | "delete" | null>(null);
  const [dialogProjectId, setDialogProjectId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const dialogProject = projects.find((project) => project.id === dialogProjectId) || null;

  const openDialog = (mode: "create" | "rename" | "delete", projectId?: string) => {
    setOpen(false);
    setError(null);
    const project = projects.find((item) => item.id === projectId);
    setDialogProjectId(project?.id || null);
    setName(mode === "rename" ? project?.name || "" : "");
    setDialogMode(mode);
  };

  const submit = async () => {
    if (!dialogMode || !dialogProject && dialogMode !== "create") return;
    if (dialogMode !== "delete" && !name.trim()) {
      setError("项目名称不能为空");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (dialogMode === "create") await createProject(name.trim());
      if (dialogMode === "rename" && dialogProject) await renameProject(dialogProject.id, name.trim());
      if (dialogMode === "delete" && dialogProject) await deleteProject(dialogProject.id);
      setDialogMode(null);
      setDialogProjectId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div ref={containerRef} className="relative">
        <Button
          variant="outline"
          size="sm"
          className="h-12 w-full min-w-0 justify-between gap-2 border-sidebar-border bg-card px-2.5 shadow-none hover:bg-sidebar-accent"
          onClick={() => setOpen((value) => !value)}
          disabled={loading}
          aria-haspopup="menu"
          aria-expanded={open}
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <FolderKanban className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1 text-left">
            <span className="block truncate text-xs font-semibold">{activeProject?.name || (loading ? "加载项目" : "选择项目")}</span>
            <span className="block text-[10px] font-normal text-muted-foreground">{activeProject ? `${activeProject.paper_count} 篇论文` : "研究项目"}</span>
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        </Button>
        {open && (
          <div className="absolute left-0 top-full z-[60] mt-2 w-full min-w-64 rounded-lg border border-border bg-popover p-1 shadow-md md:left-full md:top-0 md:ml-2 md:mt-0 md:w-72" role="menu">
            <div className="flex h-9 items-center justify-between border-b border-border px-2">
              <span className="text-xs font-medium text-muted-foreground">项目</span>
              <TooltipPrimitive.Provider delayDuration={250}>
                <TooltipPrimitive.Root>
                  <TooltipPrimitive.Trigger asChild>
                    <button
                      type="button"
                      className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => openDialog("create")}
                      aria-label="新建项目"
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                  </TooltipPrimitive.Trigger>
                  <TooltipPrimitive.Portal>
                    <TooltipPrimitive.Content side="right" sideOffset={6} className="z-[70] rounded-md bg-foreground px-2 py-1 text-xs text-background shadow-sm">
                      新建项目
                    </TooltipPrimitive.Content>
                  </TooltipPrimitive.Portal>
                </TooltipPrimitive.Root>
              </TooltipPrimitive.Provider>
            </div>
            <div className="max-h-64 overflow-y-auto py-1">
              {projects.map((project) => (
                <div key={project.id} className="group flex min-h-9 items-center rounded-md hover:bg-muted focus-within:bg-muted">
                  <button
                    role="menuitemradio"
                    aria-checked={project.id === activeProject?.id}
                    onClick={() => {
                      selectProject(project.id);
                      setOpen(false);
                    }}
                    className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <Check className={`h-4 w-4 shrink-0 ${project.id === activeProject?.id ? "opacity-100" : "opacity-0"}`} />
                    <span className="min-w-0 flex-1 truncate">{project.name}</span>
                    <span className="text-xs tabular-nums text-muted-foreground">{project.paper_count}</span>
                  </button>
                  {!project.is_system && (
                    <TooltipPrimitive.Provider delayDuration={250}>
                      <div className="flex shrink-0 items-center pr-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                        <TooltipPrimitive.Root>
                          <TooltipPrimitive.Trigger asChild>
                            <button
                              type="button"
                              className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              onClick={() => openDialog("rename", project.id)}
                              aria-label={`重命名项目 ${project.name}`}
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                          </TooltipPrimitive.Trigger>
                          <TooltipPrimitive.Portal>
                            <TooltipPrimitive.Content side="top" sideOffset={6} className="z-[70] rounded-md bg-foreground px-2 py-1 text-xs text-background shadow-sm">
                              重命名
                            </TooltipPrimitive.Content>
                          </TooltipPrimitive.Portal>
                        </TooltipPrimitive.Root>
                        <TooltipPrimitive.Root>
                          <TooltipPrimitive.Trigger asChild>
                            <button
                              type="button"
                              className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              onClick={() => openDialog("delete", project.id)}
                              aria-label={`删除项目 ${project.name}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </TooltipPrimitive.Trigger>
                          <TooltipPrimitive.Portal>
                            <TooltipPrimitive.Content side="top" sideOffset={6} className="z-[70] rounded-md bg-foreground px-2 py-1 text-xs text-background shadow-sm">
                              删除
                            </TooltipPrimitive.Content>
                          </TooltipPrimitive.Portal>
                        </TooltipPrimitive.Root>
                      </div>
                    </TooltipPrimitive.Provider>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <Dialog open={dialogMode !== null} onOpenChange={(value) => {
        if (!value) {
          setDialogMode(null);
          setDialogProjectId(null);
        }
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{dialogMode === "create" ? "新建项目" : dialogMode === "rename" ? "重命名项目" : "删除项目"}</DialogTitle>
            <DialogDescription>
              {dialogMode === "delete"
                ? `“${dialogProject?.name}”包含 ${dialogProject?.paper_count || 0} 篇论文。论文、PDF、笔记、标注会保留；该项目的聊天会话会删除。`
                : "项目用于限定论文、图谱、笔记与聊天的工作范围。"}
            </DialogDescription>
          </DialogHeader>
          {dialogMode !== "delete" && (
            <Input value={name} onChange={(event) => setName(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void submit()} autoFocus placeholder="项目名称" />
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogMode(null)}>取消</Button>
            <Button variant={dialogMode === "delete" ? "destructive" : "default"} disabled={submitting} onClick={() => void submit()}>
              {dialogMode === "create" ? "创建项目" : dialogMode === "rename" ? "保存名称" : "删除项目"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => setMobileNavOpen(false), [location.pathname, location.search]);

  const renderNavigation = () => (
    <>
      <button
        type="button"
        className="flex h-9 items-center gap-2 px-2 text-left"
        onClick={() => navigate("/")}
        aria-label="返回 CiteMap 总览"
      >
        <span className="flex h-7 w-7 items-center justify-center text-primary">
          <Waypoints className="h-6 w-6" />
        </span>
        <span className="text-lg font-semibold tracking-tight">CiteMap</span>
      </button>

      <div className="mt-4">
        <ProjectSwitcher />
      </div>

      <nav className="mt-6 space-y-1" aria-label="主导航">
        <p className="px-2 pb-1 text-[11px] text-muted-foreground">工作区</p>
        {NAV_ITEMS.map((item) => {
          const isActive = item.path === "/"
            ? location.pathname === "/"
            : location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={`flex h-11 w-full items-center gap-2.5 rounded-md px-2.5 text-sm font-medium transition-colors active:scale-[0.99] md:h-9 ${
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground"
              }`}
              aria-current={isActive ? "page" : undefined}
              aria-label={`导航到${item.label}`}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}
      </nav>

      <div className="mt-auto border-t border-sidebar-border pt-3">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => navigate("/settings")}
            className={`flex h-9 min-w-0 flex-1 items-center gap-2 rounded-md px-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${location.pathname.startsWith("/settings") ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"}`}
          >
            <Settings className="h-4 w-4" />
            <span>设置</span>
          </button>
          <ThemeToggle />
        </div>
        <p className="mt-3 px-2 text-[10px] leading-4 text-muted-foreground">本地优先的论文关系与研究笔记</p>
      </div>
    </>
  );

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a href="#main-content" className="fixed left-3 top-3 z-[80] -translate-y-16 rounded-md bg-foreground px-3 py-2 text-sm text-background transition-transform focus:translate-y-0">
        跳到主要内容
      </a>
      {mobileNavOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[1px] md:hidden"
          onClick={() => setMobileNavOpen(false)}
          aria-label="关闭导航"
        />
      )}
      <aside className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-sidebar-border bg-sidebar p-3 transition-transform duration-200 ease-out md:w-56 md:translate-x-0 ${mobileNavOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <Button variant="ghost" size="icon" className="absolute right-2 top-2 md:hidden" onClick={() => setMobileNavOpen(false)} aria-label="关闭导航">
          <X className="h-4 w-4" />
        </Button>
        <div className="flex h-full flex-col">{renderNavigation()}</div>
      </aside>

      <div className="min-h-screen md:pl-56">
        <header className="sticky top-0 z-30 flex h-14 items-center border-b border-border bg-background/95 px-4 backdrop-blur-sm md:hidden">
          <Button variant="ghost" size="icon" className="mr-2 md:hidden" onClick={() => setMobileNavOpen(true)} aria-label="打开导航">
            <Menu className="h-5 w-5" />
          </Button>
          <span className="truncate text-sm font-semibold">CiteMap</span>
        </header>

        <main id="main-content" className="mx-auto w-full max-w-[1480px] p-4 sm:p-5 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
