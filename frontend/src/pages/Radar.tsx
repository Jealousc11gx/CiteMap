import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, ExternalLink, FileSearch, Loader2, Radar as RadarIcon, RefreshCw, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorAlert } from "@/components/ErrorAlert";
import { useProject } from "@/contexts/ProjectContext";
import { fetchRadarConfig, fetchRadarConnection, fetchRadarMatches, scanRadar, syncRadarSaved, updateRadarMatch } from "@/services/api";
import type { RadarConfig, RadarMatch, RadarState } from "@/types";

const EMPTY_CONFIG: Omit<RadarConfig, "project_id" | "updated_at"> = {
  enabled: false,
  categories: ["cs.AI"],
  include_keywords: [],
  exclude_keywords: [],
  profile_override: "",
  anchor_paper_ids: [],
  top_k: 10,
  min_score: 0,
  include_cross_list: true,
  send_empty: false,
  fetch_limit: 100,
  debug: false,
  compute_mode: "cloud",
};
const RADAR_DEPLOYMENT_GUIDE_URL = "https://github.com/Jealousc11gx/CiteMap/blob/main/docs/radar-github-action-setup.md";

const RADAR_STATE_LABELS: Record<RadarState, string> = {
  unread: "未读",
  read: "已读",
  saved: "已保存",
  dismissed: "已忽略",
};

function RadarCard({ match, onState }: { match: RadarMatch; onState: (match: RadarMatch, state: RadarState) => void }) {
  const [busy, setBusy] = useState(false);
  const isRead = match.state === "read" || match.state === "saved";
  const canMarkRead = match.state === "unread";
  const canSave = match.state !== "saved";
  const canDismiss = match.state === "unread" || match.state === "read";
  const apply = async (state: RadarState) => {
    setBusy(true);
    try {
      await onState(match, state);
    } finally {
      setBusy(false);
    }
  };
  return (
    <article className="p-4 transition-colors hover:bg-muted/25 sm:p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <a href={match.arxiv_url} target="_blank" rel="noreferrer" className="group inline-flex max-w-full items-start gap-1.5 rounded-sm text-base font-semibold leading-6 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <span>{match.title}</span><ExternalLink className="mt-1 h-3.5 w-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
          </a>
          <p className="mt-1 text-xs text-muted-foreground">{match.arxiv_id} · {match.published_date || "未知日期"}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2"><span className="font-mono text-xs tabular-nums text-muted-foreground">{match.score.toFixed(3)}</span><Badge variant={match.state === "saved" ? "default" : "secondary"}>{RADAR_STATE_LABELS[match.state]}</Badge></div>
      </div>
      {match.title_zh && <p className="mt-2 text-sm font-medium">{match.title_zh}</p>}
      {!!match.affiliations?.length && <p className="mt-2 text-xs text-muted-foreground">机构：{match.affiliations.join(" · ")}</p>}
      {!!match.corresponding_authors?.length && <p className="mt-1 text-xs text-muted-foreground">通讯作者：{match.corresponding_authors.join("、")}</p>}
      {match.tldr && <p className="mt-3 text-sm leading-6"><span className="font-medium">TLDR：</span>{match.tldr}</p>}
      <p className="mt-3 line-clamp-4 text-sm leading-6 text-muted-foreground">{match.ai_summary || match.abstract_zh || match.abstract || "暂无摘要"}</p>
      <p className="mt-3 text-xs text-muted-foreground">{match.reason || "项目语义相似度"}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={busy || !canMarkRead} onClick={() => apply("read")}>{busy ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}{isRead ? "已读" : "标记已读"}</Button>
        <Button size="sm" disabled={busy || !canSave} onClick={() => apply("saved")}><Save className="mr-1 h-3.5 w-3.5" />{match.state === "saved" ? "已保存" : "保存入库"}</Button>
        <Button size="sm" variant="ghost" disabled={busy || !canDismiss} onClick={() => apply("dismissed")}><X className="mr-1 h-3.5 w-3.5" />{match.state === "dismissed" ? "已忽略" : "忽略"}</Button>
      </div>
    </article>
  );
}

