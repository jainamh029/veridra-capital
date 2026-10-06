import { motion } from "framer-motion";
import { Lock, GitBranch, Users, DatabaseZap } from "lucide-react";

const PRINCIPLES = [
  {
    icon: GitBranch,
    title: "Deterministic where it counts",
    desc: "Baseline comparisons — routing, bank, entity, domain — are exact-string checks in code, never left to a model to eyeball.",
  },
  {
    icon: Users,
    title: "Human approval, always",
    desc: "PASS, REVIEW, and BLOCK all open a tracked approval record. The platform advises; a person decides. No wire is ever sent automatically.",
  },
  {
    icon: Lock,
    title: "Immutable audit trail",
    desc: "Approval events are append-only. A decision is never edited — only reversed, which opens a new record that references the old one.",
  },
  {
    icon: DatabaseZap,
    title: "Synthetic data, honestly labeled",
    desc: "Every fund, notice, and balance in this console is synthetically generated for demonstration. Every page says so.",
  },
];

export function TrustSection() {
  return (
    <section id="trust" className="relative bg-ink-950 px-6 py-32">
      <div className="mx-auto max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6 }}
          className="mb-16 max-w-2xl"
        >
          <span className="text-xs font-bold uppercase tracking-[0.2em] text-gold-400">Architecture</span>
          <h2 className="mt-4 font-display text-4xl font-semibold leading-tight text-ivory-50 sm:text-5xl">
            Built to be
            <span className="italic text-gold-300"> trusted, not just fast.</span>
          </h2>
        </motion.div>

        <div className="grid gap-5 md:grid-cols-2">
          {PRINCIPLES.map((p, i) => (
            <motion.div
              key={p.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              className="flex gap-5 rounded-3xl border border-ink-line bg-ink-900/60 p-7"
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-gold-500/25 bg-gold-500/10">
                <p.icon className="h-5 w-5 text-gold-300" />
              </div>
              <div>
                <h3 className="font-display text-lg font-semibold text-ivory-50">{p.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ivory-400">{p.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
