import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, Radar as RadarIcon, RefreshCw, Save, Settings2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
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
import { useProject } from "@/contexts/ProjectContext";
import { fetchRadarConfig, fetchRadarMatches, scanRadar, syncRadar, updateRadarConfig, updateRadarMatch } from "@/services/api";
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
const RADAR_CONNECTION_KEY = "citemap.radar.connection.v1";
const RADAR_DEPLOYMENT_GUIDE_URL = "https://github.com/Jealousc11gx/CiteMap/blob/main/docs/radar-github-action-setup.md";

type RadarConnection = {
  remoteUrl: string;
  remoteToken: string;
};

const RADAR_STATE_LABELS: Record<RadarState, string> = {
  unread: "未读",
  read: "已读",
  saved: "已保存",
  dismissed: "已忽略",
};

function loadRadarConnection(): RadarConnection {
  try {
    const connection = JSON.parse(localStorage.getItem(RADAR_CONNECTION_KEY) || "{}");
    const legacy = JSON.parse(localStorage.getItem("citemap.radar.setup.v1") || "{}");
    return {
      remoteUrl: connection.remote_url || legacy.remote_url || localStorage.getItem("citemap.radar.remoteUrl") || "",
      remoteToken: connection.remote_token || legacy.remote_token || "",
    };
  } catch {
    return {
      remoteUrl: localStorage.getItem("citemap.radar.remoteUrl") || "",
      remoteToken: "",
    };
  }
}

function saveRadarConnection(remoteUrl: string, remoteToken: string) {
  localStorage.setItem(RADAR_CONNECTION_KEY, JSON.stringify({
    remote_url: remoteUrl,
    remote_token: remoteToken,
  }));
  localStorage.setItem("citemap.radar.remoteUrl", remoteUrl);
}

function splitValues(value: string) {
  return value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean);
}

function validateCategories(categories: string[]): string | null {
  const prefixes = new Set(["cs", "econ", "eess", "hep-ex", "hep-lat", "hep-ph", "hep-th", "math", "nlin", "nucl-ex", "nucl-th", "physics", "q-bio", "q-fin", "quant-ph", "stat", "astro-ph", "cond-mat", "gr-qc"]);
  const invalid = categories.filter((category) => {
    const [prefix, suffix] = category.split(".", 2);
    return !prefix || !suffix || !prefixes.has(prefix.toLowerCase()) || !/^[A-Za-z0-9-]+$/.test(suffix);
  });
  return invalid.length ? `无效的 arXiv categories：${invalid.join(", ")}。示例：cs.AI、cs.CV、stat.ML` : null;
}

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
    <article className="rounded-xl border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <a href={match.arxiv_url} target="_blank" rel="noreferrer" className="text-base font-semibold hover:underline">
            {match.title}
          </a>
          <p className="mt-1 text-xs text-muted-foreground">{match.arxiv_id} · {match.published_date || "未知日期"} · score {match.score.toFixed(3)}</p>
        </div>
        <span className="rounded-full bg-muted px-2 py-1 text-xs">{RADAR_STATE_LABELS[match.state]}</span>
      </div>
      {match.title_zh && <p className="mt-2 text-sm font-medium">{match.title_zh}</p>}
      {!!match.affiliations?.length && <p className="mt-2 text-xs text-muted-foreground">机构：{match.affiliations.join(" · ")}</p>}
      {!!match.corresponding_authors?.length && <p className="mt-1 text-xs text-muted-foreground">通讯作者：{match.corresponding_authors.join("、")}</p>}
      {match.tldr && <p className="mt-3 text-sm leading-6"><span className="font-medium">TLDR：</span>{match.tldr}</p>}
      <p className="mt-3 line-clamp-4 text-sm leading-6 text-muted-foreground">{match.ai_summary || match.abstract_zh || match.abstract || "暂无摘要"}</p>
      <p className="mt-3 text-xs text-muted-foreground">{match.reason || "项目语义相似度"}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={busy || !canMarkRead} onClick={() => apply("read")}>{isRead ? "已读" : "标记已读"}</Button>
        <Button size="sm" disabled={busy || !canSave} onClick={() => apply("saved")}><Save className="mr-1 h-3.5 w-3.5" />{match.state === "saved" ? "已保存" : "保存入库"}</Button>
        <Button size="sm" variant="ghost" disabled={busy || !canDismiss} onClick={() => apply("dismissed")}><X className="mr-1 h-3.5 w-3.5" />{match.state === "dismissed" ? "已忽略" : "忽略"}</Button>
      </div>
    </article>
  );
}

