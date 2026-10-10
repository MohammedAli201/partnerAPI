import { useNewCopy } from "../newCopy";
import sourcePhoto0 from "../assets/new-photos/photo-1571867424488-4565932edb41.jpg";
import sourcePhoto1 from "../assets/new-photos/photo-1450101499163-c8848c66ca85.jpg";
import sourcePhoto2 from "../assets/new-photos/photo-1518458028785-8fbcd101ebb9.jpg";
import { ArrowUpRight } from "lucide-react";
import Reveal from "./Reveal";
const SERVICES = [{
  id: "service-card-remittance",
  title: "Wallet Payout",
  desc: "Deliver USD to EVC Plus, ZAAD and eDahab wallets. Hubaal processes the payout and returns its outcome to your platform.",
  img: sourcePhoto0,
  alt: "A phone used for digital payments"
}, {
  id: "service-card-cash-delivery",
  title: "Bank Account Payout",
  desc: "Deliver USD to recipient accounts at Salaam Bank and Premier Bank. Track each instruction with its transaction reference.",
  img: sourcePhoto1,
  alt: "Bank settlement paperwork"
}, {
  id: "service-card-fx-updates",
  title: "Partner reporting",
  desc: "Review payout statuses, delivery outcomes and transaction references in your partner records. Hubaal reports each outcome to your platform.",
  img: sourcePhoto2,
  alt: "Cash prepared for pickup"
}];
const Services = () => {
  const t = useNewCopy();
  return <section id="services" className="py-20 sm:py-28">
    <div className="max-w-7xl mx-auto px-5 sm:px-8">
      <div className="grid lg:grid-cols-2 gap-8 items-end mb-14">
        <Reveal>
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-gold mb-5">{t("What we deliver")}</p>
          <h2 className="font-display font-semibold tracking-tight leading-[1.1] text-3xl sm:text-4xl lg:text-5xl text-ink-light">{t("USD payouts to recipients in Somalia")}</h2>
        </Reveal>
        <Reveal delay={0.1}>
          <p className="text-base sm:text-lg leading-relaxed text-ink-dim max-w-md lg:ml-auto">{t("Hubaal delivers USD through Somali mobile wallets and bank accounts. We confirm payout outcomes and report them to the originating partner.")}</p>
        </Reveal>
      </div>

      <div data-testid="services-grid" className="grid md:grid-cols-3 gap-5">
        {SERVICES.map((s, i) => <Reveal key={s.id} delay={i * 0.1} className="h-full">
            <a href="#partner-form" data-testid={s.id} className="group flex flex-col h-full rounded-3xl overflow-hidden bg-elevated border border-espresso/10 hover:border-gold/40 transition-colors duration-500">
              <div className="relative h-56 overflow-hidden">
                <img src={s.img} alt={t(s.alt)} loading="lazy" className="w-full h-full object-cover duotone group-hover:scale-105 transition-transform duration-700" />
                <div className="absolute inset-0 bg-gradient-to-tr from-espresso/60 via-transparent to-gold/20 mix-blend-overlay" />
                <div className="absolute inset-0 bg-gradient-to-t from-elevated via-transparent to-transparent" />
              </div>
              <div className="flex flex-col flex-1 p-7">
                <h3 className="font-display font-semibold text-xl sm:text-2xl text-ink-light tracking-tight">
                  {t(s.title)}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-ink-dim flex-1">{t(s.desc)}</p>
                <span className="mt-6 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-gold">{t("Discuss")}<ArrowUpRight size={14} className="transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </span>
              </div>
            </a>
          </Reveal>)}
      </div>
    </div>
  </section>;
};
export default Services;
