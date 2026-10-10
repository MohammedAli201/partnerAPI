import Reveal from "./Reveal";

const FLOW = [
  { num: "01", title: "Your business", sub: "Submit payout instructions", accent: false },
  { num: "02", title: "Hubaal", sub: "Deliver the local payout", accent: true },
  { num: "03", title: "Your recipient", sub: "Receive USD by wallet, bank or cash pickup", accent: false },
];

const PayoutModel = () => (
  <section data-testid="payout-model" className="py-16 sm:py-24 bg-surface">
    <div className="max-w-[1200px] mx-auto px-5 sm:px-8">
      <Reveal>
        <div className="relative bg-espresso rounded-[2.5rem] px-6 sm:px-12 lg:px-16 py-16 sm:py-20 overflow-hidden text-center">
          <div
            aria-hidden="true"
            className="absolute inset-0 pointer-events-none"
            style={{
              backgroundImage: "radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px)",
              backgroundSize: "26px 26px",
            }}
          />
          <div className="relative">
            <p
              data-testid="model-label"
              className="font-mono text-[11px] sm:text-xs tracking-[0.2em] uppercase mb-8"
            >
              <span className="inline-block w-2 h-2 rounded-full bg-brass mr-3 align-middle" />
              <span className="text-white font-bold">Somalia payout partner</span>
              <span className="text-white/40"> / USD payouts</span>
            </p>

            <h2
              data-testid="model-title"
              className="font-extrabold tracking-[-0.02em] leading-[1.1] text-[2rem] sm:text-[2.75rem] lg:text-[3.25rem] text-white max-w-3xl mx-auto"
            >
              The local payout layer behind your remittance business
            </h2>

            <p className="mt-5 max-w-xl mx-auto text-base sm:text-lg leading-[1.65] text-white/70">
              The delivery layer that lets{" "}
              <span className="text-white font-semibold border-b-2 border-brass pb-0.5">
                your business
              </span>{" "}
              pay recipients across Somalia.
            </p>

            <div
              data-testid="model-flow"
              className="mt-12 flex flex-col items-stretch justify-center max-w-3xl mx-auto sm:flex-row sm:items-center"
            >
              {FLOW.map((c, i) => (
                <div key={c.num} className="contents sm:flex sm:items-center sm:flex-1">
                  <div
                    data-testid={`model-flow-card-${i + 1}`}
                    className={`flex-1 rounded-2xl p-6 text-left ${
                      c.accent
                        ? "bg-gold text-white shadow-[0_24px_50px_-16px_rgba(124,36,52,0.55)] sm:scale-[1.05]"
                        : "bg-white/5 text-white ring-1 ring-white/10"
                    }`}
                  >
                    <p className={`font-mono text-xs ${c.accent ? "text-white/70" : "text-brass"}`}>
                      {c.num}
                    </p>
                    <p className="mt-3 text-lg font-bold">{c.title}</p>
                    <p className={`mt-1.5 text-sm leading-[1.5] ${c.accent ? "text-white/80" : "text-white/60"}`}>
                      {c.sub}
                    </p>
                  </div>
                  {i < FLOW.length - 1 && (
                    <div className="flex justify-center py-1 sm:py-0 sm:px-3" aria-hidden="true">
                      <span className="h-6 border-l-2 border-dashed border-brass/60 sm:h-0 sm:w-8 sm:border-l-0 sm:border-t-2" />
                    </div>
                  )}
                </div>
              ))}
            </div>

            <p className="mt-8 text-sm sm:text-[15px] text-white/60">
              Payout status and confirmation returned to your system.
            </p>
          </div>
        </div>
      </Reveal>
    </div>
  </section>
);

export default PayoutModel;
