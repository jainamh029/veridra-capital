import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Send, CheckCircle2, XCircle, ShieldAlert, Loader2 } from "lucide-react";
import { ConsoleShell, ConsolePageHeader } from "@/components/layout/ConsoleShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { StatusBadge, SeverityBadge, Badge } from "@/components/ui/badge";
import { KVRow, SectionLabel } from "@/components/console/shared";
import { SAMPLE_NOTICES } from "@/lib/samples";
import { money, titleCase, cn } from "@/lib/utils";
import { postDecision, ApiError, type DecisionOut } from "@/lib/api";

const EXTRACTED_ORDER: [string, string][] = [
  ["fund_name", "Fund"], ["entity", "Sender / GP entity"], ["amount", "Amount"],
  ["due_date", "Due date"], ["bank_name", "Receiving bank"],
  ["routing_number", "Routing number"], ["account_number", "Account number"],
  ["purpose", "Purpose"],
];

const CHECK_LABEL: Record<string, string> = {
  routing_checksum: "ABA routing checksum",
  baseline_routing_match: "Routing number vs. fund file",
  baseline_bank_match: "Receiving bank vs. fund file",
  entity_name_match: "GP entity name vs. fund file",
  sender_domain_match: "Sender domain vs. authorized list",
  bank_change_language: "Unverified bank-change language",
};

