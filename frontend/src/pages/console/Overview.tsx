import { useEffect, useState, type ComponentType } from "react";
import { Link } from "react-router-dom";
import {
  ShieldCheck, ClipboardCheck, Wallet, TrendingUp, FileStack, ArrowUpRight, AlertTriangle,
} from "lucide-react";
import { ConsoleShell, ConsolePageHeader } from "@/components/layout/ConsoleShell";
import { Card, CardContent } from "@/components/ui/card";
import { LoadingState } from "@/components/console/shared";
import { money } from "@/lib/utils";
import {
  getHealth, getApprovalsPending, getCashPlanningAll, getForecastingAll, getK1Routing,
  type HealthOut, type ApprovalRecord, type CashPosition, type ForecastOut, type K1ListOut,
} from "@/lib/api";

export default function Overview() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthOut | null>(null);
  const [pending, setPending] = useState<ApprovalRecord[]>([]);
  const [cash, setCash] = useState<CashPosition[]>([]);
  const [forecast, setForecast] = useState<ForecastOut[]>([]);
  const [k1, setK1] = useState<K1ListOut | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([getHealth(), getApprovalsPending(), getCashPlanningAll(), getForecastingAll(), getK1Routing()])
      .then(([h, p, c, f, k]) => {
        if (!alive) return;
        setHealth(h); setPending(p); setCash(c); setForecast(f); setK1(k);
      })
      .catch((e) => alive && setError(e.message ?? "request failed"))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  const totalConfirmed = cash.reduce((s, c) => s + (c.confirmed_cash_balance || 0), 0);
  const totalNearTerm = cash.reduce((s, c) => s + (c.near_term_obligations?.total_not_yet_realized || 0), 0);
  const projectable = forecast.filter((f) => f.sufficient_history).length;
  const blocked = pending.filter((r) => r.hub_decision === "BLOCK").length;

  return (
    <ConsoleShell>
      <ConsolePageHeader
        title="Platform overview"
        description="Live status across all five modules, pulled straight from the running API."
      />

      <div className="p-8">
        {error && (
          <div className="mb-6 flex items-center gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            Could not reach the API ({error}). Start it with{" "}
            <code className="rounded bg-white px-1.5 py-0.5 font-mono text-xs">uvicorn agents.app:app --reload</code>.
          </div>
        )}

        {loading ? (
          <LoadingState label="Pulling live status from every module…" />
        ) : (
          <>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Funds onboarded" value={String(health?.funds ?? "—")} sub={`as of ${health?.as_of ?? "—"}`} />
              <StatCard label="Pending approvals" value={String(pending.length)} sub={blocked ? `${blocked} flagged BLOCK` : "none flagged"} tone={blocked ? "warn" : "ok"} />
              <StatCard label="Confirmed cash (all funds)" value={money(totalConfirmed)} sub={`${cash.length} funds reporting`} />
              <StatCard label="K-1s tracked" value={String(k1?.summary.total ?? 0)} sub={`${k1?.summary.needs_review ?? 0} need review`} tone={(k1?.summary.needs_review ?? 0) > 0 ? "warn" : "ok"} />
            </div>

            <div className="mt-8 grid gap-5 lg:grid-cols-3">
              <ModuleCard
                to="/console/verification"
                icon={ShieldCheck}
                title="Fraud Verification"
                desc="Submit a raw notice and watch extraction, rules, and the fraud model reconcile into one decision."
                cta="Run a notice"
              />
              <ModuleCard
                to="/console/approvals"
                icon={ClipboardCheck}
                title="Payment Approvals"
                desc={`${pending.length} record${pending.length === 1 ? "" : "s"} waiting on a human decision right now.`}
                cta="Review queue"
              />
              <ModuleCard
                to="/console/cash-planning"
                icon={Wallet}
                title="Cash Planning"
                desc={`${money(totalConfirmed)} confirmed · ${money(totalNearTerm)} known but not yet realized.`}
                cta="View positions"
              />
              <ModuleCard
                to="/console/forecasting"
                icon={TrendingUp}
                title="Forecasting"
                desc={`${projectable} of ${forecast.length} funds have enough history for a next-call projection.`}
                cta="View projections"
              />
              <ModuleCard
                to="/console/k1-routing"
                icon={FileStack}
                title="K-1 Routing"
                desc={`${k1?.summary.routed ?? 0} routed automatically, ${k1?.summary.needs_review ?? 0} awaiting manual review.`}
                cta="Open documents"
              />
            </div>
          </>
        )}
      </div>
    </ConsoleShell>
  );
}

function StatCard({ label, value, sub, tone = "neutral" }: {
  label: string; value: string; sub: string; tone?: "ok" | "warn" | "neutral";
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</div>
        <div className="mt-2 font-display text-3xl font-semibold text-slate-900">{value}</div>
        <div className={`mt-1 text-xs font-medium ${
          tone === "warn" ? "text-amber-600" : tone === "ok" ? "text-emerald-600" : "text-slate-400"
        }`}>{sub}</div>
      </CardContent>
    </Card>
  );
}

function ModuleCard({ to, icon: Icon, title, desc, cta }: {
  to: string; icon: ComponentType<{ className?: string }>; title: string; desc: string; cta: string;
}) {
  return (
    <Link to={to} className="group block">
      <Card className="h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
        <CardContent className="pt-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900">
            <Icon className="h-5 w-5 text-gold-400" />
          </div>
          <h3 className="mt-4 font-display text-lg font-semibold text-slate-900">{title}</h3>
          <p className="mt-2 text-sm leading-relaxed text-slate-500">{desc}</p>
          <div className="mt-5 flex items-center gap-1 text-sm font-medium text-slate-900">
            {cta} <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
