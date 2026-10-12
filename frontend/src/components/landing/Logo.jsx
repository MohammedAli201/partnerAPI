import { MARKETING_COLORS as brand } from "@/marketing-colors";
export const LogoMark = ({ size = 32, dark = false, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className={className} aria-hidden>
    <rect width="32" height="32" rx="8" fill={dark ? brand.ivory : brand.indigo} />
    <rect x="7" y="7" width="4.5" height="18" rx="2.25" fill={dark ? brand.indigo : brand.ivory} />
    <rect x="20.5" y="7" width="4.5" height="18" rx="2.25" fill={brand.apricot} />
    <path d="M11.5 12.5 C 15 12.5, 17 19.5, 20.5 19.5" stroke={dark ? brand.indigo : brand.ivory} strokeWidth="2.4" strokeLinecap="round" />
    <circle cx="16" cy="16" r="2.2" fill={dark ? brand.indigo : brand.ivory} />
  </svg>
);

export const Logo = ({ dark = false, testId = "brand-logo" }) => (
  <a href="#hero" data-testid={testId} className="group inline-flex items-center gap-2.5">
    <LogoMark dark={dark} className="transition-transform duration-500 group-hover:rotate-[-6deg]" />
    <span className={`whitespace-nowrap font-semibold tracking-[-0.02em] ${dark ? "text-white" : "text-ink"}`}>
      Hubaal <span className={dark ? "text-slate-400" : "text-ink-4"}>Express</span>
    </span>
  </a>
);
