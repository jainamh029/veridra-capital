import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { ConsoleShell, ConsolePageHeader } from "@/components/layout/ConsoleShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { LoadingState, EmptyState, ApiOfflineNotice } from "@/components/console/shared";
import { money } from "@/lib/utils";
import { getCashPlanningAll, type CashPosition } from "@/lib/api";

export default function CashPlanning() {
  const [funds, setFunds] = useState<CashPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [narrative, setNarrative] = useState(false);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    getCashPlanningAll({ narrative })
      .then(setFunds)
      .catch((e) => setError(e.message ?? "request failed"))
      .finally(() => setLoading(false));
  }, [narrative]);

  useEffect(() => { load(); }, [load]);

  const withPending = funds.filter((f) => f.near_term_obligations.count > 0).length;

  return (
    <ConsoleShell>
      <ConsolePageHeader
        title="Cash Planning"
        description="Confirmed cash — historical ledger plus only APPROVED calls — reported separately from near-term obligations still pending. Never merged."
        action={
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
              <Switch checked={narrative} onCheckedChange={setNarrative} /> Narrative
            </label>
            <Button variant="subtle" size="sm" onClick={load}><RefreshCw className="h-3.5 w-3.5" /> Refresh</Button>
          </div>
        }
      />

      <div className="p-8">
        {loading && <LoadingState />}
        {!loading && error && <ApiOfflineNotice message={error} onRetry={load} />}
        {!loading && !error && funds.length === 0 && <EmptyState title="No funds found" />}
        {!loading && !error && funds.length > 0 && (
          <>
            <p className="mb-5 text-sm text-slate-400">{funds.length} funds · {withPending} with a near-term call</p>
            <div className="grid gap-5 lg:grid-cols-2">
              {funds.map((f) => <FundCashCard key={f.fund_id} fund={f} />)}
            </div>
          </>
        )}
      </div>
    </ConsoleShell>
  );
}

function FundCashCard({ fund }: { fund: CashPosition }) {
  const near = fund.near_term_obligations;
  const recon = fund.reconciliation;
  const comp = fund.confirmed_components;

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="font-display text-lg font-semibold text-slate-900">{fund.fund_name}</h3>
            <p className="mt-0.5 text-xs text-slate-400">
              {fund.fund_id} · ledger as of {fund.as_of_ledger} · reference {fund.reference_date}
            </p>
          </div>
          <Badge variant={recon.ok ? "pass" : "block"}>
            {recon.ok ? "reconciled" : `RECONCILE FAIL (Δ ${money(recon.delta)})`}
          </Badge>
        </div>

        <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50/60 px-5 py-4">
          <div className="text-[11px] font-bold uppercase tracking-wide text-emerald-700">Confirmed cash balance</div>
          <div className="mt-1 font-display text-3xl font-semibold text-emerald-700">{money(fund.confirmed_cash_balance)}</div>
          <div className="mt-3 space-y-1 text-xs text-emerald-900/70">
            <div className="flex justify-between"><span>Historical ledger position</span><span className="font-mono">{money(comp.historical_ledger_balance)}</span></div>
            <div className="flex justify-between"><span>+ Approved capital calls ({comp.approved_capital_calls_count})</span><span className="font-mono">{money(comp.approved_capital_calls_total)}</span></div>
          </div>
        </div>

        <div className="mt-3 rounded-2xl border border-amber-200 border-l-4 border-l-amber-400 bg-amber-50/60 px-5 py-4">
          <div className="text-[11px] font-bold uppercase tracking-wide text-amber-700">
            Known upcoming — not in the balance above
          </div>
          <div className="mt-0.5 text-xs text-amber-900/60">
            Pending calls due within {near.horizon_days} days
            {near.pending_outside_window ? ` · ${near.pending_outside_window} more beyond this window` : ""}
          </div>
          {near.items.length === 0 ? (
            <p className="mt-2 text-sm text-amber-900/50">No calls pending in this window.</p>
          ) : (
            <>
              <div className="mt-2 space-y-1">
                {near.items.slice(0, 6).map((it, i) => (
                  <div key={i} className="flex justify-between text-xs text-amber-900/80">
                    <span>due {it.due_date}</span><span className="font-mono">{money(it.amount)}</span>
                  </div>
                ))}
              </div>
              <div className="mt-2 border-t border-amber-200 pt-2 text-sm font-semibold text-amber-900">
                Total known but not yet realized: {money(near.total_not_yet_realized)}
                <span className="ml-1 font-normal text-amber-700">({near.count} call{near.count === 1 ? "" : "s"})</span>
              </div>
            </>
          )}
        </div>

        <p className="mt-3 text-xs text-slate-400">
          Excluded (no cash effect): {fund.excluded_from_balance.REJECTED} rejected, {fund.excluded_from_balance.NEEDS_MORE_INFO} needs-more-info.
        </p>

        {fund.narrative?.narrative && (
          <div className="mt-3 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">{fund.narrative.narrative}</div>
        )}
        {fund.narrative && !fund.narrative.generated && (
          <div className="mt-3 rounded-xl bg-slate-50 px-4 py-3 text-xs text-slate-400">
            narrative unavailable — {fund.narrative.reason}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
