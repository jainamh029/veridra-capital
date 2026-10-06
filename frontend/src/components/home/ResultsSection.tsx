import { motion } from "framer-motion";
import { Counter } from "./Counter";

const FRAUD_TYPES = [
  { label: "Altered routing number", rate: "3 / 3", sev: "high" },
  { label: "Wrong receiving bank", rate: "3 / 3", sev: "high" },
  { label: "Misspelled GP name", rate: "3 / 3", sev: "medium" },
  { label: "Look-alike sender domain", rate: "3 / 3", sev: "high" },
  { label: "Unverified bank change", rate: "3 / 3", sev: "high" },
  { label: "Combined domain + name attack", rate: "3 / 3", sev: "high" },
];

const SEV_STYLE: Record<string, string> = {
  high: "text-rose-300 border-rose-400/30 bg-rose-500/10",
  medium: "text-amber-300 border-amber-400/30 bg-amber-500/10",
};

export function ResultsSection() {
  return (
    <section id="results" className="relative overflow-hidden bg-ink-900 px-6 py-32">
      <div className="pointer-events-none absolute left-1/2 top-0 h-[500px] w-[900px] -translate-x-1/2 rounded-full bg-gold-500/5 blur-[160px]" />
      <div className="relative mx-auto max-w-6xl">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.6 }}
          className="mb-16 max-w-2xl"
        >
          <span className="text-xs font-bold uppercase tracking-[0.2em] text-gold-400">Evaluation</span>
          <h2 className="mt-4 font-display text-4xl font-semibold leading-tight text-ivory-50 sm:text-5xl">
            Measured against a
            <span className="italic text-gold-300"> 33-notice batch.</span>
          </h2>
          <p className="mt-5 text-[16px] leading-relaxed text-ivory-300">
            15 clean notices across 9 funds and 4 notice styles; 18 fraud notices across every
            fraud type the platform detects, including combined attacks. None were used to
            train either model.
          </p>
        </motion.div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { to: 1, decimals: 3, label: "Precision" },
            { to: 1, decimals: 3, label: "Recall" },
            { to: 1, decimals: 3, label: "F1 score" },
            { to: 0, suffix: "%", label: "False positives on clean" },
          ].map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              className="rounded-3xl border border-ink-line bg-ink-800/60 p-7"
            >
              <div className="font-display text-4xl font-semibold text-gold-300">
                <Counter to={s.to} decimals={s.decimals ?? 0} suffix={s.suffix ?? ""} />
              </div>
              <div className="mt-2 text-sm text-ivory-400">{s.label}</div>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6, delay: 0.15 }}
          className="mt-6 overflow-hidden rounded-3xl border border-ink-line bg-ink-800/60"
        >
          <div className="border-b border-ink-line px-7 py-5">
            <h3 className="font-display text-lg font-semibold text-ivory-50">Every fraud type, caught</h3>
            <p className="mt-1 text-sm text-ivory-400">Per-type detection rate and alert severity on the held-out batch.</p>
          </div>
          <div className="divide-y divide-ink-line">
            {FRAUD_TYPES.map((f) => (
              <div key={f.label} className="flex items-center justify-between px-7 py-4">
                <span className="text-sm text-ivory-200">{f.label}</span>
                <div className="flex items-center gap-3">
                  <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${SEV_STYLE[f.sev]}`}>
                    {f.sev}
                  </span>
                  <span className="w-14 text-right font-mono text-sm text-gold-300">{f.rate}</span>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
