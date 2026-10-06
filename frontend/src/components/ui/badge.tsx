import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
  {
    variants: {
      variant: {
        pass: "border-emerald-300 bg-emerald-50 text-emerald-700",
        review: "border-amber-300 bg-amber-50 text-amber-700",
        block: "border-rose-300 bg-rose-50 text-rose-700",
        neutral: "border-slate-200 bg-slate-50 text-slate-600",
        gold: "border-gold-500/40 bg-gold-500/10 text-gold-300",
        outline: "border-slate-300 bg-transparent text-slate-600",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

const DECISION_VARIANT: Record<string, BadgeProps["variant"]> = {
  PASS: "pass", APPROVED: "pass", ROUTED: "pass",
  REVIEW: "review", NEEDS_MORE_INFO: "review", AWAITING_EXTRACTION: "review", PENDING_APPROVAL: "review", NEEDS_REVIEW: "block",
  BLOCK: "block", REJECTED: "block",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge variant={DECISION_VARIANT[status] ?? "neutral"} className={className}>
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

const SEVERITY_VARIANT: Record<string, BadgeProps["variant"]> = {
  high: "block", medium: "review", "medium-low": "review", low: "gold", none: "neutral",
};

export function SeverityBadge({ severity, className }: { severity: string; className?: string }) {
  return (
    <Badge variant={SEVERITY_VARIANT[severity] ?? "neutral"} className={className}>
      severity: {severity}
    </Badge>
  );
}
