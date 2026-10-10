import { useState } from "react";
import { Check, Smartphone, Landmark, HandCoins } from "lucide-react";
import Reveal from "./Reveal";
import SectionHeader from "./SectionHeader";

import { payoutChannels } from "../channels";
const CHANNELS = payoutChannels;

const FILTERS = ["All", "Mobile wallets", "Banks", "Cash pickup"];

const TIMELINE = [
  {
    time: "10:02",
    title: "Instruction received",
    reference: "HB-774198",
    desc: "accepted from the partner system.",
    tone: "bg-espresso",
  },
  {
    time: "10:05",
    title: "Out for delivery",
    desc: "EVC Plus payout initiated — Mogadishu.",
    tone: "bg-gold",
  },
  {
    time: "10:07",
    title: "Outcome returned",
    desc: "USD 250.00 delivered · confirmation sent.",
    tone: "bg-emerald-600",
  },
];

const Partners = () => {
  const [filter, setFilter] = useState("All");
  const rows = CHANNELS.filter((c) =>
    filter === "All"
      ? true
      : filter === "Banks"
      ? c.type === "Bank"
      : filter === "Cash pickup"
      ? c.type === "Cash pickup"
      : c.type === "Mobile wallet"
  );

  return (
    <section id="coverage" className="py-16 sm:py-24 bg-void">
    <div className="max-w-[1200px] mx-auto px-5 sm:px-8">
      <SectionHeader
        testid="coverage-header"
        eyebrow="Coverage"
        title="Where funds are delivered"
        copy="Hubaal delivers recipient payouts in USD through Somali mobile wallets, bank accounts and cash pickup."
        copyTestid="usd-payout-policy"
        linkLabel="Start a partnership"
        linkHref="#partner-form"
      />

      <div className="grid lg:grid-cols-12 gap-12 items-center">
        <div className="lg:col-span-7" data-testid="partners-wall-grid">
          <Reveal>
            <div className="flex flex-wrap gap-2 mb-5" data-testid="coverage-filters">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  data-testid={`coverage-filter-${f.toLowerCase().replace(" ", "-")}`}
                  onClick={() => setFilter(f)}
                  aria-pressed={filter === f}
                  className={`px-5 py-2.5 rounded-full text-sm font-semibold transition-colors duration-300 ${
                    filter === f
                      ? "bg-espresso text-white"
                      : "bg-white border border-line text-ink-dim hover:text-ink-light"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
            <div data-testid="coverage-cells" className="grid grid-cols-2 gap-4">
              {rows.map((r, i) => (
                <Reveal key={`${filter}-${r.name}`} delay={i * 0.04}>
                  <div
                    data-testid="coverage-cell"
                    className="bg-white rounded-2xl border border-line p-5 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_12px_32px_-16px_rgba(22,32,47,0.12)]"
                  >
                    <div className="flex items-center justify-between">
                      <span className="w-9 h-9 rounded-full bg-mist flex items-center justify-center">
                        {r.type === "Bank" ? <Landmark size={15} className="text-gold" /> : r.type === "Cash pickup" ? <HandCoins size={15} className="text-gold" /> : <Smartphone size={15} className="text-gold" />}
                      </span>
                      <span className="flex items-center gap-1.5 text-[11px] font-bold text-emerald-700 bg-emerald-50 rounded-full px-2.5 py-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> USD
                      </span>
                    </div>
                    <p className="mt-4 text-base font-bold text-ink-light">{r.name}</p>
                    <p className="text-xs text-ink-dim mt-0.5">{r.type}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </Reveal>
        </div>

      <div className="lg:col-span-5">
        <Reveal delay={0.15}>
          <div
            data-testid="delivery-timeline"
            className="max-w-[360px] mx-auto bg-white rounded-3xl border border-line p-7 sm:p-8 shadow-[0_4px_20px_rgba(22,32,47,0.04)]"
          >
            <div className="flex items-center justify-between">
              <p className="text-[15px] font-semibold text-ink-light">Delivery outcome</p>
              <span className="text-xs font-medium text-ink-dim border border-line rounded-full px-3 py-1">
                Illustrative
              </span>
            </div>
            <ol className="mt-7 relative">
              <span
                className="absolute left-[15px] top-3 bottom-7 w-px bg-line"
                aria-hidden="true"
              />
              {TIMELINE.map((t, i) => (
                <li key={t.title} className={`relative flex gap-4 pb-7 ${i === TIMELINE.length - 1 ? "pb-0" : ""}`}>
                  <span
                    className={`relative z-10 w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${t.tone}`}
                  >
                    {t.tone === "bg-emerald-600" ? (
                      <Check size={14} className="text-white" strokeWidth={3} />
                    ) : (
                      <span className="w-2 h-2 rounded-full bg-white/90" />
                    )}
                  </span>
                  <div>
                    <p className="text-sm font-bold text-ink-light">
                      {t.title}
                      <span className="font-mono text-[11px] text-ink-muted ml-2">{t.time}</span>
                    </p>
                    <p className="mt-1 text-sm leading-[1.55] text-ink-dim">
                      {t.reference && <><span className="font-mono">{t.reference}</span>{" "}</>}{t.desc}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-6 pt-5 border-t border-line text-xs leading-[1.6] text-ink-dim">
              Your transaction reference stays attached and the payout status returns to your system. Timings are illustrative.
            </p>
          </div>
        </Reveal>
      </div>
      </div>
    </div>
  </section>
  );
};

export default Partners;
