import { useNewCopy } from "../newCopy";
import sourcePhoto0 from "../assets/new-photos/photo-1758525226705-3061215c7445.jpg";
import { ArrowRight, ShieldCheck, TrendingUp, CircleCheck } from "lucide-react";
import Reveal from "./Reveal";
const Collage = () => {
  const t = useNewCopy();
  return <section data-testid="collage-bento" className="py-16 sm:py-20 relative">
    <div className="max-w-7xl mx-auto px-5 sm:px-8">
      <div className="grid grid-cols-12 gap-4 sm:gap-5">
        <Reveal className="col-span-12 md:col-span-5 md:row-span-2">
          <div className="relative h-72 md:h-full md:min-h-[480px] rounded-[2rem] overflow-hidden">
            <img src={sourcePhoto0} alt={t("Two friends laughing while checking funds on a phone")} loading="lazy" className="w-full h-full object-cover duotone" />
            <div className="absolute inset-0 bg-gradient-to-tr from-espresso/35 via-transparent to-transparent mix-blend-overlay" />
            <div className="absolute inset-0 bg-gradient-to-t from-espresso/55 via-transparent to-transparent" />
            <p className="absolute bottom-6 left-6 right-6 font-mono text-[10px] uppercase tracking-[0.12em] text-cream/90">{t("The person at the end of the payment chain")}</p>
          </div>
        </Reveal>

        <Reveal delay={0.08} className="col-span-12 sm:col-span-6 md:col-span-4">
          <div className="relative h-full overflow-hidden rounded-[2rem] bg-espresso p-7 sm:p-8 text-cream">
            <div className="w-14 h-14 rounded-full bg-gold flex items-center justify-center shadow-[0_10px_25px_-8px_rgba(124,36,52,0.6)]">
              <ShieldCheck size={24} className="text-cream" />
            </div>
            <h3 className="mt-5 font-display font-semibold text-2xl tracking-tight">{t("Every instruction tracked")}</h3>
            <p className="mt-2 text-sm leading-relaxed text-cream/70">{t("Follow payout references and recorded statuses through the partner API and portal.")}</p>
          </div>
        </Reveal>

        <Reveal delay={0.16} className="col-span-12 sm:col-span-6 md:col-span-3">
          <div className="relative h-full overflow-hidden rounded-[2rem] bg-gold p-7 sm:p-8 flex flex-col justify-between gap-6">
            <h3 className="font-display font-semibold text-2xl sm:text-3xl tracking-tight text-cream leading-tight">{t("Deliver with Hubaal")}</h3>
            <a href="#partner-form" data-testid="collage-join-btn" className="inline-flex items-center justify-center gap-2 bg-cream text-ink-light font-semibold text-sm px-6 py-3 rounded-full hover:gap-3.5 transition-all duration-300 w-fit">{t("Discuss a partnership")}<ArrowRight size={15} strokeWidth={2.5} />
            </a>
          </div>
        </Reveal>

        <Reveal delay={0.1} className="col-span-6 md:col-span-4">
          <div className="h-full rounded-[2rem] bg-elevated border border-espresso/10 p-7 sm:p-8 flex flex-col justify-center">
            <p className="font-display font-semibold text-4xl sm:text-5xl text-gold tracking-tight">{t("API")}</p>
            <p className="mt-2 text-sm text-ink-dim">{t("Payout instructions, references and status updates.")}</p>
          </div>
        </Reveal>

        <Reveal delay={0.18} className="col-span-6 md:col-span-3">
          <div className="h-full rounded-[2rem] bg-elevated border border-espresso/10 p-7 sm:p-8 flex flex-col justify-center">
            <p className="font-display font-semibold text-4xl sm:text-5xl text-gold tracking-tight">{t("Direct")}</p>
            <p className="mt-2 text-sm text-ink-dim">{t("The payout team handles delivery queries and partner support.")}</p>
          </div>
        </Reveal>

        <Reveal delay={0.12} className="col-span-12">
          <div className="border-y border-espresso/15 py-6 px-2 flex flex-col sm:flex-row items-center justify-between gap-6">
            <a href="#partner-form" className="group inline-flex items-center gap-3 font-display font-semibold text-xl sm:text-2xl text-ink-light hover:text-gold transition-colors duration-300">
              <span className="w-9 h-9 rounded-lg bg-gold/10 border border-gold/25 flex items-center justify-center">
                <TrendingUp size={16} className="text-gold" />
              </span>{t("Partner with Hubaal")}<ArrowRight size={18} className="transition-transform duration-300 group-hover:translate-x-1.5" />
            </a>
            <div className="flex items-center gap-3">
              <CircleCheck size={18} className="text-gold" />
              <span className="font-display font-semibold text-lg text-ink-light">{t("Status returned on every payout instruction")}</span>
            </div>
          </div>
        </Reveal>
      </div>
    </div>
  </section>;
};
export default Collage;
