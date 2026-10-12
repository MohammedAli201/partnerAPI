import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { PayoutDiagram } from "./PayoutDiagram";
import { scrollToId } from "@/hooks/useLenis";
import { ease } from "@/lib/motion";

const LINES = ["Your Somalia", "payout partner."];

const RevealLine = ({ children, i }) => (
  <span className="block overflow-hidden pb-[0.08em]">
    <motion.span className="block" initial={{ y: "110%" }} animate={{ y: 0 }} transition={{ duration: 1, ease, delay: 0.25 + i * 0.12 }}>
      {children}
    </motion.span>
  </span>
);

export const Hero = () => {
  const go = (href) => (e) => {
    e.preventDefault();
    scrollToId(href);
  };

  return (
    <section id="hero" data-dark data-testid="hero-section" className="relative overflow-hidden pt-[72px]">
      <div className="container-x relative grid grid-cols-1 items-center gap-14 py-14 lg:grid-cols-12 lg:gap-12 lg:py-16">
        <div className="lg:col-span-6">
          <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease, delay: 0.15 }} className="eyebrow" data-testid="hero-eyebrow">
            Based in Mogadishu
          </motion.p>

          <h1 data-testid="hero-headline" className="h-display mt-7 text-[44px] leading-[1.02] sm:text-[58px] lg:text-[60px] xl:text-[68px]">
            {LINES.map((l, i) => (
              <RevealLine key={l} i={i}>
                {i === 0 ? <>Your <span className="hero-heading-accent">Somalia</span></> : l}
              </RevealLine>
            ))}
          </h1>

          <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, ease, delay: 0.6 }} className="lead mt-7 max-w-[540px]" data-testid="hero-subtext">
            One USD payout connection for payment businesses, backed by a team in Mogadishu.
          </motion.p>

          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, ease, delay: 0.75 }} className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
            <a href="#enquiry" onClick={go("#enquiry")} data-testid="hero-primary-cta" className="btn-primary whitespace-nowrap">
              Partner with Hubaal <ArrowRight className="h-4 w-4" />
            </a>
          </motion.div>

          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1, delay: 1 }} className="mt-10 border-t border-line pt-5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-4" data-testid="hero-status-note">
            Partnership enquiries are open.
          </motion.p>
        </div>

        <motion.div initial={{ opacity: 0, y: 40, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 1.2, ease, delay: 0.45 }} className="relative lg:col-span-6">
          <PayoutDiagram />
        </motion.div>
      </div>
    </section>
  );
};
