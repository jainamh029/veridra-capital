import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { RefreshCw, Check, X, HelpCircle } from "lucide-react";
import { ConsoleShell, ConsolePageHeader } from "@/components/layout/ConsoleShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { StatusBadge, SeverityBadge, Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LoadingState, EmptyState, ApiOfflineNotice } from "@/components/console/shared";
import { money, titleCase } from "@/lib/utils";
import {
  getApprovalsPending, getApprovalsAll, decideApproval, ApiError, type ApprovalRecord,
} from "@/lib/api";

const FIELD_ORDER: [string, string][] = [
  ["fund_name", "Fund"], ["entity", "Paying entity / GP"], ["amount", "Amount"],
  ["bank_name", "Receiving bank"], ["routing_number", "Routing number"],
  ["account_number", "Account number"], ["due_date", "Due date"],
];

export default function Approvals() {
  const [scope, setScope] = useState<"pending" | "all">("pending");
  const [records, setRecords] = useState<ApprovalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    const fetcher = scope === "pending" ? getApprovalsPending : getApprovalsAll;
    fetcher()
      .then(setRecords)
      .catch((e) => setError(e.message ?? "request failed"))
      .finally(() => setLoading(false));
  }, [scope]);

  useEffect(() => { load(); }, [load]);

  return (
    <ConsoleShell>
      <ConsolePageHeader
        title="Payment Approvals"
        description="Every notice — cleared or flagged — waits here for a human decision. Approving records sign-off only; nothing here sends a wire."
        action={
          <div className="flex items-center gap-3">
            <Tabs value={scope} onValueChange={(v) => setScope(v as typeof scope)}>
              <TabsList>
                <TabsTrigger value="pending">Pending</TabsTrigger>
                <TabsTrigger value="all">All</TabsTrigger>
              </TabsList>
            </Tabs>
            <Button variant="subtle" size="sm" onClick={load}>
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </Button>
          </div>
        }
      />

      <div className="p-8">
        {loading && <LoadingState />}
        {!loading && error && <ApiOfflineNotice message={error} onRetry={load} />}
        {!loading && !error && records.length === 0 && (
          <EmptyState title="Nothing here" detail={scope === "pending" ? "Every notice has been decided." : "No approval records yet — run a notice through Fraud Verification."} />
        )}
        {!loading && !error && records.length > 0 && (
          <div className="space-y-5">
            {records.map((rec) => (
              <ApprovalCard key={rec.approval_id} record={rec} onDecided={load} />
            ))}
          </div>
        )}
      </div>
    </ConsoleShell>
  );
}

function ApprovalCard({ record, onDecided }: { record: ApprovalRecord; onDecided: () => void }) {
  const vr = record.verification_report;
  const ext = vr?.extracted ?? {};
  const decision = record.hub_decision || vr?.decision || "—";
  const severity = record.hub_severity || vr?.overall_severity || "none";
  const failed = vr?.failed_checks ?? [];
  const alert = vr?.alert;

  const [who, setWho] = useState(record.assigned_approver?.email ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const decided = record.state !== "PENDING_APPROVAL";

  async function decide(state: "APPROVED" | "REJECTED" | "NEEDS_MORE_INFO") {
    if (!who.trim()) { setMsg({ text: "Enter your email in the 'acting as' field first.", ok: false }); return; }
    setBusy(true); setMsg(null);
    try {
      await decideApproval(record.approval_id, { state, approver: who.trim(), note: note.trim() || null });
      setMsg({ text: `Recorded ${state}.`, ok: true });
      onDecided();
    } catch (e) {
      setMsg({ text: e instanceof ApiError ? String(e.message) : "Network error", ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.div layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-display text-lg font-semibold text-slate-900">
                {record.fund_name || (ext.fund_name as string) || record.fund_id || "Unknown fund"}
              </h3>
              <p className="mt-0.5 text-xs text-slate-400">
                {record.approval_id} · created {record.created_at} · assigned to{" "}
                {record.assigned_approver?.name ?? "unassigned"} &lt;{record.assigned_approver?.email ?? "?"}&gt;
              </p>
            </div>
            <StatusBadge status={record.state} />
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <StatusBadge status={decision} />
            <SeverityBadge severity={severity} />
            {vr?.confidence && <Badge variant="outline">confidence: {vr.confidence}</Badge>}
          </div>

          <div className="mt-4 grid gap-x-8 gap-y-1 sm:grid-cols-2">
            {FIELD_ORDER.filter(([k]) => ext[k] != null && ext[k] !== "").map(([k, label]) => (
              <div key={k} className="flex justify-between border-b border-slate-100 py-1.5 text-sm">
                <span className="text-slate-400">{label}</span>
                <span className="font-medium text-slate-800">{k === "amount" ? money(ext[k]) : String(ext[k])}</span>
              </div>
            ))}
          </div>

          {failed.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
              {failed.map((f) => <li key={f}>{titleCase(f)}</li>)}
            </ul>
          )}

          {alert && (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3">
              <div className="text-sm font-semibold text-amber-900">{alert.subject}</div>
              <pre className="mt-1.5 whitespace-pre-wrap font-mono text-[11.5px] leading-relaxed text-amber-900/75">{alert.body}</pre>
            </div>
          )}

          {decided ? (
            <div className="mt-5 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
              Decided <strong>{record.state}</strong> by {record.decision_by} on {record.decision_at}
              {record.decision_note && <> — “{record.decision_note}”</>}
            </div>
          ) : (
            <div className="mt-5 flex flex-wrap items-start gap-2.5">
              <Input
                value={who}
                onChange={(e) => setWho(e.target.value)}
                placeholder="your email (acting as)"
                className="w-56"
              />
              <Textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="note (optional)"
                rows={1}
                className="min-w-[220px] flex-1"
              />
              <div className="flex gap-2">
                <Button variant="pass" size="sm" disabled={busy} onClick={() => decide("APPROVED")}><Check className="h-3.5 w-3.5" /> Approve</Button>
                <Button variant="block" size="sm" disabled={busy} onClick={() => decide("REJECTED")}><X className="h-3.5 w-3.5" /> Reject</Button>
                <Button variant="review" size="sm" disabled={busy} onClick={() => decide("NEEDS_MORE_INFO")}><HelpCircle className="h-3.5 w-3.5" /> Needs info</Button>
              </div>
            </div>
          )}

          <AnimatePresence>
            {msg && (
              <motion.p
                initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                className={`mt-2 text-xs font-medium ${msg.ok ? "text-emerald-600" : "text-rose-600"}`}
              >
                {msg.text}
              </motion.p>
            )}
          </AnimatePresence>
        </CardContent>
      </Card>
    </motion.div>
  );
}
