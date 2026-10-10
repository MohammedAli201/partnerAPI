export const Logo = ({ compact = false, dark = false }) => (
  <a href="/#top" aria-label="Hubaal home" data-testid="nav-logo" className="flex items-center gap-2.5 group">
    <svg aria-hidden="true" width="34" height="34" viewBox="0 0 64 64" className="shrink-0">
      <path d="M32 7l21.65 12.5v25L32 57 10.35 44.5v-25z" fill="none" stroke={dark ? "#C9A45C" : "#7C2434"} strokeWidth="4" strokeLinejoin="round" className="transition-all duration-500 group-hover:stroke-gold-glow" />
      <path d="M32 21c5.2 6.2 8.2 9.9 8.2 14.2a8.2 8.2 0 1 1-16.4 0C23.8 30.9 26.8 27.2 32 21z" fill={dark ? "#C9A45C" : "#7C2434"} />
    </svg>
    {!compact && (
      <span className="leading-none flex flex-col">
        <span className={`font-display font-semibold text-lg tracking-wide ${dark ? "text-cream" : "text-ink-light"}`}>HUBAAL</span>
        <span className={`text-[9px] tracking-[0.14em] ${dark ? "text-brass" : "text-gold"}`}>PAYOUT PARTNER</span>
      </span>
    )}
  </a>
);

export default Logo;
