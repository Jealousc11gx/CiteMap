import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Radar as RadarIcon, RefreshCw, Save, Settings2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useProject } from "@/contexts/ProjectContext";
import { fetchRadarConfig, fetchRadarMatches, scanRadar, syncRadar, updateRadarConfig, updateRadarMatch } from "@/services/api";
import type { RadarConfig, RadarMatch, RadarState } from "@/types";
import { RADAR_SETUP_COMPLETE_KEY } from "@/pages/RadarSettings";
import { RADAR_CLOUD_SETUP_COMPLETE_KEY } from "@/pages/RadarCloudSettings";

const EMPTY_CONFIG: Omit<RadarConfig, "project_id" | "updated_at"> = {
  enabled: false,
  categories: [],
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

function splitValues(value: string) {
  return value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean);
}

function RadarCard({ match, onState }: { match: RadarMatch; onState: (match: RadarMatch, state: RadarState) => void }) {
  const [busy, setBusy] = useState(false);
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
        <span className="rounded-full bg-muted px-2 py-1 text-xs">{match.state}</span>
      </div>
      {match.title_zh && <p className="mt-2 text-sm font-medium">{match.title_zh}</p>}
      {match.tldr && <p className="mt-3 text-sm leading-6"><span className="font-medium">TLDR：</span>{match.tldr}</p>}
      <p className="mt-3 line-clamp-4 text-sm leading-6 text-muted-foreground">{match.ai_summary || match.abstract_zh || match.abstract || "暂无摘要"}</p>
      <p className="mt-3 text-xs text-muted-foreground">{match.reason || "项目语义相似度"}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {match.state !== "read" && match.state !== "saved" && <Button size="sm" variant="outline" disabled={busy} onClick={() => apply("read")}>标记已读</Button>}
        {match.state !== "saved" && <Button size="sm" disabled={busy} onClick={() => apply("saved")}><Save className="mr-1 h-3.5 w-3.5" />保存入库</Button>}
        {match.state !== "dismissed" && <Button size="sm" variant="ghost" disabled={busy} onClick={() => apply("dismissed")}><X className="mr-1 h-3.5 w-3.5" />忽略</Button>}
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
  const [savingConfig, setSavingConfig] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remoteUrl, setRemoteUrl] = useState(() => { try { return JSON.parse(localStorage.getItem("citemap.radar.setup.v1") || "{}").remote_url || localStorage.getItem("citemap.radar.remoteUrl") || ""; } catch { return localStorage.getItem("citemap.radar.remoteUrl") || ""; } });
  const [remoteToken, setRemoteToken] = useState(() => { try { return JSON.parse(localStorage.getItem("citemap.radar.setup.v1") || "{}").remote_token || ""; } catch { return ""; } });
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(RADAR_SETUP_COMPLETE_KEY) !== "true") navigate("/settings/radar", { replace: true });
    else if (localStorage.getItem(RADAR_CLOUD_SETUP_COMPLETE_KEY) !== "true") navigate("/settings/radar/cloud", { replace: true });
  }, [navigate]);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [nextConfig, nextMatches] = await Promise.all([fetchRadarConfig(projectId), fetchRadarMatches(projectId)]);
      setConfig(nextConfig);
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
    setSavingConfig(true);
    try {
      const updated = await updateRadarConfig(projectId, config);
      setConfig(updated);
      setShowSettings(false);
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
        if (!remoteUrl.trim() || !remoteToken.trim()) throw new Error("请先在云端配置中填写 Worker URL 和 RADAR_TOKEN");
        await syncRadar(projectId, remoteUrl.trim(), remoteToken.trim());
      } else if (config.compute_mode === "hybrid") {
        try {
          if (!remoteUrl.trim() || !remoteToken.trim()) throw new Error("未配置云端连接");
          await syncRadar(projectId, remoteUrl.trim(), remoteToken.trim());
        } catch {
          await scanRadar(projectId);
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
    if (!remoteUrl.trim() || !remoteToken.trim()) {
      setError("请先填写远端 Radar Store URL 和 token");
      return;
    }
    setSyncing(true);
    setError(null);
    try {
      localStorage.setItem("citemap.radar.remoteUrl", remoteUrl.trim());
      await syncRadar(projectId, remoteUrl.trim(), remoteToken.trim());
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
          <Button onClick={runScan} disabled={scanning}>{scanning ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}{config.compute_mode === "local" ? "本地扫描" : "同步云端推荐"}</Button>
        </div>
      </div>
      {error && <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">{error}</div>}
      {showSettings && (
        <section className="space-y-4 rounded-xl border bg-card p-4">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.enabled} onChange={(event) => setConfig({ ...config, enabled: event.target.checked })} />启用当前项目雷达</label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1 text-sm"><span>arXiv categories</span><Input value={config.categories.join(", ")} onChange={(event) => setConfig({ ...config, categories: splitValues(event.target.value) })} placeholder="cs.AI, cs.CV" /></label>
            <label className="space-y-1 text-sm"><span>关注关键词</span><Input value={config.include_keywords.join(", ")} onChange={(event) => setConfig({ ...config, include_keywords: splitValues(event.target.value) })} placeholder="retrieval, multimodal" /></label>
            <label className="space-y-1 text-sm"><span>排除关键词</span><Input value={config.exclude_keywords.join(", ")} onChange={(event) => setConfig({ ...config, exclude_keywords: splitValues(event.target.value) })} placeholder="medical" /></label>
            <div className="grid grid-cols-2 gap-3"><label className="space-y-1 text-sm"><span>Top K</span><Input type="number" min={1} value={config.top_k} onChange={(event) => setConfig({ ...config, top_k: Number(event.target.value) })} /></label><label className="space-y-1 text-sm"><span>最低分数</span><Input type="number" step="0.01" min={0} value={config.min_score} onChange={(event) => setConfig({ ...config, min_score: Number(event.target.value) })} /></label></div>
            <div className="grid gap-3 md:grid-cols-2"><label className="space-y-1 text-sm"><span>抓取上限</span><Input type="number" min={1} max={500} value={config.fetch_limit} onChange={(event) => setConfig({ ...config, fetch_limit: Number(event.target.value) })} /></label><label className="space-y-1 text-sm"><span>计算模式</span><select className="flex h-10 w-full rounded-md border bg-background px-3 text-sm" value={config.compute_mode} onChange={(event) => setConfig({ ...config, compute_mode: event.target.value as RadarConfig["compute_mode"] })}><option value="cloud">云端计算（推荐）</option><option value="hybrid">云端优先，本地备用</option><option value="local">本地计算</option></select></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.include_cross_list} onChange={(event) => setConfig({ ...config, include_cross_list: event.target.checked })} />包含 cross-list 论文</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.send_empty} onChange={(event) => setConfig({ ...config, send_empty: event.target.checked })} />没有推荐时也发送邮件</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.debug} onChange={(event) => setConfig({ ...config, debug: event.target.checked })} />Debug 模式</label></div>
          </div>
          <label className="block space-y-1 text-sm"><span>项目研究目标补充</span><Textarea value={config.profile_override} onChange={(event) => setConfig({ ...config, profile_override: event.target.value })} placeholder="描述项目关注的研究问题" /></label>
          <div className="border-t pt-4">
            <p className="mb-2 text-sm font-medium">远端雷达同步</p>
            <p className="mb-3 text-xs text-muted-foreground">用于电脑关闭期间保存每日推荐、邮件点击状态。token 仅保存在当前浏览器内存，不写入 CiteMap 数据库。</p>
            <div className="grid gap-3 md:grid-cols-2">
              <Input value={remoteUrl} onChange={(event) => setRemoteUrl(event.target.value)} placeholder="https://your-radar-worker.example.com" />
              <Input type="password" value={remoteToken} onChange={(event) => setRemoteToken(event.target.value)} placeholder="Radar Store token" />
            </div>
            <Button variant="outline" className="mt-3" onClick={runSync} disabled={syncing}>{syncing ? "同步中…" : "同步远端历史并发布项目画像"}</Button>
          </div>
          <Button onClick={saveConfig} disabled={savingConfig}>{savingConfig ? "保存中…" : "保存设置"}</Button>
        </section>
      )}
      <div className="flex flex-wrap gap-2 border-b pb-2">
        {(["all", "unread", "read", "saved", "dismissed"] as const).map((item) => <Button key={item} size="sm" variant={tab === item ? "default" : "ghost"} onClick={() => setTab(item)}>{item === "all" ? "全部" : item === "unread" ? "未读" : item === "read" ? "已读" : item === "saved" ? "已保存" : "已忽略"}</Button>)}
      </div>
      {loading ? <div className="py-12 text-center text-sm text-muted-foreground">加载雷达结果…</div> : filtered.length === 0 ? <div className="rounded-xl border border-dashed p-12 text-center text-sm text-muted-foreground">暂无云端结果。先运行 GitHub Action，再点击“同步云端推荐”。</div> : <div className="grid gap-4 lg:grid-cols-2">{filtered.map((match) => <RadarCard key={match.id} match={match} onState={setState} />)}</div>}
    </div>
  );
}
