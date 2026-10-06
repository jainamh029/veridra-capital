import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "#modules", label: "Platform" },
  { href: "#pipeline", label: "How it works" },
  { href: "#results", label: "Results" },
  { href: "#trust", label: "Architecture" },
];

export function MarketingNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.header
      initial={{ y: -80, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      className="fixed inset-x-0 top-0 z-50"
    >
      <div
        className={cn(
          "mx-auto mt-4 flex max-w-6xl items-center justify-between rounded-2xl border px-5 py-3 transition-all duration-300",
          scrolled
            ? "border-ink-line bg-ink-900/80 backdrop-blur-xl shadow-[0_20px_60px_-30px_rgba(0,0,0,0.8)]"
            : "border-transparent bg-transparent",
        )}
      >
        <Link to="/" className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-gold-500/30 bg-gold-500/10">
            <span className="font-display text-sm font-semibold text-gold-400">V</span>
          </span>
          <span className="font-display text-[17px] font-semibold tracking-tight text-ivory-50">
            Veridra <span className="text-gold-400">Capital</span>
          </span>
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="text-[13px] font-medium text-ivory-300 transition-colors hover:text-gold-300"
            >
              {l.label}
            </a>
          ))}
        </nav>

        <Link
          to="/console"
          className="rounded-full bg-gold-500 px-5 py-2 text-[13px] font-semibold text-ink-950 shadow-[0_8px_24px_-6px_rgba(203,161,53,0.6)] transition-transform hover:scale-[1.03] hover:bg-gold-400"
        >
          Enter Console
        </Link>
      </div>
    </motion.header>
  );
}
