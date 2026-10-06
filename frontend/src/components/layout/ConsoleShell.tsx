import { NavLink, Link } from "react-router-dom";
import {
  LayoutGrid, ShieldCheck, ClipboardCheck, Wallet, TrendingUp, FileStack, ArrowUpRight, Home,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";

const NAV = [
  { to: "/console", label: "Overview", icon: LayoutGrid, end: true },
  { to: "/console/verification", label: "Fraud Verification", icon: ShieldCheck },
  { to: "/console/approvals", label: "Payment Approvals", icon: ClipboardCheck },
  { to: "/console/cash-planning", label: "Cash Planning", icon: Wallet },
  { to: "/console/forecasting", label: "Forecasting", icon: TrendingUp },
  { to: "/console/k1-routing", label: "K-1 Routing", icon: FileStack },
];

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"checking" | "up" | "down">("checking");

  useEffect(() => {
    let alive = true;
    getHealth().then(() => alive && setStatus("up")).catch(() => alive && setStatus("down"));
    return () => { alive = false; };
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="flex">
        <aside className="fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-slate-200 bg-white">
          <Link to="/" className="flex items-center gap-2.5 px-6 py-6">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-900">
              <span className="font-display text-sm font-semibold text-gold-400">V</span>
            </div>
            <div>
              <div className="font-display text-[15px] font-semibold leading-none text-slate-900">Veridra</div>
              <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Console</div>
            </div>
          </Link>

          <nav className="flex-1 space-y-1 px-3">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                    isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
                  )
                }
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="border-t border-slate-200 px-4 py-4">
            <div className="flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2.5 text-xs">
              <span
                className={cn(
                  "h-2 w-2 shrink-0 rounded-full",
                  status === "up" && "bg-emerald-500",
                  status === "down" && "bg-rose-500",
                  status === "checking" && "animate-pulse bg-slate-300",
                )}
              />
              <span className="font-medium text-slate-600">
                {status === "up" && "API connected"}
                {status === "down" && "API unreachable"}
                {status === "checking" && "Checking API…"}
              </span>
            </div>
            <Link
              to="/"
              className="mt-3 flex items-center gap-1.5 px-1 text-xs font-medium text-slate-400 hover:text-slate-700"
            >
              <Home className="h-3.5 w-3.5" /> Back to site <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>
        </aside>

        <main className="ml-64 min-h-screen flex-1">{children}</main>
      </div>
    </div>
  );
}

export function ConsolePageHeader({
  title, description, action,
}: { title: string; description: string; action?: React.ReactNode }) {
  return (
    <div className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 px-8 py-5 backdrop-blur">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-slate-900">{title}</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">{description}</p>
        </div>
        {action}
      </div>
    </div>
  );
}
