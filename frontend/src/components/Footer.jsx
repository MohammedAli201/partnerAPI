import { Mail, MapPin } from "lucide-react";
import Logo from "./Logo";
import { useBusiness } from "../business";

const COLS = [
  {
    title: "Partnerships",
    links: [
      { label: "Payout channels", href: "/#channels" },
      { label: "Why Hubaal", href: "/#why-hubaal" },
      { label: "Partner onboarding", href: "/#how-it-works" },
      { label: "Partner integration", href: "/#api" },
      { label: "About Hubaal", href: "/#about" },
      { label: "Partner questions", href: "/#faq" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Discuss a partnership", href: "/#partner-form" },
      { label: "Partner sign in", href: "/login" },
      { label: "Privacy Policy", href: "/privacy" },
      { label: "Terms of Service", href: "/terms" },
    ],
  },
];

const Footer = () => {
  const { brand, contact, licensing_disclosure, preview } = useBusiness();
  return (
    <footer data-testid="main-footer" className="bg-espresso text-white py-12 sm:py-16">
      <div className="max-w-[1200px] mx-auto px-5 sm:px-8">
        <div className="grid md:grid-cols-12 gap-10">
          <div className="md:col-span-6">
            <Logo dark />
            {preview && <div data-testid="approval-notice" className="mt-6 max-w-sm border-l-2 border-brass pl-4">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-brass">Service status</p>
              <p className="mt-2 text-[15px] leading-[1.65] text-white/85">{licensing_disclosure}</p>
            </div>}
            <div className="mt-7 space-y-3">
              <a href={`mailto:${contact.email}`} className="flex items-center gap-3 text-[15px] text-white/80 hover:text-white">
                <Mail size={15} className="text-brass shrink-0" aria-hidden="true" /> {contact.email}
              </a>
              <p className="flex items-center gap-3 text-[15px] text-white/80">
                <MapPin size={15} className="text-brass shrink-0" aria-hidden="true" /> {contact.address}
              </p>
            </div>
          </div>
          {COLS.map(column => (
            <div key={column.title} className="md:col-span-3">
              <p className="text-[13px] font-semibold text-white mb-5">{column.title}</p>
              <ul className="space-y-3">
                {column.links.map(link => <li key={link.label}>
                  <a href={link.href} className="text-[15px] text-white/70 hover:text-white transition-colors duration-300">{link.label}</a>
                </li>)}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-12 pt-7 border-t border-white/15 text-[13px] text-white/60">
          © {new Date().getFullYear()} {brand}. All rights reserved.
        </p>
      </div>
    </footer>
  );
};

export default Footer;
