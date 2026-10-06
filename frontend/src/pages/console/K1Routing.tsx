import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { RefreshCw, RotateCw, Send, Sparkles, Loader2 } from "lucide-react";
import { ConsoleShell, ConsolePageHeader } from "@/components/layout/ConsoleShell";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { LoadingState, EmptyState, ApiOfflineNotice, KVRow } from "@/components/console/shared";
import { money, titleCase } from "@/lib/utils";
import {
  getK1Routing, ingestK1, retryPendingK1, getK1Samples,
  type K1ListOut, type K1Document, type K1Sample,
} from "@/lib/api";

export default function K1Routing() {
  const [data, setData] = useState<K1ListOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const [docText, setDocText] = useState("");
  const [samples, setSamples] = useState<K1Sample[]>([]);
  const [ingesting, setIngesting] = useState(false);
  const [ingestMsg, setIngestMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    getK1Routing().then(setData).catch((e) => setError(e.message ?? "request failed")).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { getK1Samples().then(setSamples).catch(() => {}); }, []);

  async function retry() {
    setRetrying(true);
    try { await retryPendingK1(); load(); } finally { setRetrying(false); }
  }

  async function submitIngest() {
    if (!docText.trim()) return;
    setIngesting(true); setIngestMsg(null);
    try {
      const rec = await ingestK1(docText);
      setIngestMsg({ text: `Ingested — status ${rec.status}.`, ok: true });
      setDocText("");
      load();
    } catch (e) {
      setIngestMsg({ text: e instanceof Error ? e.message : "Ingest failed", ok: false });
    } finally {
      setIngesting(false);
    }
  }

  return (
    <ConsoleShell>
      <ConsolePageHeader
        title="K-1 Routing"
        description="Identifies which fund and LP a Schedule K-1 belongs to and routes it. No wire, no fraud check — deterministic matching only, or NEEDS_REVIEW."
        action={
          <div className="flex items-center gap-2">
            <Button variant="subtle" size="sm" onClick={retry} disabled={retrying}>
              {retrying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCw className="h-3.5 w-3.5" />}
              Retry pending
            </Button>
            <Button variant="subtle" size="sm" onClick={load}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>
          </div>
        }
      />

      <div className="grid gap-6 p-8 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Ingest a K-1</CardTitle>
              <CardDescription>Raw Schedule K-1 text — extraction and matching run immediately.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {samples.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {samples.map((s) => (
                    <button
                      key={s.doc_id}
                      onClick={() => setDocText(s.text)}
                      className="flex items-center gap-1.5 rounded-full border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    >
                      <Sparkles className="h-3 w-3" /> {s.fund_id} / {s.lp_id}
                    </button>
                  ))}
                </div>
              )}
              <Textarea
                rows={16}
                value={docText}
                onChange={(e) => setDocText(e.target.value)}
                placeholder="Paste Schedule K-1 text, or click a sample above…"
                className="font-mono text-[12px] leading-relaxed"
              />
              <Button variant="gold" className="w-full" onClick={submitIngest} disabled={ingesting || !docText.trim()}>
                {ingesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                {ingesting ? "Processing…" : "Ingest document"}
              </Button>
              {ingestMsg && (
                <p className={`text-xs font-medium ${ingestMsg.ok ? "text-emerald-600" : "text-rose-600"}`}>{ingestMsg.text}</p>
              )}
            </CardContent>
          </Card>

          {data && (
            <Card>
              <CardContent className="grid grid-cols-2 gap-3 pt-6 text-center">
                <MiniStat label="Total" value={data.summary.total} />
                <MiniStat label="Routed" value={data.summary.routed} tone="emerald" />
                <MiniStat label="Needs review" value={data.summary.needs_review} tone="rose" />
                <MiniStat label="Awaiting extraction" value={data.summary.awaiting_extraction} tone="amber" />
              </CardContent>
            </Card>
          )}
        </div>

        <div>
          {loading && <LoadingState />}
          {!loading && error && <ApiOfflineNotice message={error} onRetry={load} />}
          {!loading && !error && data && data.documents.length === 0 && (
            <EmptyState title="No K-1 documents tracked yet" detail="Ingest one on the left to see it routed here." />
          )}
          {!loading && !error && data && data.documents.length > 0 && (
            <div className="space-y-4">
              {data.documents.map((doc) => <K1Card key={doc.doc_id} doc={doc} />)}
            </div>
          )}
        </div>
      </div>
    </ConsoleShell>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: number; tone?: "emerald" | "rose" | "amber" }) {
  const color = tone === "emerald" ? "text-emerald-600" : tone === "rose" ? "text-rose-600" : tone === "amber" ? "text-amber-600" : "text-slate-900";
  return (
    <div>
      <div className={`font-display text-2xl font-semibold ${color}`}>{value}</div>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</div>
    </div>
  );
}

