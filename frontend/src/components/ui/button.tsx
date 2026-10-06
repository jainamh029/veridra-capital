import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium transition-all duration-200 disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
  {
    variants: {
      variant: {
        gold: "bg-gold-500 text-ink-950 hover:bg-gold-400 shadow-[0_10px_30px_-8px_rgba(203,161,53,0.55)] focus-visible:ring-gold-500",
        ghost: "bg-transparent text-ivory-100 border border-ink-line hover:border-gold-500/50 hover:text-gold-300 focus-visible:ring-gold-500",
        outline: "bg-transparent border border-slate-300 text-slate-700 hover:border-slate-900 hover:text-slate-900 focus-visible:ring-slate-400",
        solid: "bg-slate-900 text-white hover:bg-slate-800 focus-visible:ring-slate-500",
        subtle: "bg-slate-100 text-slate-700 hover:bg-slate-200 focus-visible:ring-slate-400",
        pass: "bg-emerald-600 text-white hover:bg-emerald-700 focus-visible:ring-emerald-500",
        block: "bg-rose-600 text-white hover:bg-rose-700 focus-visible:ring-rose-500",
        review: "bg-amber-500 text-white hover:bg-amber-600 focus-visible:ring-amber-400",
        link: "bg-transparent text-gold-400 hover:text-gold-300 rounded-none p-0 underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3.5 text-xs",
        md: "h-11 px-6 text-sm",
        lg: "h-13 px-8 text-base",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "solid", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
);
Button.displayName = "Button";
