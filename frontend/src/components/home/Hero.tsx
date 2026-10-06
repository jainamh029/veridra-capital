import { Suspense, lazy } from "react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowRight, ChevronDown } from "lucide-react";

const HeroScene = lazy(() => import("./HeroScene").then((m) => ({ default: m.HeroScene })));

export function Hero() {
  return (
    <section className="relative flex min-h-screen items-center overflow-hidden bg-ink-900">
      <div className="pointer-events-none absolute inset-0 bg-noise opacity-40" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[60vh] bg-[radial-gradient(ellipse_at_top,rgba(203,161,53,0.16),transparent_65%)]" />
      <div className="pointer-events-none absolute -right-1/4 top-1/3 h-[600px] w-[600px] rounded-full bg-gold-500/10 blur-[140px]" />

      <div className="absolute inset-0">
        <Suspense fallback={null}>
          <HeroScene />
        </Suspense>
      </div>

      <div className="relative z-10 mx-auto w-full max-w-6xl px-6 pt-28">
        <div className="grid items-center gap-10 md:grid-cols-[1.1fr_0.9fr]">
          <div>
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.1 }}
              className="mb-6 inline-flex items-center gap-2 rounded-full border border-gold-500/30 bg-gold-500/5 px-4 py-1.5 text-xs font-medium tracking-wide text-gold-300"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-gold-400" />
              Fine-tuned models · deterministic rules · human approval
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="font-display text-[13vw] leading-[0.98] tracking-tight text-ivory-50 sm:text-6xl md:text-[64px] lg:text-[72px]"
            >
              The operating
              <br />
              system for
              <br />
              <span className="gold-gradient-text italic">fund finance.</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.4 }}
              className="mt-7 max-w-lg text-balance text-[17px] leading-relaxed text-ivory-300"
            >
              Veridra Capital's internal platform verifies every capital call notice for
              wire fraud, routes it through human approval, plans cash, forecasts the next
              call, and matches every Schedule K-1 — end to end, in one console.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.55 }}
              className="mt-10 flex flex-wrap items-center gap-4"
            >
              <Link
                to="/console"
                className="group inline-flex items-center gap-2 rounded-full bg-gold-500 px-7 py-3.5 text-sm font-semibold text-ink-950 shadow-[0_14px_40px_-10px_rgba(203,161,53,0.6)] transition-transform hover:scale-[1.03] hover:bg-gold-400"
              >
                Enter the Console
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
              <a
                href="#pipeline"
                className="inline-flex items-center gap-2 rounded-full border border-ink-line px-7 py-3.5 text-sm font-medium text-ivory-100 transition-colors hover:border-gold-500/40 hover:text-gold-300"
              >
                See how it works
              </a>
            </motion.div>

            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.8, delay: 0.8 }}
              className="mt-14 flex flex-wrap gap-x-10 gap-y-4 border-t border-ink-line pt-8 text-ivory-500"
            >
              {[
                ["1.000", "fraud F1 score"],
                ["0%", "false positives"],
                ["10", "funds onboarded"],
                ["32,259", "notices evaluated"],
              ].map(([n, l]) => (
                <div key={l}>
                  <div className="font-display text-2xl font-semibold text-ivory-50">{n}</div>
                  <div className="text-xs">{l}</div>
                </div>
              ))}
            </motion.div>
          </div>
        </div>
      </div>

      <motion.div
        animate={{ y: [0, 8, 0] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
        className="absolute bottom-8 left-1/2 z-10 -translate-x-1/2 text-ivory-500"
      >
        <ChevronDown className="h-5 w-5" />
      </motion.div>
    </section>
  );
}
