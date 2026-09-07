import type { ReactNode } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, CheckCircle2, ExternalLink, Mail, Network, Save, Server, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function LinkButton({ href, children }: { href: string; children: ReactNode }) {
  return <Button variant="outline" size="sm" asChild><a href={href} target="_blank" rel="noreferrer">{children}<ExternalLink className="ml-2 h-3.5 w-3.5" /></a></Button>;
}

type RadarSetup = {
  llm_api_key: string;
  llm_base_url: string;
  llm_model: string;
  embedding_provider: "local" | "api" | "lexical";
  embedding_model: string;
  embedding_api_key: string;
  embedding_base_url: string;
  smtp_host: string;
  smtp_port: string;
  email_sender: string;
  email_receiver: string;
  email_password: string;
  remote_url: string;
  remote_token: string;
  categories: string;
  top_k: string;
  min_score: string;
  schedule_utc: string;
};

const STORAGE_KEY = "citemap.radar.setup.v1";
export const RADAR_SETUP_COMPLETE_KEY = "citemap.radar.setup.complete.v1";
const DAILY_ARXIV_MODEL = "jinaai/jina-embeddings-v5-text-nano-retrieval";

const DEFAULT_SETUP: RadarSetup = {
  llm_api_key: "",
  llm_base_url: "https://api.openai.com/v1",
  llm_model: "gpt-4o-mini",
  embedding_provider: "local",
  embedding_model: DAILY_ARXIV_MODEL,
  embedding_api_key: "",
  embedding_base_url: "https://api.openai.com/v1",
  smtp_host: "smtp.qq.com",
  smtp_port: "465",
  email_sender: "",
  email_receiver: "",
  email_password: "",
  remote_url: "",
  remote_token: "",
  categories: "cs.AI, cs.CV, cs.LG, cs.CL",
  top_k: "10",
  min_score: "0.35",
  schedule_utc: "22:00",
};

const STEPS = [
  { id: "model", label: "模型", icon: Sparkles, title: "选择论文排序模型", description: "默认复用 daily arxiv 的本地 SentenceTransformer。" },
  { id: "mail", label: "邮件", icon: Mail, title: "配置每日邮件", description: "Action 在电脑关闭时运行，邮件是主要提醒渠道。" },
  { id: "finish", label: "本地完成", icon: CheckCircle2, title: "完成本地配置", description: "保存本地设置后，进入云端配置。" },
] as const;

function Field({ label, value, onChange, type = "text", placeholder }: { label: string; value: string; onChange: (value: string) => void; type?: string; placeholder?: string }) {
  return <label className="space-y-1.5 text-sm"><span className="font-medium">{label}</span><Input type={type} value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} /></label>;
}

