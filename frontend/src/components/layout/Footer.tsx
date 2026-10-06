import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="border-t border-ink-line bg-ink-950 px-6 py-16">
      <div className="mx-auto max-w-6xl">
        <div className="grid gap-12 md:grid-cols-[1.3fr_1fr_1fr_1fr]">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-gold-500/30 bg-gold-500/10">
                <span className="font-display text-sm font-semibold text-gold-400">V</span>
              </span>
              <span className="font-display text-[17px] font-semibold text-ivory-50">
                Veridra <span className="text-gold-400">Capital</span>
              </span>
            </div>
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-ivory-500">
              An internal operating system for fund finance — wire-fraud verification, payment
              approvals, cash planning, forecasting, and K-1 routing, in one console.
            </p>
          </div>

          <div>
            <div className="text-[11px] font-bold uppercase tracking-widest text-ivory-500">Platform</div>
            <ul className="mt-4 space-y-2.5 text-sm text-ivory-300">
              <li><Link to="/console/verification" className="hover:text-gold-300">Fraud Verification</Link></li>
              <li><Link to="/console/approvals" className="hover:text-gold-300">Payment Approvals</Link></li>
              <li><Link to="/console/cash-planning" className="hover:text-gold-300">Cash Planning</Link></li>
              <li><Link to="/console/forecasting" className="hover:text-gold-300">Forecasting</Link></li>
              <li><Link to="/console/k1-routing" className="hover:text-gold-300">K-1 Routing</Link></li>
            </ul>
          </div>

          <div>
            <div className="text-[11px] font-bold uppercase tracking-widest text-ivory-500">Company</div>
            <ul className="mt-4 space-y-2.5 text-sm text-ivory-300">
              <li><a href="#modules" className="hover:text-gold-300">Platform overview</a></li>
              <li><a href="#pipeline" className="hover:text-gold-300">How it works</a></li>
              <li><a href="#results" className="hover:text-gold-300">Evaluation results</a></li>
              <li><a href="#trust" className="hover:text-gold-300">Architecture</a></li>
            </ul>
          </div>

          <div>
            <div className="text-[11px] font-bold uppercase tracking-widest text-ivory-500">Console</div>
            <ul className="mt-4 space-y-2.5 text-sm text-ivory-300">
              <li><Link to="/console" className="hover:text-gold-300">Overview dashboard</Link></li>
              <li><a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="hover:text-gold-300">API reference</a></li>
            </ul>
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-3 border-t border-ink-line pt-6 text-xs text-ivory-500 md:flex-row md:items-center md:justify-between">
          <p>© {new Date().getFullYear()} Veridra Capital. Internal platform demo — synthetic data only.</p>
          <p>All fund names, notices, and balances shown are synthetically generated for demonstration.</p>
        </div>
      </div>
    </footer>
  );
}
