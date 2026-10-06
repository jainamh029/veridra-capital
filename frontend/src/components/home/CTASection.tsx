import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

export function CTASection() {
  return (
    <section className="relative overflow-hidden bg-ink-900 px-6 py-32">
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-[500px] w-[900px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gold-500/10 blur-[160px]" />
      <motion.div
        initial={{ opacity: 0, y: 28 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.7 }}
        className="relative mx-auto max-w-3xl text-center"
      >
        <h2 className="font-display text-4xl font-semibold leading-tight text-ivory-50 sm:text-5xl">
          Every module is live.
          <br />
          <span className="italic text-gold-300">Go run a notice through it.</span>
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-[16px] leading-relaxed text-ivory-300">
          Open the console to submit a capital call notice, decide a pending approval, or pull
          a fund's live cash position and forecast — against the real backend, in real time.
        </p>
        <Link
          to="/console"
          className="group mt-10 inline-flex items-center gap-2 rounded-full bg-gold-500 px-8 py-4 text-sm font-semibold text-ink-950 shadow-[0_14px_40px_-10px_rgba(203,161,53,0.6)] transition-transform hover:scale-[1.03] hover:bg-gold-400"
        >
          Enter the Console
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </motion.div>
    </section>
  );
}
