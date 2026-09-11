import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, Check, Cloud, Compass, Eye, EyeOff, Loader2, Radar as RadarIcon, Save, Trash2 } from "lucide-react";
import { useProject } from "@/contexts/ProjectContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ErrorAlert } from "@/components/ErrorAlert";
import { Skeleton } from "@/components/ui/skeleton";
import {
  fetchAppSettings,
  fetchExploreProfiles,
  fetchRadarConfig,
  fetchRadarConnection,
  updateAppSettings,
  updateExploreProfile,
  updateRadarConfig,
  updateRadarConnection,
} from "@/services/api";
import type { AppSettings, ExploreProfile, RadarConfig, RadarConnection } from "@/types";

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
  "EXPLORE_DAY_OFFSET", "EXPLORE_ARXIV_ENABLED", "EXPLORE_HF_DAILY_ENABLED",
  "EXPLORE_HF_TRENDING_ENABLED", "EXPLORE_HF_TRENDING_MAX_AGE_DAYS",
  "EXPLORE_INCLUDE_HISTORICAL_MILESTONES", "EXPLORE_WATCHED_AUTHORS_ENABLED",
  "EXPLORE_WATCHED_AUTHORS_WINDOW_DAYS", "EXPLORE_OPENREVIEW_ENABLED",
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