export function Radar() {
  const { activeProject } = useProject();
  const navigate = useNavigate();
  const projectId = activeProject?.id;
  const [config, setConfig] = useState(EMPTY_CONFIG);
  const [matches, setMatches] = useState<RadarMatch[]>([]);
  const [tab, setTab] = useState<"all" | RadarState>("all");
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [connectionSaved, setConnectionSaved] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [nextConfig, nextMatches, connection] = await Promise.all([fetchRadarConfig(projectId), fetchRadarMatches(projectId), fetchRadarConnection()]);
      setConfig({ ...nextConfig, categories: nextConfig.categories.length ? nextConfig.categories : ["cs.AI"] });
      setMatches(nextMatches);
      setConnectionSaved(Boolean(connection.remote_url && connection.token_configured));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => tab === "all" ? matches : matches.filter((match) => match.state === tab), [matches, tab]);
  const stateCount = (state: RadarState) => matches.filter((match) => match.state === state).length;

  const runScan = async () => {
    if (!projectId) return;
    setScanning(true);
    setError(null);
    setNotice(null);
    try {
      if (config.compute_mode === "cloud") {
        if (!connectionSaved) throw new Error("请先在设置中连接 Worker，再获取云端结果");
        const result = await syncRadarSaved(projectId, false, false);
        setNotice(`已获取云端结果，新增 ${result.synced.applied || 0} 条。`);
      } else if (config.compute_mode === "hybrid") {
        try {
          if (!connectionSaved) throw new Error("未配置云端连接");
          const result = await syncRadarSaved(projectId, false, false);
          setNotice(`已获取云端结果，新增 ${result.synced.applied || 0} 条。`);
        } catch {
          await scanRadar(projectId);
          setNotice("云端暂不可用，已使用本地计算。");
        }
      } else {
        await scanRadar(projectId);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setScanning(false);
    }
  };

  const setState = async (match: RadarMatch, state: RadarState) => {
    try {
      const updated = await updateRadarMatch(match.id, state);
      setMatches((items) => items.map((item) => item.id === match.id ? { ...item, ...updated } : item));
      if (connectionSaved && projectId) {
        syncRadarSaved(projectId).catch((err) => {
          setError(err instanceof Error ? err.message : String(err));
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (!activeProject || activeProject.is_system) return <div className="flex min-h-64 items-center justify-center rounded-lg border border-dashed p-8 text-center"><div><RadarIcon className="mx-auto h-8 w-8 text-muted-foreground" /><p className="mt-3 font-medium">请选择研究项目</p><p className="mt-1 text-sm text-muted-foreground">论文雷达会根据项目中的论文生成个性化推荐。</p></div></div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="workspace-heading flex items-center gap-2"><RadarIcon className="h-5 w-5 text-primary" />论文雷达</h1>
          <p className="workspace-description">根据“{activeProject.name}”中的 {activeProject.paper_count} 篇论文生成个性化推荐。</p>
        </div>
        <div className="w-full sm:w-auto">
          {(config.compute_mode !== "cloud" || connectionSaved) && <Button onClick={runScan} disabled={scanning}>{scanning ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}{scanning ? "运行中" : config.compute_mode === "local" ? "本地扫描" : "获取结果"}</Button>}
        </div>
      </div>
      {error && <ErrorAlert title="雷达操作失败" message={error} onRetry={() => void load()} />}
      {notice && <div className="flex items-center gap-2 rounded-md border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300" role="status"><CheckCircle2 className="h-4 w-4 shrink-0" />{notice}<button className="ml-auto rounded p-1 hover:bg-emerald-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => setNotice(null)} aria-label="关闭提示"><X className="h-3.5 w-3.5" /></button></div>}
      {!connectionSaved && config.compute_mode !== "local" && (
        <section className="rounded-lg border bg-muted/30 px-4 py-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold">连接云端雷达</h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">配置远程服务地址与访问令牌后获取云端结果。</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button variant="outline" asChild><a href={RADAR_DEPLOYMENT_GUIDE_URL} target="_blank" rel="noreferrer">部署文档<ExternalLink className="ml-2 h-4 w-4" /></a></Button>
              <Button onClick={() => navigate("/settings?tab=radar")}>去设置</Button>
            </div>
          </div>
        </section>
      )}
      <div className="flex gap-1 overflow-x-auto border-b pb-2" role="tablist" aria-label="雷达结果状态">
        {(["all", "unread", "read", "saved", "dismissed"] as const).map((item) => <Button key={item} size="sm" variant={tab === item ? "secondary" : "ghost"} onClick={() => setTab(item)} role="tab" aria-selected={tab === item} className="flex-none">{item === "all" ? "全部" : item === "unread" ? "未读" : item === "read" ? "已读" : item === "saved" ? "已保存" : "已忽略"}<span className="ml-1 tabular-nums text-muted-foreground">{item === "all" ? matches.length : stateCount(item)}</span></Button>)}
      </div>
      {loading ? <div className="divide-y rounded-lg border" aria-label="正在加载雷达结果">{Array.from({ length: 4 }, (_, index) => <div key={index} className="space-y-3 p-5"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-4 w-1/3" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /></div>)}</div> : filtered.length === 0 ? <div className="flex min-h-64 items-center justify-center rounded-lg border border-dashed p-8 text-center"><div><FileSearch className="mx-auto h-8 w-8 text-muted-foreground" /><p className="mt-3 font-medium">{matches.length ? "该状态下没有结果" : "还没有雷达结果"}</p><p className="mt-1 text-sm text-muted-foreground">{matches.length ? "切换状态查看其他论文。" : config.compute_mode === "local" ? "运行本地扫描获取候选论文。" : connectionSaved ? "获取云端结果，开始筛选论文。" : "完成上方云端连接后即可获取结果。"}</p>{matches.length === 0 && (connectionSaved || config.compute_mode === "local") && <Button className="mt-4" size="sm" onClick={runScan}>开始扫描</Button>}</div></div> : <div className="divide-y overflow-hidden rounded-lg border bg-card">{filtered.map((match) => <RadarCard key={match.id} match={match} onState={setState} />)}</div>}
    </div>
  );
}
