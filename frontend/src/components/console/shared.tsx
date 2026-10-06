import { AlertTriangle, Loader2, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

export function LoadingState({ label = "Loading live data…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-24 text-slate-400">
      <Loader2 className="h-6 w-6 animate-spin" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50 py-20 text-center">
      <Inbox className="h-6 w-6 text-slate-400" />
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {detail && <p className="max-w-sm text-xs text-slate-400">{detail}</p>}
    </div>
  );
}

export function ApiOfflineNotice({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-rose-200 bg-rose-50 py-16 text-center">
      <AlertTriangle className="h-6 w-6 text-rose-500" />
      <p className="text-sm font-medium text-rose-700">Could not reach the API</p>
      <p className="max-w-md text-xs text-rose-500">{message}</p>
      <p className="text-xs text-slate-500">
        Start it with <code className="rounded bg-white px-1.5 py-0.5 font-mono">uvicorn agents.app:app --reload</code>
      </p>
      <button
        onClick={onRetry}
        className="mt-1 rounded-full border border-rose-300 bg-white px-4 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-100"
      >
        Retry
      </button>
    </div>
  );
}

export function KVRow({ k, v, className }: { k: string; v: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-4 border-b border-slate-100 py-2 text-sm last:border-0", className)}>
      <span className="shrink-0 text-slate-500">{k}</span>
      <span className="text-right font-medium text-slate-900 tabular-nums">{v}</span>
    </div>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="mb-2 text-[11px] font-bold uppercase tracking-widest text-slate-400">{children}</div>;
}