function asBool(value: string | undefined, fallback = false) {
  if (value == null) return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-border py-7 first:pt-0 last:border-b-0">
      <div className="mb-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="mt-1 max-w-2xl text-xs leading-5 text-muted-foreground">{description}</p>}
      </div>
      <div className="divide-y divide-border/70">{children}</div>
    </section>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(240px,420px)] sm:items-start sm:gap-8">
      <span className="min-w-0 pt-1.5">
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{hint}</span>}
      </span>
      <span className="block min-w-0">{children}</span>
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
        className={`relative h-6 w-10 shrink-0 rounded-full border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${checked ? "border-primary bg-primary" : "border-input bg-muted"}`}
      >
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
      </button>
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
      fetchRadarConnection(),
      activeProject ? fetchRadarConfig(activeProject.id) : Promise.resolve(null),
    ]).then(([nextSettings, profiles, nextConnection, nextRadar]) => {
      if (cancelled) return;
      setSettings(nextSettings);
      setProfile(profiles[0] || null);
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

  const value = (name: string) => settings.values[name] || "";
  const setValue = (name: string, next: string | boolean | number) => {
    setSettings((current) => ({ ...current, values: { ...current.values, [name]: String(next) } }));
    setDirty(true);
    setNotice(null);
  };
  const isChecked = (name: string, fallback = false) => asBool(value(name), fallback);
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
      if (activeProject) setRadarConfig(await updateRadarConfig(activeProject.id, radarConfig));
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
      <div className="flex min-h-10 items-center justify-between gap-4 border-b border-border pb-5">
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
          {section === "ai" && (
            <Section title="模型" description="用于聊天、标注、Explore、Venue Trend、Paper River。">
              {secretField("LLM_API_KEY", "API Key")}
              <Field label="Base URL"><Input value={value("LLM_BASE_URL")} onChange={(event) => setValue("LLM_BASE_URL", event.target.value)} /></Field>
              <Field label="Model"><Input value={value("LLM_MODEL")} onChange={(event) => setValue("LLM_MODEL", event.target.value)} /></Field>
              <Field label="Provider type"><Input value={value("LLM_PROVIDER_TYPE")} onChange={(event) => setValue("LLM_PROVIDER_TYPE", event.target.value)} /></Field>
              <Field label="Capabilities"><Input value={value("LLM_CAPABILITIES")} onChange={(event) => setValue("LLM_CAPABILITIES", event.target.value)} /></Field>
              <Field label="Context size"><Input type="number" min="1024" value={value("LLM_MAX_CONTEXT_SIZE")} onChange={(event) => setValue("LLM_MAX_CONTEXT_SIZE", event.target.value)} /></Field>
            </Section>
          )}

          {section === "explore" && (
            <>
              <Section title="时间">
                <Field label="目标日偏移" hint="UTC 天；默认 1。"><Input type="number" min="0" max="30" value={value("EXPLORE_DAY_OFFSET")} onChange={(event) => setValue("EXPLORE_DAY_OFFSET", event.target.value)} /></Field>
                <Field label="HF Trending 最大年龄" hint="天；默认 30。"><Input type="number" min="0" max="3650" value={value("EXPLORE_HF_TRENDING_MAX_AGE_DAYS")} onChange={(event) => setValue("EXPLORE_HF_TRENDING_MAX_AGE_DAYS", event.target.value)} /></Field>
                <ToggleField label="HF Trending" checked={isChecked("EXPLORE_HF_TRENDING_ENABLED", true)} onChange={(checked) => setValue("EXPLORE_HF_TRENDING_ENABLED", checked)} />
                <ToggleField label="历史 milestone" hint="允许 curated paper 突破年龄限制。" checked={isChecked("EXPLORE_INCLUDE_HISTORICAL_MILESTONES")} onChange={(checked) => setValue("EXPLORE_INCLUDE_HISTORICAL_MILESTONES", checked)} />
              </Section>
              <Section title="来源">
                <ToggleField label="arXiv" checked={isChecked("EXPLORE_ARXIV_ENABLED", true)} onChange={(checked) => setValue("EXPLORE_ARXIV_ENABLED", checked)} />
                <ToggleField label="HF Daily" checked={isChecked("EXPLORE_HF_DAILY_ENABLED", true)} onChange={(checked) => setValue("EXPLORE_HF_DAILY_ENABLED", checked)} />
                <ToggleField label="关注作者" checked={isChecked("EXPLORE_WATCHED_AUTHORS_ENABLED", true)} onChange={(checked) => setValue("EXPLORE_WATCHED_AUTHORS_ENABLED", checked)} />
                <ToggleField label="OpenReview" checked={isChecked("EXPLORE_OPENREVIEW_ENABLED", true)} onChange={(checked) => setValue("EXPLORE_OPENREVIEW_ENABLED", checked)} />
                <Field label="关注作者窗口"><Input type="number" min="1" max="365" value={value("EXPLORE_WATCHED_AUTHORS_WINDOW_DAYS")} onChange={(event) => setValue("EXPLORE_WATCHED_AUTHORS_WINDOW_DAYS", event.target.value)} /></Field>
                <Field label="OpenReview 窗口"><Input type="number" min="1" max="365" value={value("EXPLORE_OPENREVIEW_WINDOW_DAYS")} onChange={(event) => setValue("EXPLORE_OPENREVIEW_WINDOW_DAYS", event.target.value)} /></Field>
                <Field label="OpenReview 最大页数"><Input type="number" min="1" max="100" value={value("EXPLORE_OPENREVIEW_MAX_PAGES")} onChange={(event) => setValue("EXPLORE_OPENREVIEW_MAX_PAGES", event.target.value)} /></Field>
                <Field label="OpenReview venues" hint="支持 {year}。"><Textarea rows={6} value={value("EXPLORE_OPENREVIEW_VENUES").replaceAll(",", "\n")} onChange={(event) => setValue("EXPLORE_OPENREVIEW_VENUES", splitValues(event.target.value).join(","))} /></Field>
              </Section>
              {profile && (
                <Section title="探索主题">
                  <Field label="名称"><Input value={profile.name} onChange={(event) => { setProfile({ ...profile, name: event.target.value }); setDirty(true); setNotice(null); }} /></Field>
                  <Field label="arXiv categories"><Input value={profile.categories.join(", ")} onChange={(event) => { setProfile({ ...profile, categories: splitValues(event.target.value) }); setDirty(true); setNotice(null); }} /></Field>
                  <Field label="纳入关键词"><Textarea rows={4} value={profile.include_keywords.join("\n")} onChange={(event) => { setProfile({ ...profile, include_keywords: splitValues(event.target.value) }); setDirty(true); setNotice(null); }} /></Field>
                  <Field label="排除关键词"><Textarea rows={4} value={profile.exclude_keywords.join("\n")} onChange={(event) => { setProfile({ ...profile, exclude_keywords: splitValues(event.target.value) }); setDirty(true); setNotice(null); }} /></Field>
                </Section>
              )}
            </>
          )}

          {section === "radar" && (
            <>
              <Section title="项目" description={activeProject?.name || "未选择项目"}>
                <ToggleField label="启用雷达" checked={radarConfig.enabled} disabled={!activeProject || Boolean(activeProject.is_system)} onChange={(checked) => setRadar("enabled", checked)} />
                <ToggleField label="包含 cross-list" checked={radarConfig.include_cross_list} onChange={(checked) => setRadar("include_cross_list", checked)} />
                <ToggleField label="发送空结果" checked={radarConfig.send_empty} onChange={(checked) => setRadar("send_empty", checked)} />
                <Field label="Categories"><Input value={radarConfig.categories.join(", ")} onChange={(event) => setRadar("categories", splitValues(event.target.value))} /></Field>
                <Field label="Anchor paper IDs"><Input value={radarConfig.anchor_paper_ids.join(", ")} onChange={(event) => setRadar("anchor_paper_ids", splitValues(event.target.value))} /></Field>
                <Field label="纳入关键词"><Textarea rows={3} value={radarConfig.include_keywords.join("\n")} onChange={(event) => setRadar("include_keywords", splitValues(event.target.value))} /></Field>
                <Field label="排除关键词"><Textarea rows={3} value={radarConfig.exclude_keywords.join("\n")} onChange={(event) => setRadar("exclude_keywords", splitValues(event.target.value))} /></Field>
                <Field label="Top K"><Input type="number" min="1" max="100" value={radarConfig.top_k} onChange={(event) => setRadar("top_k", Number(event.target.value))} /></Field>
                <Field label="Fetch limit"><Input type="number" min="1" max="500" value={radarConfig.fetch_limit} onChange={(event) => setRadar("fetch_limit", Number(event.target.value))} /></Field>
                <Field label="最低相似度"><Input type="number" min="0" max="1" step="0.01" value={radarConfig.min_score} onChange={(event) => setRadar("min_score", Number(event.target.value))} /></Field>
                <Field label="计算模式"><select value={radarConfig.compute_mode} onChange={(event) => setRadar("compute_mode", event.target.value as RadarConfig["compute_mode"])} className={SELECT_CLASS}><option value="cloud">Cloud</option><option value="local">Local</option><option value="hybrid">Hybrid</option></select></Field>
                <Field label="Profile override"><Textarea rows={4} value={radarConfig.profile_override} onChange={(event) => setRadar("profile_override", event.target.value)} /></Field>
              </Section>
              <Section title="Worker">
                <Field label="URL"><Input value={connection.remote_url} onChange={(event) => { setConnection({ ...connection, remote_url: event.target.value }); setDirty(true); setNotice(null); }} placeholder="https://radar.example.workers.dev" /></Field>
                <Field label="Token">
                  <div className="flex gap-2">
                    <Input type="password" value={secretInputs.RADAR_TOKEN || ""} onChange={(event) => { setSecretInputs((current) => ({ ...current, RADAR_TOKEN: event.target.value })); setClearRadarToken(false); setDirty(true); setNotice(null); }} placeholder={connection.token_configured && !clearRadarToken ? "已配置" : "未配置"} autoComplete="off" />
                    {connection.token_configured && !clearRadarToken && <Button type="button" size="icon" variant="outline" onClick={() => { setClearRadarToken(true); setDirty(true); setNotice(null); }} aria-label="清除 Token" title="保存后清除"><Trash2 className="h-4 w-4" /></Button>}
                  </div>
                  {clearRadarToken && <span className="mt-1.5 block text-xs text-destructive">保存后清除</span>}
                </Field>
              </Section>
              <Section title="Embedding">
                <Field label="Provider"><select value={value("RADAR_EMBEDDING_PROVIDER")} onChange={(event) => setValue("RADAR_EMBEDDING_PROVIDER", event.target.value)} className={SELECT_CLASS}><option value="local">Local</option><option value="api">API</option><option value="lexical">Lexical</option></select></Field>
                <Field label="Model"><Input value={value("RADAR_EMBEDDING_MODEL")} onChange={(event) => setValue("RADAR_EMBEDDING_MODEL", event.target.value)} /></Field>
                {secretField("RADAR_EMBEDDING_API_KEY", "API Key", "留空复用全局 LLM API Key。")}
                <Field label="Base URL"><Input value={value("RADAR_EMBEDDING_BASE_URL")} onChange={(event) => setValue("RADAR_EMBEDDING_BASE_URL", event.target.value)} /></Field>
                <Field label="Task"><Input value={value("RADAR_EMBEDDING_TASK")} onChange={(event) => setValue("RADAR_EMBEDDING_TASK", event.target.value)} /></Field>
                <Field label="Prompt name"><Input value={value("RADAR_EMBEDDING_PROMPT_NAME")} onChange={(event) => setValue("RADAR_EMBEDDING_PROMPT_NAME", event.target.value)} /></Field>
                <Field label="Batch size"><Input type="number" min="1" max="1024" value={value("RADAR_EMBEDDING_BATCH_SIZE")} onChange={(event) => setValue("RADAR_EMBEDDING_BATCH_SIZE", event.target.value)} /></Field>
                <ToggleField label="Trust remote code" checked={isChecked("RADAR_EMBEDDING_TRUST_REMOTE_CODE", true)} onChange={(checked) => setValue("RADAR_EMBEDDING_TRUST_REMOTE_CODE", checked)} />
              </Section>
              <Section title="生成与日志">
                <ToggleField label="生成 LLM 摘要" checked={isChecked("RADAR_LLM_ENABLED", true)} onChange={(checked) => setValue("RADAR_LLM_ENABLED", checked)} />
                <ToggleField label="摘要失败则停止" checked={isChecked("RADAR_LLM_REQUIRED")} onChange={(checked) => setValue("RADAR_LLM_REQUIRED", checked)} />
                <ToggleField label="雷达调试日志" checked={isChecked("RADAR_DEBUG")} onChange={(checked) => setValue("RADAR_DEBUG", checked)} />
                <ToggleField label="项目调试模式" checked={radarConfig.debug} onChange={(checked) => setRadar("debug", checked)} />
              </Section>
              <Section title="邮件">
                <Field label="发件人"><Input value={value("RADAR_EMAIL_SENDER")} onChange={(event) => setValue("RADAR_EMAIL_SENDER", event.target.value)} /></Field>
                <Field label="收件人"><Input value={value("RADAR_EMAIL_RECEIVER")} onChange={(event) => setValue("RADAR_EMAIL_RECEIVER", event.target.value)} /></Field>
                {secretField("RADAR_EMAIL_PASSWORD", "Password / App Token")}
                <Field label="SMTP Host"><Input value={value("RADAR_SMTP_HOST")} onChange={(event) => setValue("RADAR_SMTP_HOST", event.target.value)} /></Field>
                <Field label="SMTP Port"><Input type="number" min="1" max="65535" value={value("RADAR_SMTP_PORT")} onChange={(event) => setValue("RADAR_SMTP_PORT", event.target.value)} /></Field>
                <ToggleField label="SMTP SSL" checked={isChecked("RADAR_SMTP_SSL", true)} onChange={(checked) => setValue("RADAR_SMTP_SSL", checked)} />
              </Section>
            </>
          )}

          {section === "integrations" && (
            <>
              <Section title="Semantic Scholar">
                {secretField("SEMANTIC_SCHOLAR_API_KEY", "API Key")}
              </Section>
              <Section title="OpenReview">
                <Field label="Email"><Input type="email" value={value("OPENREVIEW_EMAIL")} onChange={(event) => setValue("OPENREVIEW_EMAIL", event.target.value)} /></Field>
                {secretField("OPENREVIEW_PASSWORD", "Password")}
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
