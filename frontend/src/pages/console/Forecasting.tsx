import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
import { ConsoleShell, ConsolePageHeader } from "@/components/layout/ConsoleShell";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { LoadingState, EmptyState, ApiOfflineNotice } from "@/components/console/shared";
import { money } from "@/lib/utils";
import { getForecastingAll, type ForecastOut } from "@/lib/api";

export default function Forecasting() {
  const [funds, setFunds] = useState<ForecastOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [narrative, setNarrative] = useState(false);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    getForecastingAll({ narrative })
      .then(setFunds)
      .catch((e) => setError(e.message ?? "request failed"))
      .finally(() => setLoading(false));
  }, [narrative]);

  useEffect(() => { load(); }, [load]);

  const projectable = funds.filter((f) => f.sufficient_history).length;

  return (
    <ConsoleShell>
      <ConsolePageHeader
        title="Scenario / Forecasting"
        description="Three tiers, never added together: confirmed cash, known pending obligations, and a projected next call extrapolated from the fund's own cadence."
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
            <p className="mb-5 text-sm text-slate-400">{funds.length} funds · {projectable} with enough history to project</p>
            <div className="grid gap-5 lg:grid-cols-2">
              {funds.map((f) => <FundForecastCard key={f.fund_id} fund={f} />)}
            </div>
          </>
        )}
      </div>
    </ConsoleShell>
  );
}

function FundForecastCard({ fund }: { fund: ForecastOut }) {
  const ctx = fund.context;
  const chartData = (fund.history_used ?? []).slice(-10).map((h) => ({
    date: h.date.slice(5), amount: h.amount,
  }));

  return (
    <Card>
      <CardContent className="pt-6">
        <div>
          <h3 className="font-display text-lg font-semibold text-slate-900">{fund.fund_name}</h3>
          <p className="mt-0.5 text-xs text-slate-400">
            {fund.fund_id} · vantage {fund.as_of} · ledger as of {ctx.as_of_ledger}
          </p>
        </div>

        <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50/60 px-5 py-3.5">
          <div className="text-[11px] font-bold uppercase tracking-wide text-emerald-700">1 · Confirmed cash balance</div>
          <div className="mt-0.5 font-display text-2xl font-semibold text-emerald-700">{money(ctx.confirmed_cash_balance)}</div>
        </div>

        <div className="mt-3 rounded-2xl border border-amber-200 border-l-4 border-l-amber-400 bg-amber-50/60 px-5 py-3.5">
          <div className="text-[11px] font-bold uppercase tracking-wide text-amber-700">2 · Known pending obligations</div>
          <div className="mt-0.5 text-xl font-semibold text-amber-900">{money(ctx.near_term_obligations_total)}</div>
          <div className="text-xs text-amber-700/70">{ctx.near_term_obligations_count} pending call(s) in the near-term window — not in the balance above.</div>
        </div>

        {!fund.sufficient_history ? (
          <div className="mt-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
            <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400">3 · Projected next call — none available</div>
            <p className="mt-1 text-sm text-slate-500">
              <strong>No projection for this fund.</strong> {fund.reason ?? "not enough confirmed call history"}. This is the
              absence of a projection, not a $0 estimate.
            </p>
          </div>
        ) : (
          <div className="mt-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-4">
            <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400">3 · Projected next call — estimate, not an obligation</div>
            <p className="mt-1 text-xs italic text-slate-400">
              Simple historical extrapolation — not a forecasting model, not a real obligation.
              {fund.next_expected_call?.overdue_relative_to_as_of && (
                <strong className="text-slate-600"> Point estimate already before {fund.as_of} — a call may be due.</strong>
              )}
            </p>
            {fund.basis?.low_confidence && (
              <p className="mt-1 text-xs font-medium text-amber-600">
                ⚠ Low confidence ({fund.next_expected_call?.confidence}) — only {fund.basis.interval_sample_size} historical gap(s).
              </p>
            )}
            <div className="mt-2 text-lg font-semibold text-slate-600">
              ~ {money(fund.next_expected_call?.estimated_amount)}
              <span className="ml-2 text-xs font-normal text-slate-400">
                window {fund.next_expected_call?.window_start} → {fund.next_expected_call?.window_end}
              </span>
            </div>

            {chartData.length > 0 && (
              <div className="mt-3 h-32">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="#e2e8f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} axisLine={false} tickLine={false} width={48}
                      tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                    <Tooltip formatter={(v) => money(typeof v === "number" ? v : Number(v))} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Bar dataKey="amount" radius={[4, 4, 0, 0]}>
                      {chartData.map((_, i) => <Cell key={i} fill={i === chartData.length - 1 ? "#cba135" : "#cbd5e1"} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            <div className="mt-2 text-[11px] text-slate-400">method: {fund.method}</div>
          </div>
        )}

        {fund.narrative?.narrative && (
          <div className="mt-3 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">{fund.narrative.narrative}</div>
        )}
      </CardContent>
    </Card>
  );
}
