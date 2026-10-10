import { useNewCopy } from "../newCopy";
import { Zap, Percent, ShieldCheck, Headphones } from "lucide-react";
import Reveal from "./Reveal";
const CELLS = [{
  id: "bento-fast-transfer",
  icon: Zap,
  title: "Local payout processing",
  desc: "Hubaal processes payout instructions and tracks local delivery to the recipient’s wallet or bank account.",
  span: "md:col-span-8",
  big: true
}, {
  id: "bento-low-cost",
  icon: Percent,
  title: "Clear payout records",
  desc: "Transaction references and payout records give your team a clear view of each instruction.",
  span: "md:col-span-4"
}, {
  id: "bento-trusted-service",
  icon: ShieldCheck,
  title: "Confirmed outcomes",
  desc: "Recorded statuses and references keep delivery outcomes visible, including instructions that need manual review.",
  span: "md:col-span-4"
}, {
  id: "bento-support",
  icon: Headphones,
  title: "Partner support desk",
  desc: "Speak with the team handling local delivery, transaction queries and partner support.",
  span: "md:col-span-8",
  big: true
}];
const Bento = () => {
  const t = useNewCopy();
  return <section id="why-us" className="py-20 sm:py-28 bg-surface border-y border-espresso/10">
    <div className="max-w-7xl mx-auto px-5 sm:px-8">
      <Reveal className="mb-14">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-gold mb-5">{t("Why remittance companies choose Hubaal")}</p>
        <h2 className="font-display font-semibold tracking-tight leading-[1.1] text-3xl sm:text-4xl lg:text-5xl text-ink-light">{t("Process, track and confirm each payout")}</h2>
      </Reveal>

      <div data-testid="why-us-bento-grid" className="grid md:grid-cols-12 gap-5">
        {CELLS.map((c, i) => <Reveal key={c.id} delay={i * 0.07} className={`col-span-1 ${c.span} h-full`}>
            <div className="group relative h-full rounded-3xl bg-elevated border border-espresso/10 hover:border-gold/45 p-8 sm:p-10 transition-all duration-500 hover:-translate-y-1 overflow-hidden">
              <div className="absolute -top-16 -right-16 w-48 h-48 rounded-full bg-gold/8 blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
              <c.icon size={30} strokeWidth={1.6} className="text-gold" />
              <h3 className="mt-6 font-display font-semibold text-2xl text-ink-light tracking-tight">
                {t(c.title)}
              </h3>
              <p className={`mt-3 leading-relaxed text-ink-dim ${c.big ? "max-w-md" : ""} text-sm sm:text-base`}>
                {t(c.desc)}
              </p>
            </div>
          </Reveal>)}
      </div>
    </div>
  </section>;
};
export default Bento;