function K1Card({ doc }: { doc: K1Document }) {
  const awaiting = doc.status === "AWAITING_EXTRACTION";
  const routed = doc.status === "ROUTED";

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className={awaiting ? "border-amber-200 bg-amber-50/30" : routed ? "border-emerald-200" : "border-rose-200"}>
        <CardContent className="pt-6">
          <div className="flex items-start justify-between gap-3">
            <h3 className="font-mono text-sm font-semibold text-slate-800">{doc.doc_id}</h3>
            <StatusBadge status={doc.status} />
          </div>
          <p className="mt-1 text-xs text-slate-400">
            case: {doc.case ?? "—"} · received {doc.received_at}
            {doc.retry_count > 0 && ` · retries: ${doc.retry_count}`}
          </p>

          {awaiting ? (
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
              <div className="text-xs font-bold uppercase tracking-wide text-amber-700">Not processed yet</div>
              <p className="mt-1 text-sm text-amber-900/80">
                The extraction model was unavailable. Queued for retry — not routed, not reviewed, nothing downgraded.
              </p>
              {doc.extraction_error && <p className="mt-1 font-mono text-[11px] text-amber-700/60">{doc.extraction_error}</p>}
            </div>
          ) : (
            <>
              {doc.extracted && (
                <div className="mt-3">
                  <KVRow k="Extracted fund" v={doc.extracted.fund_name ?? "—"} />
                  <KVRow k="Extracted LP" v={doc.extracted.lp_name ?? "—"} />
                  <KVRow k="Tax year" v={doc.extracted.tax_year ?? "—"} />
                  <KVRow k="Ordinary business income" v={money(doc.extracted.ordinary_business_income)} />
                  <KVRow k="Guaranteed payments" v={money(doc.extracted.guaranteed_payments)} />
                </div>
              )}

              {routed ? (
                <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
                  <div className="text-xs font-bold uppercase tracking-wide text-emerald-700">Routed</div>
                  {doc.matched_fund && (
                    <p className="mt-1 text-sm text-emerald-900/80">
                      Fund: {doc.matched_fund.fund_name} ({doc.matched_fund.fund_id}) —{" "}
                      {doc.matched_fund.exact ? "exact" : `fuzzy ${doc.matched_fund.match_score}%`}
                    </p>
                  )}
                  {doc.matched_lp && (
                    <p className="text-sm text-emerald-900/80">
                      LP: {doc.matched_lp.lp_name} ({doc.matched_lp.lp_id}) —{" "}
                      {doc.matched_lp.exact ? "exact" : `fuzzy ${doc.matched_lp.match_score}%`}
                    </p>
                  )}
                  {doc.routed_to && (
                    <p className="mt-1 text-xs text-emerald-700/70">
                      Delivered to {doc.routed_to.recipient} · queue {doc.routed_to.queue} · ref {doc.routed_to.recipient_ref}
                    </p>
                  )}
                </div>
              ) : (
                <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3">
                  <div className="text-xs font-bold uppercase tracking-wide text-rose-700">Needs review — not routed</div>
                  <p className="mt-1 text-sm font-semibold text-rose-900">{titleCase(doc.review_reason)}</p>
                  {doc.review_detail && <p className="text-sm text-rose-900/70">{doc.review_detail}</p>}
                  {doc.matched_fund && (
                    <p className="mt-1 text-xs text-rose-700/70">
                      Closest fund match: {doc.matched_fund.fund_name} ({doc.matched_fund.match_score}%)
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