export default function Verification() {
  const [noticeText, setNoticeText] = useState("");
  const [senderDomain, setSenderDomain] = useState("");
  const [senderEmail, setSenderEmail] = useState("");
  const [useModel, setUseModel] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DecisionOut | null>(null);
  const [activeSample, setActiveSample] = useState<string | null>(null);

  function loadSample(key: string) {
    const s = SAMPLE_NOTICES.find((x) => x.key === key);
    if (!s) return;
    setActiveSample(key);
    setNoticeText(s.notice_text);
    setSenderDomain(s.sender_domain ?? "");
    setSenderEmail(s.sender_email ?? "");
    setResult(null);
    setError(null);
  }

  async function submit() {
    if (!noticeText.trim()) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const out = await postDecision({
        notice_text: noticeText,
        sender_domain: senderDomain || null,
        sender_email: senderEmail || null,
        use_model: useModel,
      });
      setResult(out);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.message) : "Request failed — is the API running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ConsoleShell>
      <ConsolePageHeader
        title="Fraud Verification"
        description="Paste a raw capital call notice. Extraction, deterministic rules, and the fine-tuned fraud model run live and reconcile into one decision."
      />

      <div className="grid gap-6 p-8 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* --- input column --- */}
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Try a sample notice</CardTitle>
              <CardDescription>Real synthetic notices — one clean, two fraud types.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {SAMPLE_NOTICES.map((s) => (
                <button
                  key={s.key}
                  onClick={() => loadSample(s.key)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors",
                    activeSample === s.key
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-300 text-slate-600 hover:border-slate-900 hover:text-slate-900",
                    s.kind === "fraud" && activeSample !== s.key && "border-rose-200 text-rose-600 hover:border-rose-400",
                  )}
                >
                  <Sparkles className="h-3 w-3" /> {s.label}
                </button>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Notice</CardTitle>
              <CardDescription>Raw text as received — any format.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Notice text</Label>
                <Textarea
                  rows={14}
                  value={noticeText}
                  onChange={(e) => { setNoticeText(e.target.value); setActiveSample(null); }}
                  placeholder="Paste the full notice — email body, PDF text, whatever came in…"
                  className="font-mono text-[12.5px] leading-relaxed"
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label>Sender domain (optional)</Label>
                  <Input
                    value={senderDomain}
                    onChange={(e) => setSenderDomain(e.target.value)}
                    placeholder="from the mail envelope"
                  />
                </div>
                <div>
                  <Label>Sender email (optional)</Label>
                  <Input
                    value={senderEmail}
                    onChange={(e) => setSenderEmail(e.target.value)}
                    placeholder="investor.relations@…"
                  />
                </div>
              </div>
              <div className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3">
                <div>
                  <div className="text-sm font-medium text-slate-700">Use the fraud model</div>
                  <div className="text-xs text-slate-400">Adds the fine-tuned model as a second opinion alongside rules.</div>
                </div>
                <Switch checked={useModel} onCheckedChange={setUseModel} />
              </div>
              <Button variant="gold" size="lg" className="w-full" onClick={submit} disabled={loading || !noticeText.trim()}>
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                {loading ? "Running pipeline…" : "Run through pipeline"}
              </Button>
              {error && (
                <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{error}</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* --- result column --- */}
        <div className="space-y-5">
          <AnimatePresence mode="wait">
            {!result && !loading && (
              <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <div className="flex h-full min-h-[420px] flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 text-center">
                  <ShieldAlert className="h-8 w-8 text-slate-300" />
                  <p className="max-w-xs text-sm text-slate-400">
                    Run a notice to see extraction, every individual check, and the reconciled decision.
                  </p>
                </div>
              </motion.div>
            )}

            {result && (
              <motion.div
                key={result.status + result.decision}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="space-y-5"
              >
                <Card className={cn(
                  "border-2",
                  result.decision === "PASS" && "border-emerald-200",
                  result.decision === "REVIEW" && "border-amber-200",
                  result.decision === "BLOCK" && "border-rose-200",
                )}>
                  <CardContent className="pt-6">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={result.status === "NEEDS_ONBOARDING" ? "NEEDS_ONBOARDING" : result.decision} />
                      <SeverityBadge severity={result.overall_severity} />
                      <Badge variant="outline">confidence: {result.confidence}</Badge>
                      {result.fraud_labels.map((l) => (
                        <Badge key={l} variant="gold">{titleCase(l)}</Badge>
                      ))}
                    </div>
                    {result.status === "NEEDS_ONBOARDING" && (
                      <p className="mt-3 text-sm text-slate-500">{result.note}</p>
                    )}
                    {result.approval && (
                      <p className="mt-3 text-xs text-slate-400">
                        Approval record <span className="font-mono text-slate-600">{result.approval.approval_id}</span> opened — see Payment Approvals.
                      </p>
                    )}
                  </CardContent>
                </Card>

                {result.alert && (
                  <Card className="border-amber-200 bg-amber-50/40">
                    <CardHeader>
                      <CardTitle className="text-amber-900">{result.alert.subject}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <pre className="whitespace-pre-wrap font-mono text-[12px] leading-relaxed text-amber-900/80">{result.alert.body}</pre>
                    </CardContent>
                  </Card>
                )}

                <Card>
                  <CardHeader><CardTitle>Extracted fields</CardTitle></CardHeader>
                  <CardContent>
                    {EXTRACTED_ORDER.filter(([k]) => result.extracted[k] != null && result.extracted[k] !== "").map(([k, label]) => (
                      <KVRow key={k} k={label} v={k === "amount" ? money(result.extracted[k]) : String(result.extracted[k])} />
                    ))}
                  </CardContent>
                </Card>

                {result.checks && (
                  <Card>
                    <CardHeader><CardTitle>Every check, independently</CardTitle></CardHeader>
                    <CardContent className="space-y-2">
                      {Object.entries(result.checks).map(([key, cv]) => (
                        <div key={key} className={cn(
                          "flex items-start gap-3 rounded-xl border px-4 py-3",
                          cv.passed ? "border-emerald-100 bg-emerald-50/50" : "border-rose-100 bg-rose-50/50",
                        )}>
                          {cv.passed
                            ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                            : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />}
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-sm font-medium text-slate-800">{CHECK_LABEL[key] ?? titleCase(key)}</span>
                              {!cv.passed && <SeverityBadge severity={cv.severity} />}
                            </div>
                            {cv.detail && <p className="mt-0.5 text-xs text-slate-500">{cv.detail}</p>}
                            {!cv.passed && (cv.observed != null || cv.baseline != null) && (
                              <p className="mt-1 font-mono text-[11px] text-slate-400">
                                observed: {String(cv.observed)} · on file: {String(cv.baseline)}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {result.fund_baseline && (
                  <Card>
                    <CardHeader><CardTitle>Matched fund baseline</CardTitle></CardHeader>
                    <CardContent>
                      <KVRow k="Fund" v={result.fund_baseline.fund_name} />
                      <KVRow k="GP entity on file" v={result.fund_baseline.gp_entity} />
                      <KVRow k="Bank on file" v={result.fund_baseline.bank} />
                      <KVRow k="Routing on file" v={result.fund_baseline.routing} />
                      <KVRow k="Authorized domains" v={result.fund_baseline.authorized_domains.join(", ")} />
                    </CardContent>
                  </Card>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </ConsoleShell>
  );
}
