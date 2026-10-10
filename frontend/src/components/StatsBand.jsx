const ITEMS = [
  "USD payouts",
  "Mobile wallets",
  "Bank accounts",
  "Cash pickup",
  "Based in Mogadishu",
];

const StatsBand = () => (
  <section data-testid="stats-band" aria-label="Partner service overview" className="bg-gold py-3 overflow-hidden font-sans">
    <div className="stats-marquee-track flex w-max animate-marquee will-change-transform hover:[animation-play-state:paused]">
      {[0, 1].map((copy) => (
        <div key={copy} aria-hidden={copy === 1} className="stats-marquee-set flex items-center shrink-0">
          {ITEMS.map(label => (
            <span key={label} className="stats-marquee-item flex items-center px-6 sm:px-8">
              <span className="text-sm sm:text-[15px] leading-[18px] sm:leading-5 font-semibold text-cream whitespace-nowrap">
                {label}
              </span>
              <span className="ml-5 sm:ml-6 text-xs leading-[18px] sm:leading-5 text-white/50" aria-hidden="true">·</span>
            </span>
          ))}
        </div>
      ))}
    </div>
  </section>
);

export default StatsBand;