export function RadarSettings() {
  const navigate = useNavigate();
  const [setup, setSetup] = useState<RadarSetup>(() => {
    try { return { ...DEFAULT_SETUP, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") }; } catch { return DEFAULT_SETUP; }
  });
  const [step, setStep] = useState(0);
  const [saved, setSaved] = useState(false);
  const [completed, setCompleted] = useState(() => localStorage.getItem(RADAR_SETUP_COMPLETE_KEY) === "true");
  const update = (key: keyof RadarSetup, value: string) => setSetup((current) => ({ ...current, [key]: value }));
  const save = (markComplete = false) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(setup));
    if (markComplete) { localStorage.setItem(RADAR_SETUP_COMPLETE_KEY, "true"); setCompleted(true); navigate("/settings/radar/cloud"); }
    setSaved(true); window.setTimeout(() => setSaved(false), 1800);
  };
  const current = STEPS[step];

  const renderStep = () => {
    if (current.id === "model") return <div className="space-y-5"><div className="rounded-lg border bg-muted/30 p-4 text-sm leading-6"><p className="font-medium">daily arxiv 配置</p><p className="mt-1 text-muted-foreground">本地模型首次运行会下载。GitHub Action 已配置 Hugging Face cache，后续运行复用模型。Action 会用 LLM 生成每篇论文 TLDR。</p></div><label className="space-y-1.5 text-sm"><span className="font-medium">Embedding provider</span><select className="flex h-9 w-full rounded-md border bg-background px-3 text-sm" value={setup.embedding_provider} onChange={(event) => update("embedding_provider", event.target.value as RadarSetup["embedding_provider"])}><option value="local">Local SentenceTransformer</option><option value="api">OpenAI-compatible API</option><option value="lexical">Lexical fallback（仅测试）</option></select></label><Field label="Embedding Model" value={setup.embedding_model} onChange={(v) => update("embedding_model", v)} /><p className="text-xs text-muted-foreground">固定参数：task=retrieval，prompt_name=document，trust_remote_code=true。API 请求按 batch_size=64 分批。</p>{setup.embedding_provider === "api" && <><Field label="Embedding API Base URL" value={setup.embedding_base_url} onChange={(v) => update("embedding_base_url", v)} /><Field label="Embedding API Key" type="password" value={setup.embedding_api_key} onChange={(v) => update("embedding_api_key", v)} /></>}<div className="border-t pt-4"><p className="mb-3 text-sm font-medium">Action LLM / TLDR</p><div className="grid gap-3 md:grid-cols-2"><Field label="LLM Base URL" value={setup.llm_base_url} onChange={(v) => update("llm_base_url", v)} /><Field label="LLM Model" value={setup.llm_model} onChange={(v) => update("llm_model", v)} /><Field label="LLM API Key" type="password" value={setup.llm_api_key} onChange={(v) => update("llm_api_key", v)} /></div><p className="mt-2 text-xs text-muted-foreground">Action Secrets 中需要配置 LLM_API_KEY。LLM 失败默认降级为论文摘要，不阻止邮件。</p></div></div>;
    if (current.id === "mail") return <div className="space-y-5"><div className="rounded-lg border bg-muted/30 p-4 text-sm leading-6"><p className="font-medium">需要 SMTP 授权码</p><p className="mt-1 text-muted-foreground">QQ、Gmail 等邮箱通常需要单独生成授权码。不要填写普通登录密码。</p></div><div className="grid gap-4 md:grid-cols-2"><Field label="SMTP Host" value={setup.smtp_host} onChange={(v) => update("smtp_host", v)} /><Field label="SMTP Port" value={setup.smtp_port} onChange={(v) => update("smtp_port", v)} /><Field label="发件邮箱" value={setup.email_sender} onChange={(v) => update("email_sender", v)} /><Field label="收件邮箱" value={setup.email_receiver} onChange={(v) => update("email_receiver", v)} /><Field label="SMTP 授权码" type="password" value={setup.email_password} onChange={(v) => update("email_password", v)} /></div><div className="flex flex-wrap gap-2"><LinkButton href="https://service.mail.qq.com/detail/106/995">QQ 邮箱授权码帮助</LinkButton><LinkButton href="https://support.google.com/mail/answer/185833">Google App Password 帮助</LinkButton></div></div>;
    return <div className="space-y-5"><div className="rounded-lg border bg-primary/5 p-4 text-sm leading-6"><p className="font-medium">本地配置完成后进入云端</p><p className="mt-1 text-muted-foreground">下一步会配置 Cloudflare Worker、D1、GitHub Secrets、GitHub Variables、Action。两部分严格串行，云端未完成前不能进入论文雷达。</p></div><div className="space-y-3 text-sm">{[["模型", setup.embedding_provider === "local" ? setup.embedding_model : "API provider"], ["邮件", setup.email_sender && setup.email_receiver ? `${setup.email_sender} → ${setup.email_receiver}` : "尚未填写发件/收件邮箱"]].map(([label, value]) => <div key={label} className="flex items-center justify-between gap-4 border-b py-2"><span className="text-muted-foreground">{label}</span><span className="max-w-[70%] truncate text-right font-medium">{value}</span></div>)}</div></div>;
  };

  return <div className="mx-auto max-w-4xl space-y-6 p-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm text-muted-foreground">Step 1 · Local setup</p><h1 className="text-2xl font-semibold">论文雷达本地配置</h1><p className="mt-1 max-w-2xl text-sm text-muted-foreground">先完成本地模型与邮件配置。保存并完成后，自动进入云端配置。</p></div><Button variant="outline" onClick={() => save()}>{saved ? <Check className="mr-2 h-4 w-4" /> : <Save className="mr-2 h-4 w-4" />}{saved ? "已保存" : "保存草稿"}</Button></div>
    <div className="grid gap-2 md:grid-cols-3">{STEPS.map((item, index) => { const Icon = item.icon; return <button key={item.id} type="button" onClick={() => setStep(index)} className={`rounded-lg border p-3 text-left transition-colors ${index === step ? "border-primary bg-primary/5" : "bg-card hover:bg-muted/50"}`}><div className="flex items-center gap-2"><Icon className="h-4 w-4" /><span className="text-sm font-medium">{item.label}</span>{index < step && <Check className="ml-auto h-3.5 w-3.5 text-primary" />}</div><p className="mt-1 hidden text-xs text-muted-foreground md:block">{item.description}</p></button>; })}</div>
    <section className="rounded-xl border bg-card p-5"><div className="mb-6 flex items-start justify-between gap-4"><div><p className="text-sm text-muted-foreground">步骤 {step + 1} / {STEPS.length}</p><h2 className="mt-1 text-xl font-semibold">{current.title}</h2></div>{completed && <span className="rounded-full bg-primary/10 px-3 py-1 text-xs text-primary">已完成，可重新编辑</span>}</div>{renderStep()}<div className="mt-8 flex items-center justify-between border-t pt-5"><Button variant="ghost" onClick={() => setStep((value) => Math.max(0, value - 1))} disabled={step === 0}><ArrowLeft className="mr-2 h-4 w-4" />上一步</Button>{step < STEPS.length - 1 ? <Button onClick={() => { save(); setStep((value) => Math.min(STEPS.length - 1, value + 1)); }}>保存并继续<ArrowRight className="ml-2 h-4 w-4" /></Button> : <Button onClick={() => save(true)}><CheckCircle2 className="mr-2 h-4 w-4" />完成配置</Button>}</div></section>
    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground"><span className="inline-flex items-center gap-1"><Server className="h-3.5 w-3.5" />Step 1 本地</span><span className="inline-flex items-center gap-1"><Network className="h-3.5 w-3.5" />完成后进入 Step 2 云端</span></div>
  </div>;
}
