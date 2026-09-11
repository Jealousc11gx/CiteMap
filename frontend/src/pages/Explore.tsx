import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  BarChart3,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Compass,
  ExternalLink,
  Loader2,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { useProject } from "@/contexts/ProjectContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorAlert } from "@/components/ErrorAlert";
import { Skeleton } from "@/components/ui/skeleton";
import {
  analyzeExploreCandidate,
  analyzePendingExplore,
  fetchExploreCandidates,
  fetchExploreDigest,
  fetchExploreProfiles,
  fetchExploreTrends,
  scanExplore,
  updateExploreTriage,
} from "@/services/api";
import type { ExploreCandidate, ExploreDigest, ExploreProfile, ExploreTriageStatus, ExploreTrends } from "@/types";

type ExploreTab = "digest" | "pool";
type SourceFilter = "all" | string;
type TopicFilter = "all" | string;
type TriageFilter = "all" | ExploreTriageStatus;

const SOURCE_LABELS: Record<string, string> = {
  arxiv: "arXiv",
  hf_daily: "Hugging Face",
  arxiv_authors: "关注作者",
  openreview: "OpenReview",
};

const TRIAGE_LABELS: Record<ExploreTriageStatus, string> = {
  unreviewed: "未整理",
  read: "已读",
  later: "稍后处理",
  ignored: "已忽略",
  project: "已加入项目",
};

function sourceLabel(source: string) {
  return SOURCE_LABELS[source] || source;
}

function dateLabel(value?: string | null) {
  return value ? value.slice(0, 10) : "日期未知";
}

