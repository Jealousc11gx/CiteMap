import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, Check, ChevronDown, Cloud, Compass, Eye, EyeOff, Info, Loader2, Radar as RadarIcon, Save, Trash2, UserRound } from "lucide-react";
import { useProject } from "@/contexts/ProjectContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ErrorAlert } from "@/components/ErrorAlert";
import { Skeleton } from "@/components/ui/skeleton";
import {
  fetchAppSettings,
  fetchExploreProfiles,
  fetchPapers,
  fetchRadarConfig,
  fetchRadarConnection,
  updateAppSettings,
  updateExploreProfile,
  updateRadarConfig,
  updateRadarConnection,
} from "@/services/api";
import type { AppSettings, ExploreProfile, Paper, RadarConfig, RadarConnection } from "@/types";

type SettingsSection = "ai" | "explore" | "radar" | "integrations";

const SETTINGS_SECTIONS: Array<{ id: SettingsSection; label: string; icon: typeof Bot }> = [
  { id: "ai", label: "AI", icon: Bot },
  { id: "explore", label: "探索", icon: Compass },
  { id: "radar", label: "雷达", icon: RadarIcon },
  { id: "integrations", label: "集成", icon: Cloud },
];

const EMPTY_RADAR_CONFIG: Omit<RadarConfig, "project_id" | "updated_at"> = {
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

const AI_NAMES = ["LLM_BASE_URL", "LLM_MODEL", "LLM_PROVIDER_TYPE", "LLM_CAPABILITIES", "LLM_MAX_CONTEXT_SIZE"];
const EXPLORE_NAMES = [
  "EXPLORE_DAY_OFFSET", "EXPLORE_FETCH_LIMIT", "EXPLORE_ARXIV_ENABLED", "EXPLORE_HF_DAILY_ENABLED",
  "EXPLORE_HF_TRENDING_ENABLED", "EXPLORE_HF_TRENDING_MAX_AGE_DAYS",
  "EXPLORE_INCLUDE_HISTORICAL_MILESTONES", "EXPLORE_WATCHED_AUTHORS_ENABLED",
  "EXPLORE_WATCHED_AUTHORS", "EXPLORE_WATCHED_AUTHORS_WINDOW_DAYS", "EXPLORE_OPENREVIEW_ENABLED",
  "EXPLORE_OPENREVIEW_WINDOW_DAYS", "EXPLORE_OPENREVIEW_MAX_PAGES", "EXPLORE_OPENREVIEW_VENUES",
];
const RADAR_NAMES = [
  "RADAR_EMBEDDING_PROVIDER", "RADAR_EMBEDDING_MODEL", "RADAR_EMBEDDING_TASK",
  "RADAR_EMBEDDING_PROMPT_NAME", "RADAR_EMBEDDING_TRUST_REMOTE_CODE",
  "RADAR_EMBEDDING_BATCH_SIZE", "RADAR_EMBEDDING_BASE_URL", "RADAR_LLM_ENABLED",
  "RADAR_LLM_REQUIRED", "RADAR_DEBUG", "RADAR_EMAIL_SENDER", "RADAR_EMAIL_RECEIVER",
  "RADAR_SMTP_HOST", "RADAR_SMTP_PORT", "RADAR_SMTP_SSL",
];
const SECRET_NAMES = [
  "LLM_API_KEY", "RADAR_EMBEDDING_API_KEY", "RADAR_EMAIL_PASSWORD",
  "SEMANTIC_SCHOLAR_API_KEY", "OPENREVIEW_PASSWORD",
];

const SELECT_CLASS = "h-11 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40 md:h-9";

function splitValues(value: string) {
  return value.split(/[\n,，]/).map((item) => item.trim()).filter(Boolean);
}

function ExpandableTextarea({ value, onChange, rows = 4, placeholder }: {
  value: string;
  onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  rows?: number;
  placeholder?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Textarea
      value={value}
      onChange={onChange}
      onFocus={() => setExpanded(true)}
      onBlur={() => setExpanded(false)}
      rows={expanded ? rows : 1}
      placeholder={placeholder}
      className={expanded ? "min-h-24 resize-y" : "h-9 min-h-0 resize-none overflow-hidden whitespace-nowrap"}
    />
  );
}

function asBool(value: string | undefined, fallback = false) {
  if (value == null) return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function Section({ title, description, children, collapsible = false, defaultOpen = true }: { title: string; description?: string; children: React.ReactNode; collapsible?: boolean; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const heading = <><h2 className="text-sm font-semibold">{title}</h2>{description && <p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">{description}</p>}</>;
  if (collapsible) {
    return (
      <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)} className="group mb-5 rounded-xl border border-border/80 bg-card px-5 py-1 last:mb-0 sm:px-6">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 py-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <div className="min-w-0">{heading}</div>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        <div className="divide-y divide-border/60 pb-4">{children}</div>
      </details>
    );
  }
  return (
    <section className="mb-5 rounded-xl border border-border/80 bg-card px-5 py-5 last:mb-0 sm:px-6">
      <div className="mb-2">{heading}</div>
      <div className="divide-y divide-border/60">{children}</div>
    </section>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_320px] sm:items-start sm:gap-8">
      <span className="min-w-0 pt-1.5">
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{hint}</span>}
      </span>
      <span className="block min-w-0 sm:w-80 sm:justify-self-end">{children}</span>
    </label>
  );
}

