import { useNewCopy } from "../newCopy";
import sourcePhoto0 from "../assets/new-photos/photo-1629697776275-725482b486f7.jpg";
import { motion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";
import Reveal from "./Reveal";
const WALLETS = ["EVC PLUS", "ZAAD", "eDAHAB", "BANK ACCOUNT", "CASH PICKUP"];
const AppFeature = () => {
  const t = useNewCopy();
  return <section data-testid="app-feature-container" className="py-20 sm:py-28 overflow-hidden">
    <div className="max-w-7xl mx-auto px-5 sm:px-8 grid lg:grid-cols-2 gap-14 items-center">
      <Reveal className="order-2 lg:order-1">
        <div className="relative max-w-sm mx-auto lg:mx-0">
          <div className="absolute inset-0 -m-8 rounded-full bg-gold/12 blur-[90px] pointer-events-none" />
          <div className="relative rounded-t-[9rem] rounded-b-[2.2rem] overflow-hidden border border-gold/35 shadow-[0_30px_70px_-30px_rgba(22,32,47,0.5)]">
            <img src={sourcePhoto0} alt={t("Hands holding a mobile phone")} loading="lazy" className="w-full h-[520px] object-cover duotone" />
            <div className="absolute inset-0 bg-gradient-to-tr from-espresso/70 via-transparent to-gold/20 mix-blend-overlay" />
            <div className="absolute inset-0 bg-gradient-to-t from-void/80 via-transparent to-transparent" />
            <motion.div initial={{
              opacity: 0
            }} whileInView={{
              opacity: 1
            }} viewport={{
              once: true
            }} transition={{
              delay: 0.3,
              duration: 0.7
            }} data-testid="payout-confirmation-card" className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[80%] bg-elevated/95 backdrop-blur-xl border border-espresso/10 rounded-2xl p-5 shadow-[0_18px_45px_-22px_rgba(22,32,47,0.28)]">
              <div className="flex items-center gap-2.5">
                <span className="w-8 h-8 rounded-full bg-gold flex items-center justify-center shrink-0">
                  <CheckCircle2 size={16} className="text-cream" />
                </span>
                <span className="font-display font-semibold text-lg text-ink-light">{t("Payout confirmed")}</span>
              </div>
              <p data-testid="payout-confirmation-amount" className="mt-3.5 font-display font-semibold text-3xl text-ink-light tracking-tight">
                USD 100.00
              </p>
              <div className="mt-3 space-y-1.5 text-sm">
                <div className="flex justify-between gap-3">
                  <span className="text-ink-dim">{t("Receiving channel")}</span>
                  <span className="font-medium text-ink-light">EVC Plus</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-ink-dim">{t("Status")}</span>
                  <span className="font-medium text-emerald-700">{t("Delivered")}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-ink-dim">{t("Reference")}</span>
                  <span className="font-mono text-xs text-ink-light pt-0.5">HB-EXAMPLE-001</span>
                </div>
              </div>
              <p className="mt-3.5 text-[10px] text-ink-muted">{t("Example payout confirmation · illustrative data")}</p>
            </motion.div>
          </div>
        </div>
      </Reveal>

      <Reveal delay={0.1} className="order-1 lg:order-2">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-gold mb-5">{t("The receiving experience")}</p>
        <h2 className="font-display font-semibold tracking-tight leading-[1.1] text-3xl sm:text-4xl lg:text-5xl text-ink-light max-w-lg">{t("Delivered to the wallet they already trust")}</h2>
        <p className="mt-5 text-base sm:text-lg leading-relaxed text-ink-dim max-w-lg">{t("Hubaal delivers USD to the recipient’s mobile wallet or bank account in Somalia. Your platform receives the payout outcome and transaction reference.")}</p>
        <div className="mt-8 flex flex-wrap gap-2.5">
          {WALLETS.map(w => <span key={t(w)} className="font-mono text-[10px] tracking-[0.12em] text-gold border border-gold/30 rounded-full px-4 py-2 hover:bg-gold/10 transition-colors duration-300">
              {t(w)}
            </span>)}
        </div>
        <a href="#coverage" data-testid="app-download-btn" className="mt-9 inline-flex items-center gap-2.5 bg-gold text-void font-semibold text-sm sm:text-base px-7 py-3.5 rounded-full hover:bg-gold-glow hover:gap-4 transition-all duration-300">{t("Explore payout coverage")}</a>
      </Reveal>
    </div>
  </section>;
};
export default AppFeature;
