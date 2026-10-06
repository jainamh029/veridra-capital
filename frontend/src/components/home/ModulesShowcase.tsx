import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { ShieldCheck, ClipboardCheck, Wallet, TrendingUp, FileStack, ArrowUpRight } from "lucide-react";

const MODULES = [
  {
    icon: ShieldCheck,
    tag: "Module 01",
    title: "Fraud Verification",
    desc: "A fine-tuned extraction model reads any capital call notice; a deterministic rules layer and a fine-tuned wire-fraud model cross-check bank, routing, entity, and sender domain against the fund's locked baseline.",
    stat: "1.000 precision / recall",
    to: "/console/verification",
  },
  {
    icon: ClipboardCheck,
    tag: "Module 02",
    title: "Payment Approvals",
    desc: "Every notice — cleared or flagged — opens a tracked, append-only approval record. A human always decides; the platform never executes a wire itself.",
    stat: "Full audit trail",
    to: "/console/approvals",
  },
  {
    icon: Wallet,
    tag: "Module 03",
    title: "Cash Planning",
    desc: "The confirmed cash position — historical ledger plus only APPROVED calls — reported separately from near-term obligations still pending. The two numbers are never merged.",
    stat: "Reconciled, per fund",
    to: "/console/cash-planning",
  },
  {
    icon: TrendingUp,
    tag: "Module 04",
    title: "Forecasting",
    desc: "A transparent, deterministic projection of each fund's next expected call, extrapolated from its own historical cadence — shown as a distinctly tentative third tier, never summed with actuals.",
    stat: "Explainable, no black box",
    to: "/console/forecasting",
  },
  {
    icon: FileStack,
    tag: "Module 05",
    title: "K-1 Routing",
    desc: "Identifies which fund and LP a Schedule K-1 belongs to and routes it to the right tax contact — deterministic fuzzy matching, with unresolved documents surfaced for review, never guessed.",
    stat: "10 / 10 match accuracy",
    to: "/console/k1-routing",
  },
];

const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { duration: 0.6, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] as const },
  }),
};

export function ModulesShowcase() {
  return (
    <section id="modules" className="relative bg-ink-900 px-6 py-32">
      <div className="mx-auto max-w-6xl">
        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-100px" }}
          custom={0}
          variants={fadeUp}
          className="mb-16 max-w-2xl"
        >
          <span className="text-xs font-bold uppercase tracking-[0.2em] text-gold-400">The platform</span>
          <h2 className="mt-4 font-display text-4xl font-semibold leading-tight text-ivory-50 sm:text-5xl">
            Five modules. One
            <span className="italic text-gold-300"> operational record.</span>
          </h2>
          <p className="mt-5 text-[16px] leading-relaxed text-ivory-300">
            Each module is a live, working system — not a mockup. Open the console to run a
            notice through the pipeline, decide a pending approval, or pull a fund's cash
            position, right now.
          </p>
        </motion.div>

        <div className="grid gap-5 md:grid-cols-2">
          {MODULES.map((m, i) => (
            <motion.div
              key={m.title}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-80px" }}
              custom={i}
              variants={fadeUp}
              className={m.title === "K-1 Routing" ? "md:col-span-2" : ""}
            >
              <Link
                to={m.to}
                className="group relative flex h-full flex-col justify-between overflow-hidden rounded-3xl border border-ink-line bg-ink-800/60 p-8 transition-all duration-300 hover:-translate-y-1 hover:border-gold-500/30 hover:bg-ink-800"
              >
                <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-gold-500/0 blur-3xl transition-colors duration-500 group-hover:bg-gold-500/10" />

                <div className="relative">
                  <div className="mb-6 flex items-center justify-between">
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-gold-500/25 bg-gold-500/10">
                      <m.icon className="h-5 w-5 text-gold-300" />
                    </div>
                    <span className="text-[11px] font-semibold uppercase tracking-widest text-ivory-500">{m.tag}</span>
                  </div>
                  <h3 className="font-display text-xl font-semibold text-ivory-50">{m.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-ivory-400">{m.desc}</p>
                </div>

                <div className="relative mt-8 flex items-center justify-between border-t border-ink-line pt-5">
                  <span className="text-xs font-semibold text-gold-300">{m.stat}</span>
                  <span className="flex items-center gap-1 text-xs font-medium text-ivory-400 transition-colors group-hover:text-gold-300">
                    Open module <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                  </span>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
