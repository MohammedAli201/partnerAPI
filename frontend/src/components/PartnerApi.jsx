import { Check, ArrowRight } from "lucide-react";
import Reveal from "./Reveal";

const POINTS = [
  "Submit payout instructions.",
  "Keep your transaction references attached.",
  "Receive payout status updates.",
];

const InstructionVisual = () => (
  <div className="max-w-[460px] mx-auto rounded-[24px] bg-[#1B2636] ring-1 ring-white/15 p-6 sm:p-8 shadow-[0_24px_60px_-24px_rgba(0,0,0,0.5)]" data-testid="api-example">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/15 pb-5">
      <p className="text-lg font-bold text-white">Example payout instruction</p>
      <span className="text-xs text-brass rounded-full border border-brass/40 px-3 py-1">Illustrative data</span>
    </div>
    <dl className="mt-6 space-y-5">
      <div><dt className="text-xs text-white/60">Partner reference</dt><dd className="mt-1 font-mono text-sm text-white">HB-EXAMPLE-001</dd></div>
      <div><dt className="text-xs text-white/60">Recipient amount</dt><dd className="mt-1 text-3xl font-extrabold text-white">USD 100.00</dd></div>
      <div><dt className="text-xs text-white/60">Payout channel</dt><dd className="mt-1 text-base text-white">EVC Plus</dd></div>
    </dl>
    <div className="mt-7 pt-5 border-t border-white/15 flex items-center gap-3">
      <span className="w-2 h-2 bg-brass rounded-full" aria-hidden="true" />
      <p className="text-sm text-white/80"><span className="sr-only">Status: </span>Instruction accepted. Payout pending.</p>
    </div>
  </div>
);

const PartnerApi = () => (
  <section id="api" data-testid="partner-api" className="relative py-16 sm:py-24 lg:py-28 bg-espresso overflow-hidden">
    <div aria-hidden="true" className="absolute inset-0 pointer-events-none" style={{ backgroundImage: "radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px)", backgroundSize: "26px 26px" }} />
    <div className="relative max-w-[1200px] mx-auto px-5 sm:px-8 grid lg:grid-cols-12 gap-14 lg:gap-16 items-center">
      <div className="lg:col-span-5 order-2 lg:order-1"><Reveal><InstructionVisual /></Reveal></div>
      <div className="lg:col-span-7 order-1 lg:order-2">
        <Reveal>
          <p className="inline-block text-sm font-bold text-brass border-b-2 border-brass/60 pb-1">Partner integration</p>
          <h2 className="mt-5 font-extrabold uppercase tracking-[-0.01em] leading-[1.05] text-[2rem] sm:text-[2.75rem] lg:text-[3.25rem] text-white max-w-xl">Connect your system to Hubaal.</h2>
          <p className="mt-6 text-base sm:text-lg leading-[1.65] text-white/70 max-w-xl">Submit payout instructions through our API and receive payout outcomes in your system.</p>
          <ul className="mt-7 space-y-3.5">
            {POINTS.map(point => <li key={point} className="flex items-center gap-3.5 text-[15px] sm:text-base text-white/85">
              <span className="w-5 h-5 rounded-full bg-brass flex items-center justify-center shrink-0"><Check size={11} className="text-espresso" strokeWidth={3.5} aria-hidden="true" /></span>
              {point}
            </li>)}
          </ul>
          <a href="/partners/integration" data-testid="api-cta" className="group mt-9 inline-flex items-center gap-2.5 bg-gold text-white font-semibold text-base px-7 py-3.5 rounded-full ring-1 ring-white/25 hover:bg-gold-glow transition-colors duration-300">
            View integration guide <ArrowRight size={17} strokeWidth={2.5} className="transition-transform duration-300 group-hover:translate-x-1" aria-hidden="true" />
          </a>
        </Reveal>
      </div>
    </div>
  </section>
);

export default PartnerApi;
