import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { FileText, ScanText, ListChecks, BrainCircuit, GitMerge, BellRing } from "lucide-react";

const STEPS = [
  { icon: FileText, title: "Raw notice", desc: "A capital call notice arrives as plain text — any format, any sender." },
  { icon: ScanText, title: "Extraction", desc: "A fine-tuned local model pulls entity, bank, routing, amount, due date." },
  { icon: ListChecks, title: "Rules layer", desc: "ABA checksum, baseline routing / bank / name / domain compare — every check runs, none short-circuit." },
  { icon: BrainCircuit, title: "Model layer", desc: "A fine-tuned wire-fraud model gives a second, independent opinion." },
  { icon: GitMerge, title: "Reconciled decision", desc: "PASS, REVIEW, or BLOCK — severity is the maximum across every finding." },
  { icon: BellRing, title: "Approver alert", desc: "A named, specific alert opens a tracked approval — never a silent pass." },
];

export function PipelineFlow() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.75", "end 0.4"] });
  const lineScale = useTransform(scrollYProgress, [0, 1], [0, 1]);

  return (
    <section id="pipeline" className="relative bg-ink-950 px-6 py-32">
      <div className="mx-auto max-w-6xl">
        <div className="mb-20 max-w-2xl">
          <span className="text-xs font-bold uppercase tracking-[0.2em] text-gold-400">How it works</span>
          <h2 className="mt-4 font-display text-4xl font-semibold leading-tight text-ivory-50 sm:text-5xl">
            One notice in.
            <br />
            <span className="italic text-gold-300">One decision out.</span>
          </h2>
        </div>

        <div ref={ref} className="relative">
          <div className="absolute left-6 top-6 hidden h-[calc(100%-3rem)] w-px bg-ink-line md:block" />
          <motion.div
            style={{ scaleY: lineScale }}
            className="absolute left-6 top-6 hidden h-[calc(100%-3rem)] w-px origin-top bg-gradient-to-b from-gold-400 to-gold-500/10 md:block"
          />

          <div className="space-y-10">
            {STEPS.map((step, i) => (
              <motion.div
                key={step.title}
                initial={{ opacity: 0, x: -24 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: "-120px" }}
                transition={{ duration: 0.6, delay: i * 0.05 }}
                className="relative flex items-start gap-6 md:pl-0"
              >
                <div className="relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-gold-500/40 bg-ink-900 text-gold-300 shadow-[0_0_0_6px_rgba(10,13,20,1)]">
                  <step.icon className="h-5 w-5" />
                </div>
                <div className="flex-1 rounded-2xl border border-ink-line bg-ink-900/60 px-6 py-5 md:flex md:items-center md:justify-between md:gap-8">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs text-gold-500">{String(i + 1).padStart(2, "0")}</span>
                      <h3 className="font-display text-lg font-semibold text-ivory-50">{step.title}</h3>
                    </div>
                    <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-ivory-400">{step.desc}</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
