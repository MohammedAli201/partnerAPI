import { Logo } from "./Logo";
import { scrollToId } from "@/hooks/useLenis";
import { COMPANY } from "@/content/site";

const COLS = [
  { title: "Platform", links: [["Coverage", "#coverage"], ["How it works", "#how-it-works"], ["Payout support", "#exceptions"], ["Integration", "#integration"]] },
  { title: "Partners", links: [["Why Hubaal", "#why-hubaal"], ["Safeguards", "#trust"]] },
  { title: "Company", links: [["About Hubaal", "#about"]] },
];

export const Footer = () => {
  const go = (href) => (e) => {
    e.preventDefault();
    scrollToId(href);
  };
  return (
    <footer data-dark data-testid="site-footer" className="relative border-t border-line bg-canvas pb-10 pt-16">
      <div className="container-x">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <Logo dark testId="footer-logo" />
            <p className="mt-5 max-w-[380px] text-[15px] leading-relaxed text-ink-3">Your local payout connection to Somalia.</p>
            <div data-testid="footer-status-badge" className="mt-6 inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-amber-800">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> {COMPANY.regulatoryStatus}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-10 sm:grid-cols-3 lg:col-span-7">
            {COLS.map((c) => (
              <div key={c.title}>
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-4">{c.title}</p>
                <ul className="mt-5 space-y-3">
                  {c.links.map(([l, h]) => (
                    <li key={l}>
                      <a href={h} onClick={go(h)} data-testid={`footer-link-${l.toLowerCase().replace(/[^a-z]+/g, "-")}`} className="text-[14px] text-ink-2 transition-colors hover:text-teal-700">{l}</a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-14 grid grid-cols-1 gap-6 border-t border-line pt-8 text-[13px] text-ink-4 sm:grid-cols-2">
          <div className="space-y-1">
            <p>{COMPANY.legalName} · Reg. no. {COMPANY.registrationNumber} · {COMPANY.city}</p>
            <p>
              Partnerships: <a href={`mailto:${COMPANY.email}`} data-testid="footer-email" className="text-ink-2 hover:text-teal-700">{COMPANY.email}</a> · <a href={`tel:${COMPANY.phone.replace(/\s+/g, "")}`} data-testid="footer-phone" className="text-ink-2 hover:text-teal-700">{COMPANY.phone}</a>
            </p>
          </div>
          <p className="sm:text-right">© {new Date().getFullYear()} {COMPANY.legalName}. All rights reserved.</p>
        </div>
        <p className="mt-8 max-w-[760px] font-mono text-[11px] leading-relaxed text-ink-4/80" data-testid="footer-disclaimer">
          {COMPANY.regulatoryDetail}
        </p>
      </div>
    </footer>
  );
};