function ToggleField({ label, hint, checked, onChange, disabled = false }: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex min-h-11 items-center justify-between gap-6 py-3">
      <span className="min-w-0">
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${checked ? "border-primary bg-primary" : "border-input bg-muted"}`}
      >
        <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-5" : "translate-x-0"}`} />
      </button>
    </div>
  );
}

function InfoRow({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-3 text-sm">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <div><p className="font-medium">{title}</p><p className="mt-0.5 max-w-2xl text-xs leading-5 text-muted-foreground">{children}</p></div>
    </div>
  );
}

export function Settings() {
  const { activeProject } = useProject();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedSection = searchParams.get("tab") as SettingsSection | null;
  const section = SETTINGS_SECTIONS.some((item) => item.id === requestedSection) ? requestedSection! : "ai";
  const [settings, setSettings] = useState<AppSettings>({ values: {}, secrets: {} });
  const [profile, setProfile] = useState<ExploreProfile | null>(null);
  const [libraryAuthors, setLibraryAuthors] = useState<string[]>([]);
  const [selectedAuthor, setSelectedAuthor] = useState("");
  const [authorSearchOpen, setAuthorSearchOpen] = useState(false);
  const [radarConfig, setRadarConfig] = useState(EMPTY_RADAR_CONFIG);
  const [connection, setConnection] = useState<RadarConnection>({ remote_url: "", token_configured: false });
  const [secretInputs, setSecretInputs] = useState<Record<string, string>>({});
  const [visibleSecrets, setVisibleSecrets] = useState<Set<string>>(new Set());
  const [clearedSecrets, setClearedSecrets] = useState<Set<string>>(new Set());
  const [clearRadarToken, setClearRadarToken] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetchAppSettings(),
      fetchExploreProfiles(),
      fetchPapers(),
      fetchRadarConnection(),
      activeProject ? fetchRadarConfig(activeProject.id) : Promise.resolve(null),
    ]).then(([nextSettings, profiles, papers, nextConnection, nextRadar]) => {
      if (cancelled) return;
      setSettings(nextSettings);
      setProfile(profiles[0] || null);
      const authors = new Set<string>();
      (papers as Paper[]).forEach((paper) => (paper.authors || []).forEach((author) => {
        const name = typeof author === "string" ? author.trim() : "";
        if (name) authors.add(name);
      }));
      setLibraryAuthors(Array.from(authors).sort((a, b) => a.localeCompare(b)));
      setConnection(nextConnection);
      if (nextRadar) setRadarConfig(nextRadar);
      setDirty(false);
    }).catch((err) => {
      if (!cancelled) setError(err instanceof Error ? err.message : String(err));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [activeProject?.id]);

  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    if (loading || section !== "explore" || window.location.hash !== "#explore-topic-settings") return;
    window.requestAnimationFrame(() => document.getElementById("explore-topic-settings")?.scrollIntoView({ block: "start" }));
  }, [loading, section]);

  const value = (name: string) => settings.values[name] || "";
  const setValue = (name: string, next: string | boolean | number) => {
    setSettings((current) => ({ ...current, values: { ...current.values, [name]: String(next) } }));
    setDirty(true);
    setNotice(null);
  };
  const isChecked = (name: string, fallback = false) => asBool(value(name), fallback);
  const watchedAuthorNames = useMemo(() => splitValues(value("EXPLORE_WATCHED_AUTHORS")).map((item) => item.split("|")[0].trim()), [settings]);
  const availableAuthors = useMemo(() => {
    const query = selectedAuthor.trim().toLocaleLowerCase();
    return libraryAuthors
      .filter((author) => !watchedAuthorNames.some((watched) => watched.toLocaleLowerCase() === author.toLocaleLowerCase()))
      .filter((author) => !query || author.toLocaleLowerCase().includes(query))
      .slice(0, 8);
  }, [libraryAuthors, selectedAuthor, watchedAuthorNames]);
  const addWatchedAuthor = () => {
    const author = selectedAuthor.trim();
    if (!author || watchedAuthorNames.some((item) => item.toLowerCase() === author.toLowerCase())) return;
    const current = value("EXPLORE_WATCHED_AUTHORS").trim();
    setValue("EXPLORE_WATCHED_AUTHORS", current ? `${current},${author}` : author);
    setSelectedAuthor("");
    setAuthorSearchOpen(false);
  };
  const setRadar = <K extends keyof typeof radarConfig>(name: K, next: (typeof radarConfig)[K]) => {
    setRadarConfig((current) => ({ ...current, [name]: next }));
    setDirty(true);
    setNotice(null);
  };

  const secretField = (name: string, label: string, hint?: string) => {
    const configured = Boolean(settings.secrets[name]) && !clearedSecrets.has(name);
    const visible = visibleSecrets.has(name);
    return (
      <Field label={label} hint={hint}>
        <div className="flex gap-2">
          <div className="relative min-w-0 flex-1">
            <Input
              type={visible ? "text" : "password"}
              value={secretInputs[name] || ""}
              onChange={(event) => {
                setSecretInputs((current) => ({ ...current, [name]: event.target.value }));
                setClearedSecrets((current) => {
                  const next = new Set(current);
                  next.delete(name);
                  return next;
                });
                setDirty(true);
                setNotice(null);
              }}
              placeholder={configured ? "已配置" : "未配置"}
              autoComplete="off"
              className="pr-9"
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setVisibleSecrets((current) => {
                const next = new Set(current);
                next.has(name) ? next.delete(name) : next.add(name);
                return next;
              })}
              aria-label={visible ? `隐藏 ${label}` : `显示 ${label}`}
              title={visible ? "隐藏" : "显示"}
            >
              {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {configured && (
            <Button
              type="button"
              size="icon"
              variant="outline"
              onClick={() => {
                setClearedSecrets((current) => new Set(current).add(name));
                setDirty(true);
                setNotice(null);
              }}
              aria-label={`清除 ${label}`}
              title="保存后清除"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
        {clearedSecrets.has(name) && <span className="mt-1.5 block text-xs text-destructive">保存后清除</span>}
      </Field>
    );
  };

  const saveAll = async () => {
    if (!dirty) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const settingNames = [...AI_NAMES, ...EXPLORE_NAMES, ...RADAR_NAMES, "OPENREVIEW_EMAIL"];
      const values = Object.fromEntries(settingNames.map((name) => [name, value(name)]));
      const secrets = Object.fromEntries(
        SECRET_NAMES.filter((name) => secretInputs[name]?.trim()).map((name) => [name, secretInputs[name].trim()]),
      );
      const clearSecrets = SECRET_NAMES.filter((name) => clearedSecrets.has(name));
      const updated = await updateAppSettings({ values, secrets, clear_secrets: clearSecrets });
      setSettings(updated);
      setSecretInputs((current) => ({ ...current, ...Object.fromEntries(SECRET_NAMES.map((name) => [name, ""])) }));
      setClearedSecrets(new Set());
      if (profile) setProfile(await updateExploreProfile(profile));
      if (activeProject && !activeProject.is_system) setRadarConfig(await updateRadarConfig(activeProject.id, radarConfig));
      if (connection.remote_url.trim() || secretInputs.RADAR_TOKEN?.trim() || clearRadarToken) {
        setConnection(await updateRadarConnection(connection.remote_url, secretInputs.RADAR_TOKEN, clearRadarToken));
        setSecretInputs((current) => ({ ...current, RADAR_TOKEN: "" }));
        setClearRadarToken(false);
      }
      setDirty(false);
      setNotice("已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <div className="mx-auto max-w-6xl space-y-6" aria-label="正在加载设置">
      <div className="flex items-center justify-between border-b pb-5"><Skeleton className="h-7 w-20" /><Skeleton className="h-8 w-24" /></div>
      <div className="grid gap-8 md:grid-cols-[160px_minmax(0,1fr)] lg:gap-12">
        <div className="space-y-2">{Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-9 w-full" />)}</div>
        <div className="space-y-4">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-14 w-full" />)}</div>
      </div>
    </div>
  );

  return (
    <div className="mx-auto max-w-6xl">
      <div className="flex min-h-10 items-center justify-between gap-4 pb-5">
        <div>
          <h1 className="text-xl font-semibold">设置</h1>
          <div className="mt-1 min-h-4" aria-live="polite">
            {notice ? <p className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400"><Check className="h-3.5 w-3.5" />{notice}</p> : dirty ? <p className="text-xs text-muted-foreground">有未保存的更改</p> : null}
          </div>
        </div>
        <Button onClick={() => void saveAll()} disabled={saving || !dirty} size="sm">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}{saving ? "保存中" : "保存更改"}
        </Button>
      </div>

      {error && <div className="mt-4"><ErrorAlert title="无法保存设置" message={error} onRetry={() => setError(null)} /></div>}

      <div className="grid gap-8 py-6 md:grid-cols-[160px_minmax(0,1fr)] lg:gap-12">
        <nav className="flex gap-1 overflow-x-auto md:sticky md:top-20 md:block md:self-start" aria-label="设置分类">
          {SETTINGS_SECTIONS.map((item) => {
            const active = item.id === section;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setSearchParams({ tab: item.id }, { replace: true })}
                className={`flex h-11 flex-none items-center gap-2 rounded-md px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:mb-1 md:h-9 md:w-full md:px-2.5 ${active ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"}`}
                aria-current={active ? "page" : undefined}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="min-w-0">
          {section === "ai" && <>
            <Section title="OpenAI-compatible API" description="聊天、论文标注、探索、趋势、Paper River 共用。">
              {secretField("LLM_API_KEY", "API Key")}
              <Field label="Base URL"><Input value={value("LLM_BASE_URL")} onChange={(event) => setValue("LLM_BASE_URL", event.target.value)} /></Field>
              <Field label="Model"><Input value={value("LLM_MODEL")} onChange={(event) => setValue("LLM_MODEL", event.target.value)} /></Field>
            </Section>
            <Section title="Advanced" collapsible defaultOpen={false}>
              <Field label="Provider type" hint="Kimi Agent SDK provider 类型，例如 openai_legacy。"><Input value={value("LLM_PROVIDER_TYPE")} onChange={(event) => setValue("LLM_PROVIDER_TYPE", event.target.value)} /></Field>
              <Field label="Capabilities" hint="Kimi Agent SDK provider capability ID。通常留空。"><Input value={value("LLM_CAPABILITIES")} onChange={(event) => setValue("LLM_CAPABILITIES", event.target.value)} /></Field>
              <Field label="Context length"><Input type="number" min="1024" value={value("LLM_MAX_CONTEXT_SIZE")} onChange={(event) => setValue("LLM_MAX_CONTEXT_SIZE", event.target.value)} /></Field>
            </Section>
          </>}

          {section === "explore" && (
            <>
              {profile && (
                <div id="explore-topic-settings" className="scroll-mt-24">
                  <Section title="探索主题" description="主题决定采集范围；筛选、打分、分桶继续使用 LLM 推理优化算法。">
                    <Field label="主题名称"><Input value={profile.name} onChange={(event) => { setProfile({ ...profile, name: event.target.value }); setDirty(true); setNotice(null); }} /></Field>
                    <Field label="主题说明" hint="描述你在 LLM 推理优化中重点关注的方向。"><ExpandableTextarea rows={3} value={profile.description} onChange={(event) => { setProfile({ ...profile, description: event.target.value }); setDirty(true); setNotice(null); }} /></Field>
                    <Field label="arXiv 分类" hint="例如 cs.LG=机器学习，cs.CL=计算语言学，cs.AR=硬件架构。"><Input value={profile.categories.join(", ")} onChange={(event) => { setProfile({ ...profile, categories: splitValues(event.target.value) }); setDirty(true); setNotice(null); }} /></Field>
                    <Field label="重点关键词" hint="用于放宽本地预筛选；一行一个。"><ExpandableTextarea rows={4} value={profile.include_keywords.join("\n")} onChange={(event) => { setProfile({ ...profile, include_keywords: splitValues(event.target.value) }); setDirty(true); setNotice(null); }} /></Field>
                    <Field label="排除关键词" hint="标题或摘要命中这些词时优先过滤；一行一个。"><ExpandableTextarea rows={4} value={profile.exclude_keywords.join("\n")} onChange={(event) => { setProfile({ ...profile, exclude_keywords: splitValues(event.target.value) }); setDirty(true); setNotice(null); }} /></Field>
                  </Section>
                </div>
              )}
              <Section title="时间">
                <Field label="目标日偏移" hint="UTC 天；默认 1。"><Input type="number" min="0" max="30" value={value("EXPLORE_DAY_OFFSET")} onChange={(event) => setValue("EXPLORE_DAY_OFFSET", event.target.value)} /></Field>
                <Field label="每个来源采集上限" hint="默认 100。只限制原始候选，采集不调用 LLM。"><Input type="number" min="10" max="500" step="10" value={value("EXPLORE_FETCH_LIMIT")} onChange={(event) => setValue("EXPLORE_FETCH_LIMIT", event.target.value)} /></Field>
                <Field label="Hugging Face 热门榜最大年龄" hint="只保留目标日前 N 天内的论文；默认 30 天。"><Input type="number" min="0" max="3650" value={value("EXPLORE_HF_TRENDING_MAX_AGE_DAYS")} onChange={(event) => setValue("EXPLORE_HF_TRENDING_MAX_AGE_DAYS", event.target.value)} /></Field>
                <ToggleField label="Hugging Face 热门榜" hint="按 Hugging Face 热度补充近期论文。" checked={isChecked("EXPLORE_HF_TRENDING_ENABLED", true)} onChange={(checked) => setValue("EXPLORE_HF_TRENDING_ENABLED", checked)} />
                <ToggleField label="保留历史精选" hint="允许精选论文突破年龄限制。" checked={isChecked("EXPLORE_INCLUDE_HISTORICAL_MILESTONES")} onChange={(checked) => setValue("EXPLORE_INCLUDE_HISTORICAL_MILESTONES", checked)} />
              </Section>
              <Section title="来源">
                <ToggleField label="arXiv" checked={isChecked("EXPLORE_ARXIV_ENABLED", true)} onChange={(checked) => setValue("EXPLORE_ARXIV_ENABLED", checked)} />
                <ToggleField label="Hugging Face 日榜" hint="采集当天在 Hugging Face 出现的论文。" checked={isChecked("EXPLORE_HF_DAILY_ENABLED", true)} onChange={(checked) => setValue("EXPLORE_HF_DAILY_ENABLED", checked)} />
                <ToggleField label="订阅关注作者更新" hint="这些作者的新论文会单独出现在探索首页，不受主题精选数量上限影响。" checked={isChecked("EXPLORE_WATCHED_AUTHORS_ENABLED")} onChange={(checked) => setValue("EXPLORE_WATCHED_AUTHORS_ENABLED", checked)} />
                <ToggleField label="OpenReview" checked={isChecked("EXPLORE_OPENREVIEW_ENABLED", true)} onChange={(checked) => setValue("EXPLORE_OPENREVIEW_ENABLED", checked)} />
                <Field label="关注作者时间范围（天）" hint="抓取目标日前 N 天内这些作者提交的新论文；默认 7 天。"><Input type="number" min="1" max="365" value={value("EXPLORE_WATCHED_AUTHORS_WINDOW_DAYS")} onChange={(event) => setValue("EXPLORE_WATCHED_AUTHORS_WINDOW_DAYS", event.target.value)} /></Field>
                <Field label="关注作者" hint="订阅作者更新。先从论文库选择，必要时再手动补充机构信息。">
                  <div className="space-y-2">
                    <div className="flex items-start gap-2">
                      <div className="relative min-w-0 flex-1">
                        <UserRound className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                          aria-label="搜索论文库作者"
                          value={selectedAuthor}
                          maxLength={120}
                          onChange={(event) => {
                            setSelectedAuthor(event.target.value);
                            setAuthorSearchOpen(true);
                          }}
                          onFocus={() => setAuthorSearchOpen(true)}
                          onBlur={() => window.setTimeout(() => setAuthorSearchOpen(false), 100)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") {
                              event.preventDefault();
                              addWatchedAuthor();
                            }
                            if (event.key === "Escape") setAuthorSearchOpen(false);
                          }}
                          placeholder="输入姓名搜索"
                          autoComplete="off"
                          className="pl-9"
                        />
                        {authorSearchOpen && <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md">
                          {availableAuthors.length ? availableAuthors.map((author) => (
                            <button
                              key={author}
                              type="button"
                              title={author}
                              onMouseDown={(event) => event.preventDefault()}
                              onClick={() => {
                                setSelectedAuthor(author);
                                setAuthorSearchOpen(false);
                              }}
                              className="block w-full truncate rounded-sm px-2 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              {author}
                            </button>
                          )) : <p className="px-2 py-2 text-sm text-muted-foreground">没有匹配作者</p>}
                        </div>}
                      </div>
                      <Button type="button" variant="outline" size="sm" onClick={addWatchedAuthor} disabled={!selectedAuthor}>添加</Button>
                    </div>
                    <ExpandableTextarea rows={6} value={value("EXPLORE_WATCHED_AUTHORS").replaceAll(",", "\n")} onChange={(event) => setValue("EXPLORE_WATCHED_AUTHORS", splitValues(event.target.value).join(","))} placeholder="姓名 | 机构，可手动补充" />
                  </div>
                </Field>
                <Field label="OpenReview 投稿时间范围（天）" hint="读取目标日前 N 天内的会议投稿；默认 7 天。"><Input type="number" min="1" max="365" value={value("EXPLORE_OPENREVIEW_WINDOW_DAYS")} onChange={(event) => setValue("EXPLORE_OPENREVIEW_WINDOW_DAYS", event.target.value)} /></Field>
                <Field label="OpenReview Max pages" hint="单次采集每个会议最多请求的页数。"><Input type="number" min="1" max="100" value={value("EXPLORE_OPENREVIEW_MAX_PAGES")} onChange={(event) => setValue("EXPLORE_OPENREVIEW_MAX_PAGES", event.target.value)} /></Field>
                <Field label="OpenReview 会议路径" hint="一行一个，支持 {year}，例如 ICLR.cc/{year}/Conference。点击输入框展开编辑。"><ExpandableTextarea rows={6} value={value("EXPLORE_OPENREVIEW_VENUES").replaceAll(",", "\n")} onChange={(event) => setValue("EXPLORE_OPENREVIEW_VENUES", splitValues(event.target.value).join(","))} /></Field>
                <InfoRow title="OpenReview 采集说明">按投稿时间倒序请求；进入设定时间范围外，或返回不足一页时自动停止。采集阶段不调用 LLM，不消耗 token。</InfoRow>
              </Section>
            </>
          )}

          {section === "radar" && (
            <>
              <Section title="项目" description={activeProject ? `基于“${activeProject.name}”中的论文生成个性化推荐。` : "请先选择研究项目。"} collapsible defaultOpen>
                <ToggleField label="启用雷达" checked={radarConfig.enabled} disabled={!activeProject || Boolean(activeProject.is_system)} onChange={(checked) => setRadar("enabled", checked)} />
                <ToggleField label="包含交叉列表论文" hint="同时出现在其他分类的论文也纳入抓取。" checked={radarConfig.include_cross_list} onChange={(checked) => setRadar("include_cross_list", checked)} />
                <ToggleField label="发送空结果" checked={radarConfig.send_empty} onChange={(checked) => setRadar("send_empty", checked)} />
                <Field label="arXiv 分类"><Input value={radarConfig.categories.join(", ")} onChange={(event) => setRadar("categories", splitValues(event.target.value))} /></Field>
                <Field label="纳入关键词"><Textarea rows={3} value={radarConfig.include_keywords.join("\n")} onChange={(event) => setRadar("include_keywords", splitValues(event.target.value))} /></Field>
                <Field label="排除关键词"><Textarea rows={3} value={radarConfig.exclude_keywords.join("\n")} onChange={(event) => setRadar("exclude_keywords", splitValues(event.target.value))} /></Field>
                <Field label="返回前 K 篇" hint="每次运行最多保留的推荐数；邮件只发送其中本次新增的论文。"><Input type="number" min="1" max="100" value={radarConfig.top_k} onChange={(event) => setRadar("top_k", Number(event.target.value))} /></Field>
                <Field label="抓取数量上限"><Input type="number" min="1" max="500" value={radarConfig.fetch_limit} onChange={(event) => setRadar("fetch_limit", Number(event.target.value))} /></Field>
                <Field label="最低相似度"><Input type="number" min="0" max="1" step="0.01" value={radarConfig.min_score} onChange={(event) => setRadar("min_score", Number(event.target.value))} /></Field>
                <Field label="计算模式"><select value={radarConfig.compute_mode} onChange={(event) => setRadar("compute_mode", event.target.value as RadarConfig["compute_mode"])} className={SELECT_CLASS}><option value="cloud">云端计算</option><option value="local">本地计算</option><option value="hybrid">云端优先，本地备用</option></select></Field>
                <Field label="项目简介补充" hint="补充给相似度模型的研究方向说明。"><ExpandableTextarea rows={4} value={radarConfig.profile_override} onChange={(event) => setRadar("profile_override", event.target.value)} /></Field>
              </Section>
              <Section title="远程雷达服务" collapsible defaultOpen>
                <Field label="Worker URL"><Input value={connection.remote_url} onChange={(event) => { setConnection({ ...connection, remote_url: event.target.value }); setDirty(true); setNotice(null); }} placeholder="https://radar.example.workers.dev" /></Field>
                <Field label="Access Token">
                  <div className="flex gap-2">
                    <Input type="password" value={secretInputs.RADAR_TOKEN || ""} onChange={(event) => { setSecretInputs((current) => ({ ...current, RADAR_TOKEN: event.target.value })); setClearRadarToken(false); setDirty(true); setNotice(null); }} placeholder={connection.token_configured && !clearRadarToken ? "已配置" : "未配置"} autoComplete="off" />
                    {connection.token_configured && !clearRadarToken && <Button type="button" size="icon" variant="outline" onClick={() => { setClearRadarToken(true); setDirty(true); setNotice(null); }} aria-label="清除 Token" title="保存后清除"><Trash2 className="h-4 w-4" /></Button>}
                  </div>
                  {clearRadarToken && <span className="mt-1.5 block text-xs text-destructive">保存后清除</span>}
                </Field>
              </Section>
              <Section title="向量检索" collapsible={true} defaultOpen={false}>
                <Field label="服务方式"><select value={value("RADAR_EMBEDDING_PROVIDER")} onChange={(event) => setValue("RADAR_EMBEDDING_PROVIDER", event.target.value)} className={SELECT_CLASS}><option value="local">本地模型</option><option value="api">兼容 API</option><option value="lexical">关键词匹配</option></select></Field>
                <Field label="Embedding model"><Input value={value("RADAR_EMBEDDING_MODEL")} onChange={(event) => setValue("RADAR_EMBEDDING_MODEL", event.target.value)} /></Field>
                {secretField("RADAR_EMBEDDING_API_KEY", "Embedding API Key", "留空复用全局 LLM API Key。")}
                <Field label="Base URL"><Input value={value("RADAR_EMBEDDING_BASE_URL")} onChange={(event) => setValue("RADAR_EMBEDDING_BASE_URL", event.target.value)} /></Field>
                <Field label="Task"><Input value={value("RADAR_EMBEDDING_TASK")} onChange={(event) => setValue("RADAR_EMBEDDING_TASK", event.target.value)} /></Field>
                <Field label="Prompt name"><Input value={value("RADAR_EMBEDDING_PROMPT_NAME")} onChange={(event) => setValue("RADAR_EMBEDDING_PROMPT_NAME", event.target.value)} /></Field>
                <Field label="Batch size"><Input type="number" min="1" max="1024" value={value("RADAR_EMBEDDING_BATCH_SIZE")} onChange={(event) => setValue("RADAR_EMBEDDING_BATCH_SIZE", event.target.value)} /></Field>
                <ToggleField label="允许加载远程代码" hint="仅在使用本地模型时生效。" checked={isChecked("RADAR_EMBEDDING_TRUST_REMOTE_CODE", true)} onChange={(checked) => setValue("RADAR_EMBEDDING_TRUST_REMOTE_CODE", checked)} />
              </Section>
              <Section title="生成与日志" collapsible={true} defaultOpen={false}>
                <ToggleField label="生成 LLM 摘要" checked={isChecked("RADAR_LLM_ENABLED", true)} onChange={(checked) => setValue("RADAR_LLM_ENABLED", checked)} />
                <ToggleField label="摘要失败则停止" checked={isChecked("RADAR_LLM_REQUIRED")} onChange={(checked) => setValue("RADAR_LLM_REQUIRED", checked)} />
                <ToggleField label="雷达调试日志" checked={isChecked("RADAR_DEBUG")} onChange={(checked) => setValue("RADAR_DEBUG", checked)} />
                <ToggleField label="项目调试模式" checked={radarConfig.debug} onChange={(checked) => setRadar("debug", checked)} />
              </Section>
              <Section title="邮件" collapsible={true} defaultOpen={false}>
                <InfoRow title="发送范围">定时任务只发送本轮新增推荐，已发过的论文不会重复发送；雷达页仍保留历史结果。</InfoRow>
                <Field label="发件人"><Input value={value("RADAR_EMAIL_SENDER")} onChange={(event) => setValue("RADAR_EMAIL_SENDER", event.target.value)} /></Field>
                <Field label="收件人"><Input value={value("RADAR_EMAIL_RECEIVER")} onChange={(event) => setValue("RADAR_EMAIL_RECEIVER", event.target.value)} /></Field>
                {secretField("RADAR_EMAIL_PASSWORD", "邮箱密码 / 应用专用密码")}
                <Field label="SMTP 服务器"><Input value={value("RADAR_SMTP_HOST")} onChange={(event) => setValue("RADAR_SMTP_HOST", event.target.value)} /></Field>
                <Field label="SMTP 端口"><Input type="number" min="1" max="65535" value={value("RADAR_SMTP_PORT")} onChange={(event) => setValue("RADAR_SMTP_PORT", event.target.value)} /></Field>
                <ToggleField label="启用 SSL 加密" checked={isChecked("RADAR_SMTP_SSL", true)} onChange={(checked) => setValue("RADAR_SMTP_SSL", checked)} />
              </Section>
            </>
          )}

          {section === "integrations" && (
            <>
              <Section title="Semantic Scholar">
                {secretField("SEMANTIC_SCHOLAR_API_KEY", "API Key")}
              </Section>
              <Section title="OpenReview" description="公开投稿无需登录。仅在会议需要认证访问时填写账户。">
                <Field label="Email"><Input type="email" value={value("OPENREVIEW_EMAIL")} onChange={(event) => setValue("OPENREVIEW_EMAIL", event.target.value)} /></Field>
                {secretField("OPENREVIEW_PASSWORD", "密码")}
                <InfoRow title="可选账户">留空不影响公开会议采集。保存后凭据只写入本地 backend/.env。</InfoRow>
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