export function Radar() {
  const { activeProject } = useProject();
  const isSystemProject = Boolean(activeProject?.is_system);
  const projectId = activeProject?.id;
  const [config, setConfig] = useState(EMPTY_CONFIG);
  const [matches, setMatches] = useState<RadarMatch[]>([]);
  const [tab, setTab] = useState<"all" | RadarState>("all");
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [remoteUrl, setRemoteUrl] = useState(() => loadRadarConnection().remoteUrl);
  const [remoteToken, setRemoteToken] = useState(() => loadRadarConnection().remoteToken);
  const [connectionSaved, setConnectionSaved] = useState(() => {
    const connection = loadRadarConnection();
    return Boolean(connection.remoteUrl && connection.remoteToken);
  });
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [nextConfig, nextMatches] = await Promise.all([fetchRadarConfig(projectId), fetchRadarMatches(projectId)]);
      setConfig({ ...nextConfig, categories: nextConfig.categories.length ? nextConfig.categories : ["cs.AI"] });
      setMatches(nextMatches);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => tab === "all" ? matches : matches.filter((match) => match.state === tab), [matches, tab]);

  const saveConfig = async () => {
    if (!projectId) return;
    const categoryError = validateCategories(config.categories);
    if (categoryError) {
      setError(categoryError);
      return;
    }
    setSavingConfig(true);
    try {
      const updated = await updateRadarConfig(projectId, config);
      setConfig(updated);
      setShowSettings(false);
      if (connectionSaved && remoteUrl.trim() && remoteToken.trim()) {
        await syncRadar(projectId, remoteUrl.trim(), remoteToken.trim(), true, true);
        setNotice("设置已保存并发布到云端。运行 GitHub Action 完成计算，再点击“获取云端结果”。");
      } else {
        setNotice("设置已保存。连接 Worker 后发布项目配置，才能进行云端计算。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingConfig(false);
    }
  };

  const runScan = async () => {
    if (!projectId) return;
    setScanning(true);
    setError(null);
    try {
      if (config.compute_mode === "cloud") {
        if (!connectionSaved || !remoteUrl.trim() || !remoteToken.trim()) throw new Error("请先连接 Worker，再获取云端结果");
        const result = await syncRadar(projectId, remoteUrl.trim(), remoteToken.trim(), false, false);
        setNotice(`已获取云端结果，新增 ${result.synced.applied || 0} 条。`);
      } else if (config.compute_mode === "hybrid") {
        try {
          if (!connectionSaved || !remoteUrl.trim() || !remoteToken.trim()) throw new Error("未配置云端连接");
          const result = await syncRadar(projectId, remoteUrl.trim(), remoteToken.trim(), false, false);
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

  const runSync = async () => {
    if (!projectId) return;
    if (!remoteUrl.trim() || !remoteToken.trim()) {
      setError("请填写 Worker URL 和 RADAR_TOKEN");
      return;
    }
    setSyncing(true);
    setError(null);
    setNotice(null);
    try {
      await syncRadar(projectId, remoteUrl.trim(), remoteToken.trim(), true, true);
      saveRadarConnection(remoteUrl.trim(), remoteToken.trim());
      setConnectionSaved(true);
      setNotice("项目配置已发布到云端。请运行 GitHub Action 完成计算，再点击“获取云端结果”。");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSyncing(false);
    }
  };

  const setState = async (match: RadarMatch, state: RadarState) => {
    try {
      const updated = await updateRadarMatch(match.id, state);
      setMatches((items) => items.map((item) => item.id === match.id ? { ...item, ...updated } : item));
      if (connectionSaved && projectId && remoteUrl.trim() && remoteToken.trim()) {
        syncRadar(projectId, remoteUrl.trim(), remoteToken.trim()).catch((err) => {
          setError(err instanceof Error ? err.message : String(err));
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (!activeProject) return <div className="p-6 text-muted-foreground">请先选择研究项目。</div>;

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2"><RadarIcon className="h-5 w-5 text-primary" /><h1 className="text-2xl font-semibold">论文雷达</h1></div>
          <p className="mt-1 text-sm text-muted-foreground">{activeProject.name} · 未保存候选不会进入正式论文库</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowSettings((value) => !value)}><Settings2 className="mr-2 h-4 w-4" />设置</Button>
          <Button onClick={runScan} disabled={scanning}>{scanning ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}{config.compute_mode === "local" ? "运行本地扫描" : "获取云端结果"}</Button>
        </div>
      </div>
      <Dialog open={Boolean(error)} onOpenChange={(open) => { if (!open) setError(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-destructive/10 text-destructive"><AlertTriangle className="h-5 w-5" /></div>
            <DialogTitle>雷达操作失败</DialogTitle>
            <DialogDescription className="max-h-[50vh] overflow-y-auto break-words pt-1 leading-6 text-foreground">{error}</DialogDescription>
          </DialogHeader>
          <DialogFooter><Button variant="outline" onClick={() => setError(null)}>关闭</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      {notice && <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm text-primary" role="status"><CheckCircle2 className="h-4 w-4 shrink-0" />{notice}</div>}
      {!connectionSaved && !showSettings && (
        <section className="border-y bg-muted/30 px-4 py-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold">连接云端雷达</h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">Fork 仓库并完成 GitHub Actions 部署后，在此连接 Worker。模型、SMTP、Cloudflare 凭据只配置在 GitHub。</p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <label className="space-y-1.5 text-xs font-medium"><span>Worker URL</span><Input value={remoteUrl} onChange={(event) => setRemoteUrl(event.target.value)} placeholder="https://citemap-radar.example.workers.dev" /></label>
                <label className="space-y-1.5 text-xs font-medium"><span>RADAR_TOKEN</span><Input type="password" value={remoteToken} onChange={(event) => setRemoteToken(event.target.value)} placeholder="与 GitHub Secret 相同" /></label>
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button variant="outline" asChild><a href={RADAR_DEPLOYMENT_GUIDE_URL} target="_blank" rel="noreferrer">部署文档<ExternalLink className="ml-2 h-4 w-4" /></a></Button>
              <Button onClick={runSync} disabled={syncing}>{syncing ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : null}{syncing ? "发布中" : "连接并发布项目"}</Button>
            </div>
          </div>
        </section>
      )}
      {showSettings && (
        <section className="space-y-4 rounded-xl border bg-card p-4">
          <div>
            <label className={`flex items-center gap-2 text-sm ${isSystemProject ? "text-muted-foreground" : ""}`}>
              <input
                type="checkbox"
                checked={config.enabled}
                disabled={isSystemProject}
                onChange={(event) => setConfig({ ...config, enabled: event.target.checked })}
              />
              启用当前项目雷达
            </label>
            {isSystemProject && <p className="mt-1 text-xs leading-5 text-muted-foreground">未分类项目不能启用雷达。请新建研究项目，将论文加入该项目后再配置。</p>}
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1 text-sm"><span>arXiv categories</span><Input value={config.categories.join(", ")} onChange={(event) => setConfig({ ...config, categories: splitValues(event.target.value) })} placeholder="cs.AI, cs.CV" /></label>
            <label className="space-y-1 text-sm"><span>关注关键词</span><Input value={config.include_keywords.join(", ")} onChange={(event) => setConfig({ ...config, include_keywords: splitValues(event.target.value) })} placeholder="retrieval, multimodal" /><span className="block text-xs leading-5 text-muted-foreground">标题或摘要命中任一词后才进入语义排序；留空不过滤。</span></label>
            <label className="space-y-1 text-sm"><span>排除关键词</span><Input value={config.exclude_keywords.join(", ")} onChange={(event) => setConfig({ ...config, exclude_keywords: splitValues(event.target.value) })} placeholder="medical" /><span className="block text-xs leading-5 text-muted-foreground">标题或摘要命中任一词即排除，优先级高于关注关键词。</span></label>
            <div className="grid grid-cols-2 gap-3"><label className="space-y-1 text-sm"><span>Top K</span><Input type="number" min={1} value={config.top_k} onChange={(event) => setConfig({ ...config, top_k: Number(event.target.value) })} /></label><label className="space-y-1 text-sm"><span>最低分数</span><Input type="number" step="0.01" min={0} value={config.min_score} onChange={(event) => setConfig({ ...config, min_score: Number(event.target.value) })} /></label></div>
            <div className="grid gap-3 md:grid-cols-2"><label className="space-y-1 text-sm"><span>抓取上限</span><Input type="number" min={1} max={500} value={config.fetch_limit} onChange={(event) => setConfig({ ...config, fetch_limit: Number(event.target.value) })} /></label><label className="space-y-1 text-sm"><span>计算模式</span><select className="flex h-10 w-full rounded-md border bg-background px-3 text-sm" value={config.compute_mode} onChange={(event) => setConfig({ ...config, compute_mode: event.target.value as RadarConfig["compute_mode"] })}><option value="cloud">云端计算（推荐）</option><option value="hybrid">云端优先，本地备用</option><option value="local">本地计算</option></select></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.include_cross_list} onChange={(event) => setConfig({ ...config, include_cross_list: event.target.checked })} />包含 cross-list 论文</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.send_empty} onChange={(event) => setConfig({ ...config, send_empty: event.target.checked })} />没有推荐时也发送邮件</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.debug} onChange={(event) => setConfig({ ...config, debug: event.target.checked })} />Debug 模式</label></div>
          </div>
          <label className="block space-y-1 text-sm"><span>项目研究目标补充</span><Textarea value={config.profile_override} onChange={(event) => setConfig({ ...config, profile_override: event.target.value })} placeholder="描述项目关注的研究问题" /></label>
          <div className="border-t pt-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div><p className="text-sm font-medium">云端连接</p><p className="mt-1 text-xs text-muted-foreground">这里只保存 Worker URL、RADAR_TOKEN。Actions 的模型、邮件、Cloudflare 配置不在本地管理。</p></div>
              <Button variant="ghost" size="sm" asChild><a href={RADAR_DEPLOYMENT_GUIDE_URL} target="_blank" rel="noreferrer">部署文档<ExternalLink className="ml-2 h-3.5 w-3.5" /></a></Button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="space-y-1.5 text-xs font-medium"><span>Worker URL</span><Input value={remoteUrl} onChange={(event) => { setRemoteUrl(event.target.value); setConnectionSaved(false); }} placeholder="https://citemap-radar.example.workers.dev" /></label>
              <label className="space-y-1.5 text-xs font-medium"><span>RADAR_TOKEN</span><Input type="password" value={remoteToken} onChange={(event) => { setRemoteToken(event.target.value); setConnectionSaved(false); }} placeholder="与 GitHub Secret 相同" /></label>
            </div>
            <Button variant="outline" className="mt-3" onClick={runSync} disabled={syncing}>{syncing ? "发布中…" : connectionSaved ? "重新发布项目配置" : "连接并发布项目"}</Button>
          </div>
          <Button onClick={saveConfig} disabled={savingConfig}>{savingConfig ? "保存中…" : "保存设置"}</Button>
        </section>
      )}
      <div className="flex flex-wrap gap-2 border-b pb-2">
        {(["all", "unread", "read", "saved", "dismissed"] as const).map((item) => <Button key={item} size="sm" variant={tab === item ? "default" : "ghost"} onClick={() => setTab(item)}>{item === "all" ? "全部" : item === "unread" ? "未读" : item === "read" ? "已读" : item === "saved" ? "已保存" : "已忽略"}</Button>)}
      </div>
      {loading ? <div className="py-12 text-center text-sm text-muted-foreground">加载雷达结果…</div> : filtered.length === 0 ? <div className="rounded-xl border border-dashed p-12 text-center text-sm text-muted-foreground">暂无结果。先发布项目配置，运行 GitHub Action 完成云端计算，再点击“获取云端结果”。</div> : <div className="grid gap-4 lg:grid-cols-2">{filtered.map((match) => <RadarCard key={match.id} match={match} onState={setState} />)}</div>}
    </div>
  );
}