function shortText(value: string, length = 180) {
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function candidateSources(candidate: ExploreCandidate) {
  return candidate.sources.length ? candidate.sources.map((source) => sourceLabel(source.source)).join(" · ") : "arXiv";
}

function FilterSelect({ label, value, onChange, options }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      <span>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 rounded-md border border-input bg-background px-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring md:h-9"
      >
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function SourceBadges({ candidate }: { candidate: ExploreCandidate }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {candidate.sources.map((source) => (
        <Badge key={source.source} variant="outline" className="font-normal">
          {sourceLabel(source.source)}
        </Badge>
      ))}
      {candidate.sources.length > 1 && <span className="text-xs text-emerald-600 dark:text-emerald-400">多源交叉</span>}
    </div>
  );
}

function SpotlightRow({ candidate, onOpen }: { candidate: ExploreCandidate; onOpen: (candidate: ExploreCandidate) => void }) {
  return (
    <button type="button" onClick={() => onOpen(candidate)} className="group w-full border-b border-border/70 py-4 text-left last:border-b-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-medium leading-6 group-hover:text-primary">{candidate.title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{shortText(candidate.abstract, 150)}</p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>{candidate.topic || "未分类"}</span>
            <span>{candidateSources(candidate)}</span>
            <span>{dateLabel(candidate.published_date)}</span>
          </div>
        </div>
        <ArrowUpRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
      </div>
    </button>
  );
}

function CandidateRow({ candidate, busy, onOpen, onTriage }: {
  candidate: ExploreCandidate;
  busy: boolean;
  onOpen: (candidate: ExploreCandidate) => void;
  onTriage: (candidate: ExploreCandidate, status: ExploreTriageStatus) => void;
}) {
  return (
    <div className="border-b border-border/70 px-1 py-5 last:border-b-0">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <button type="button" onClick={() => onOpen(candidate)} className="group min-w-0 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{candidate.topic || "未归桶"}</Badge>
            <Badge variant="outline" className="font-normal">
              {candidate.relevance_score == null ? "待判断" : candidate.gate_status === "rejected" ? "已排除" : `相关性 ${candidate.relevance_score}/10`}
            </Badge>
            <Badge variant="outline" className="font-normal">热度 {candidate.heat_score.toFixed(0)}</Badge>
            {candidate.triage_status !== "unreviewed" && <Badge variant="outline" className="font-normal">{TRIAGE_LABELS[candidate.triage_status]}</Badge>}
          </div>
          <h3 className="mt-2 text-base font-semibold leading-6 group-hover:text-primary">{candidate.title}</h3>
          {candidate.title_zh && <p className="mt-1 text-sm text-muted-foreground">{candidate.title_zh}</p>}
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{shortText(candidate.abstract)}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted-foreground">
            <SourceBadges candidate={candidate} />
            <span>{dateLabel(candidate.published_date)}</span>
            <span>{candidate.arxiv_id}</span>
          </div>
        </button>
        <div className="flex shrink-0 flex-wrap items-center gap-2 lg:max-w-[240px] lg:justify-end">
          <Button size="sm" variant="outline" onClick={() => onTriage(candidate, "later")} disabled={busy || candidate.triage_status === "later"}>
            {busy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Clock3 className="mr-1.5 h-3.5 w-3.5" />}稍后处理
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onTriage(candidate, "ignored")} disabled={busy || candidate.triage_status === "ignored"}>
            <X className="mr-1.5 h-3.5 w-3.5" />忽略
          </Button>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, emphasized = false }: { label: string; value: number; emphasized?: boolean }) {
  return (
    <div className="min-w-0 py-3">
      <p className={`font-mono text-lg font-semibold tabular-nums sm:text-xl ${emphasized ? "text-primary" : "text-foreground"}`}>{value}</p>
      <p className="mt-0.5 text-[11px] text-muted-foreground sm:text-xs">{label}</p>
    </div>
  );
}

function DistributionPanel({ title, summary, items, defaultOpen }: {
  title: string;
  summary: string;
  items: Array<[string, number]>;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className="group rounded-lg border bg-card">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span>{title}</span>
        <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
          {summary}
          <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
        </span>
      </summary>
      <div className="space-y-3 border-t px-4 py-4">
        {items.length ? items.map(([label, count]) => (
          <div key={label} className="flex items-center justify-between gap-3 text-sm"><span className="truncate">{label}</span><span className="tabular-nums text-muted-foreground">{count} 篇</span></div>
        )) : <p className="text-sm text-muted-foreground">无</p>}
      </div>
    </details>
  );
}

function TrendSummary({ trends }: { trends: ExploreTrends | null }) {
  const topics = Object.entries(trends?.topics || {}).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const max = Math.max(1, ...topics.map(([, count]) => count));
  return (
    <section className="rounded-lg border bg-card px-4 py-4">
      <div className="flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">近 {trends?.days || 30} 日主题</h2>
      </div>
      {topics.length ? <div className="mt-4 space-y-3">{topics.map(([topic, count]) => (
        <div key={topic}>
          <div className="flex items-center justify-between gap-3 text-xs"><span className="truncate">{topic}</span><span className="tabular-nums text-muted-foreground">{count}</span></div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary/75" style={{ width: `${Math.max(8, (count / max) * 100)}%` }} /></div>
        </div>
      ))}</div> : <p className="mt-3 text-sm text-muted-foreground">暂无历史数据</p>}
    </section>
  );
}

function DigestView({ digest, trends, onOpen, onGoPool, onManageAuthors }: {
  digest: ExploreDigest | null;
  trends: ExploreTrends | null;
  onOpen: (candidate: ExploreCandidate) => void;
  onGoPool: () => void;
  onManageAuthors: () => void;
}) {
  if (!digest) return <EmptyState title="还没有今日数据" description="采集新论文后，这里会生成当天的论文速览。" />;
  const selected = digest.buckets.flatMap((bucket) => bucket.papers);
  const topics = Object.entries(digest.topic_counts).sort((a, b) => b[1] - a[1]);
  const sources = Object.entries(digest.source_counts).sort((a, b) => b[1] - a[1]).map(([source, count]) => [sourceLabel(source), count] as [string, number]);
  const hasSelection = digest.highlighted_count > 0;
  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
      <Card>
        <CardContent className="px-0 py-0">
          <div className="grid grid-cols-3 divide-x">
            <section className="flex min-h-40 min-w-0 flex-col p-4 sm:p-5">
              <BookOpen className="h-4 w-4 text-primary" />
              <p className="mt-3 truncate text-sm font-semibold tabular-nums sm:text-base">{digest.digest_date}</p>
              <p className="mt-1 text-xs text-muted-foreground">每日论文速览</p>
            </section>
            <section className="flex min-h-40 min-w-0 flex-col p-4 sm:p-5">
              <UserRound className="h-4 w-4 text-primary" />
              <div className="mt-3 flex min-w-0 items-center gap-2"><h2 className="min-w-0 text-sm font-semibold sm:text-base">关注作者</h2><span className="text-sm tabular-nums text-muted-foreground">{digest.watched_count}</span></div>
              <p className="mt-1 text-xs text-muted-foreground">{digest.watched_count ? "篇新论文" : "今天无更新"}</p>
              <button type="button" onClick={onManageAuthors} className="mt-auto w-fit text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">管理订阅</button>
            </section>
            <section className="flex min-h-40 min-w-0 flex-col p-4 sm:p-5">
              <Sparkles className="h-4 w-4 text-primary" />
              <div className="mt-3 flex min-w-0 items-center gap-2"><h2 className="min-w-0 text-sm font-semibold sm:text-base">主题精选</h2><span className="text-sm tabular-nums text-muted-foreground">{digest.highlighted_count}</span></div>
              <p className="mt-1 text-xs text-muted-foreground">{digest.highlighted_count ? "篇值得阅读" : "今天无精选"}</p>
              <button type="button" onClick={onGoPool} className="mt-auto w-fit text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">查看候选</button>
            </section>
          </div>
          {(digest.watched.length > 0 || selected.length > 0) && <div className="border-t px-5 py-1 sm:px-6">
            {digest.watched.map((candidate) => <SpotlightRow key={`watched-${candidate.id}`} candidate={candidate} onOpen={onOpen} />)}
            {selected.map((candidate) => <SpotlightRow key={`selected-${candidate.id}`} candidate={candidate} onOpen={onOpen} />)}
          </div>}
        </CardContent>
      </Card>
      <aside className="space-y-4 lg:sticky lg:top-6">
        <section className="rounded-lg border bg-card px-4 py-4">
          <div className="flex items-center justify-between gap-3"><h2 className="text-sm font-semibold">今日进度</h2><span className="text-xs text-muted-foreground">{digest.digest_date}</span></div>
          <div className="mt-2 grid grid-cols-2 divide-x border-y [&>*:nth-child(even)]:pl-4 [&>*:nth-child(n+3)]:border-t">
            <Metric label="已采集" value={digest.scanned_count} />
            <Metric label="待判断" value={digest.pending_count} emphasized={digest.pending_count > 0} />
            <Metric label="主题精选" value={digest.highlighted_count} />
            <Metric label="作者更新" value={digest.watched_count} />
          </div>
          {digest.pending_count > 0 && <Button variant="ghost" size="sm" className="mt-2 w-full justify-between px-0" onClick={onGoPool}>处理待判断论文 <ArrowUpRight className="h-3.5 w-3.5" /></Button>}
        </section>
        <TrendSummary trends={trends} />
        <DistributionPanel key={`topics-${digest.digest_date}-${hasSelection}`} title="主题分布" summary={hasSelection ? `${digest.highlighted_count} 篇精选` : "无"} items={topics} defaultOpen={hasSelection} />
        <DistributionPanel key={`sources-${digest.digest_date}-${hasSelection}`} title="来源分布" summary={hasSelection ? `${digest.scanned_count} 篇采集` : "无推荐"} items={sources} defaultOpen={hasSelection} />
      </aside>
    </div>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="flex min-h-56 items-center justify-center rounded-lg border border-dashed p-8 text-center"><div><Compass className="mx-auto h-8 w-8 text-muted-foreground" /><p className="mt-3 font-medium">{title}</p><p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p></div></div>;
}

export function Explore() {
  const { activeProject } = useProject();
  const navigate = useNavigate();
  const [tab, setTab] = useState<ExploreTab>("digest");
  const [profile, setProfile] = useState<ExploreProfile | null>(null);
  const [digest, setDigest] = useState<ExploreDigest | null>(null);
  const [trends, setTrends] = useState<ExploreTrends | null>(null);
  const [candidates, setCandidates] = useState<ExploreCandidate[]>([]);
  const [source, setSource] = useState<SourceFilter>("all");
  const [topic, setTopic] = useState<TopicFilter>("all");
  const [triage, setTriage] = useState<TriageFilter>("unreviewed");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [candidateLimit, setCandidateLimit] = useState(30);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ExploreCandidate | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const load = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const profiles = await fetchExploreProfiles();
      const current = profiles.find((item) => item.id === "explore_default") || profiles[0] || null;
      setProfile(current);
      const profileId = current?.id || "explore_default";
      const [nextDigest, nextTrends, nextCandidates] = await Promise.all([
        fetchExploreDigest(profileId),
        fetchExploreTrends(profileId),
        fetchExploreCandidates({ profileId, source, topic, triageStatus: triage === "all" ? undefined : triage, query: debouncedQuery, limit: candidateLimit }),
      ]);
      setDigest(nextDigest);
      setTrends(nextTrends);
      setCandidates(nextCandidates);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [candidateLimit, debouncedQuery, source, topic, triage]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => { setCandidateLimit(30); }, [debouncedQuery, source, topic, triage]);

  const topics = useMemo(() => Object.keys(trends?.topics || {}).sort(), [trends]);
  const sources = useMemo(() => Array.from(new Set(["arxiv", "hf_daily", ...Object.keys(digest?.source_counts || {})])).sort(), [digest]);

  const handleScan = async () => {
    setSyncing(true);
    setNotice(null);
    try {
      await scanExplore(profile?.id || "explore_default");
      await load(false);
      setNotice("采集完成，候选论文已更新");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSyncing(false);
    }
  };

  const handleTriage = async (candidate: ExploreCandidate, status: ExploreTriageStatus) => {
    if (status === "project" && (!activeProject || activeProject.is_system)) {
      setError("请先在顶部切换到一个研究项目，再加入项目");
      return;
    }
    setBusyId(candidate.id);
    try {
      await updateExploreTriage(candidate.id, status, status === "project" ? activeProject?.id : undefined, false, profile?.id);
      setSelected(null);
      await load(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  const handleAnalyzePending = async () => {
    setAnalyzing(true);
    setNotice(null);
    try {
      await analyzePendingExplore(profile?.id || "explore_default", 20);
      await load(false);
      setNotice("待处理候选分析完成");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAnalyzing(false);
    }
  };

  const handleAnalyze = async (candidate: ExploreCandidate) => {
    setBusyId(candidate.id);
    try {
      const analyzed = await analyzeExploreCandidate(
        candidate.id,
        profile?.id || "explore_default",
      );
      setSelected(analyzed);
      await load(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-5">
      <div className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="workspace-heading flex items-center gap-2"><Compass className="h-5 w-5 text-primary" />探索</h1>
          <p className="workspace-description mt-1">
            {profile?.name ? `围绕“${profile.name}”发现值得关注的新论文，确认后再加入研究项目。` : "发现值得关注的新论文，确认后再加入研究项目。"}
          </p>
          {profile && <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium">当前主题：{profile.name}</span>
            {profile.categories.map((category) => <Badge key={category} variant="outline" className="font-normal">{category}</Badge>)}
            {profile.include_keywords.length > 0 && <span className="text-muted-foreground">{profile.include_keywords.length} 个重点关键词</span>}
            <button type="button" onClick={() => navigate("/settings?tab=explore#explore-topic-settings")} className="inline-flex items-center gap-1 rounded-sm px-1.5 py-1 font-medium text-primary hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <Settings2 className="h-3.5 w-3.5" />设置主题
            </button>
          </div>}
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          <Button variant="outline" onClick={handleScan} disabled={syncing || analyzing} className="min-w-0">
            <RefreshCw className={`mr-2 h-4 w-4 ${syncing ? "animate-spin" : ""}`} />{syncing ? "采集中" : "采集新论文"}
          </Button>
          <Button onClick={handleAnalyzePending} disabled={syncing || analyzing} className="min-w-0">
            {analyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}{analyzing ? "分析中" : "判断新论文"}
          </Button>
        </div>
      </div>

      {error && <ErrorAlert message={error} onRetry={() => void load()} />}
      {notice && <div className="flex items-center gap-2 rounded-md border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300" role="status"><CheckCircle2 className="h-4 w-4" />{notice}<button className="ml-auto rounded p-1 hover:bg-emerald-500/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={() => setNotice(null)} aria-label="关闭提示"><X className="h-3.5 w-3.5" /></button></div>}

      <Tabs value={tab} onValueChange={(value) => setTab(value as ExploreTab)}>
        <TabsList className="w-full sm:w-fit"><TabsTrigger value="digest">今日</TabsTrigger><TabsTrigger value="pool">候选论文</TabsTrigger></TabsList>
        <TabsContent value="digest" className="mt-5">{loading ? <LoadingState /> : <DigestView digest={digest} trends={trends} onOpen={setSelected} onGoPool={() => setTab("pool")} onManageAuthors={() => navigate("/settings?tab=explore")} />}</TabsContent>
        <TabsContent value="pool" className="mt-5">
          <Card>
            <CardHeader className="border-b pb-5"><div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between"><div><CardTitle>候选论文</CardTitle><CardDescription className="mt-1">{loading ? "正在更新" : `当前显示 ${candidates.length} 篇`}</CardDescription></div><div className="flex flex-wrap items-center gap-2"><FilterSelect label="来源" value={source} onChange={(value) => setSource(value)} options={[{ value: "all", label: "全部来源" }, ...sources.map((item) => ({ value: item, label: sourceLabel(item) }))]} /><FilterSelect label="主题" value={topic} onChange={(value) => setTopic(value)} options={[{ value: "all", label: "全部主题" }, ...topics.map((item) => ({ value: item, label: item }))]} /><FilterSelect label="状态" value={triage} onChange={(value) => setTriage(value as TriageFilter)} options={[{ value: "all", label: "全部状态" }, ...Object.entries(TRIAGE_LABELS).map(([value, label]) => ({ value, label }))]} /></div></div><div className="relative max-w-md"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题或摘要" className="pl-9" /></div></CardHeader>
            <CardContent className="pt-1">
              {loading ? <LoadingState /> : candidates.length ? <>
                {candidates.map((candidate) => <CandidateRow key={candidate.id} candidate={candidate} busy={busyId === candidate.id} onOpen={setSelected} onTriage={(item, status) => void handleTriage(item, status)} />)}
                {candidates.length >= candidateLimit && candidateLimit < 100 && <div className="flex justify-center border-t py-4"><Button type="button" variant="outline" size="sm" onClick={() => setCandidateLimit((current) => Math.min(100, current + 30))}>{candidateLimit >= 90 ? "再显示 10 篇" : "再显示 30 篇"}</Button></div>}
              </> : <EmptyState title="没有候选论文" description="调整筛选条件，或采集一次新论文。" />}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-2xl">
          {selected && <>
            <DialogHeader><DialogTitle className="pr-6 leading-6">{selected.title}</DialogTitle><DialogDescription>{selected.arxiv_id} · {dateLabel(selected.published_date)} · {selected.topic || "未分类"}</DialogDescription></DialogHeader>
            <div className="space-y-5 overflow-y-auto text-sm">
              <SourceBadges candidate={selected} />
              <p className="leading-7 text-muted-foreground">{selected.abstract}</p>
              {selected.summary_zh && (
                <div className="rounded-md bg-muted/60 p-4">
                  <p className="font-medium">双语摘要</p>
                  <p className="mt-2 leading-7">{selected.summary_zh}</p>
                  <p className="mt-2 leading-6 text-muted-foreground">{selected.summary_en}</p>
                </div>
              )}
              <div className="grid gap-3 rounded-md bg-muted/50 p-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-muted-foreground">相关性判断</p>
                  <p className="mt-1">
                    {selected.relevance_score == null ? "等待分析" : <>{selected.relevance_score}/10 · {selected.topic || "未归桶"}</>}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">热度与综合分</p>
                  <p className="mt-1">{selected.heat_score.toFixed(1)} · 综合 {selected.ranking_score.toFixed(1)}</p>
                </div>
                <div className="sm:col-span-2">
                  <p className="text-xs text-muted-foreground">判断依据</p>
                  <p className="mt-1 leading-6">{selected.judge_reason || "等待判断"}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => void handleAnalyze(selected)} disabled={busyId === selected.id}>
                  <Sparkles className="mr-1.5 h-3.5 w-3.5" />{busyId === selected.id ? "分析中" : "判断相关性并生成双语摘要"}
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <a href={selected.arxiv_url} target="_blank" rel="noreferrer"><ExternalLink className="mr-1.5 h-3.5 w-3.5" />打开原文</a>
                </Button>
              </div>
            </div>
            <DialogFooter className="flex-wrap sm:justify-between"><span className="text-xs text-muted-foreground">目标：{activeProject?.is_system ? "请先选择研究项目" : activeProject?.name || "未选择项目"}</span><div className="flex gap-2"><Button variant="outline" onClick={() => void handleTriage(selected, "later")} disabled={busyId === selected.id}><Clock3 className="mr-1.5 h-4 w-4" />稍后处理</Button><Button onClick={() => void handleTriage(selected, "project")} disabled={Boolean(busyId === selected.id || !activeProject || activeProject.is_system)}><CheckCircle2 className="mr-1.5 h-4 w-4" />加入项目</Button></div></DialogFooter>
          </>}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function LoadingState() {
  return <div className="space-y-4 py-4" aria-label="正在加载探索内容">{Array.from({ length: 4 }, (_, index) => <div key={index} className="space-y-2 border-b pb-4 last:border-0"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /></div>)}</div>;
}
