import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X, ArrowRight } from "lucide-react";
import Logo from "./Logo";
import { useLocation } from "react-router-dom";

const LINKS = [
  { label: "Payout channels", href: "#channels" },
  { label: "Why Hubaal", href: "#why-hubaal" },
  { label: "Partner onboarding", href: "#how-it-works" },
  { label: "About Hubaal", href: "#about" },
];

export const Nav = () => {
  const { pathname } = useLocation();
  const homeHref = (hash) => pathname === "/" ? hash : `/${hash}`;
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const onDark = (pathname === "/" && !scrolled) || open;

  useEffect(() => {
    if (!open) return;
    const toggle = document.querySelector('[data-testid="nav-mobile-menu-toggle"]');
    const main = document.querySelector('main'), footer = document.querySelector('footer');
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    if (main) main.inert = true;
    if (footer) footer.inert = true;
    window.__lenis?.stop();
    const key = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); setOpen(false); return; }
      if (event.key !== 'Tab') return;
      const items = [toggle, ...document.querySelectorAll('[data-testid="mobile-menu-panel"] a')].filter(Boolean);
      event.preventDefault();
      const current = items.indexOf(document.activeElement);
      items[(current + (event.shiftKey ? -1 : 1) + items.length) % items.length]?.focus();
    };
    const desktop = window.matchMedia('(min-width: 1024px)');
    const closeOnDesktop = () => { if (desktop.matches) setOpen(false); };
    desktop.addEventListener('change', closeOnDesktop);
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('keydown', key);
      desktop.removeEventListener('change', closeOnDesktop);
      document.body.style.overflow = overflow;
      if (main) main.inert = false;
      if (footer) footer.inert = false;
      window.__lenis?.start();
      toggle?.focus();
    };
  }, [open]);

  return (
    <>
      <header
        data-testid="nav-header"
        className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${
          scrolled && !open
            ? "bg-white/90 backdrop-blur-lg border-b border-line"
            : "bg-transparent border-b border-transparent"
        }`}
      >
        <div className="max-w-[1200px] mx-auto px-5 sm:px-8 h-[72px] flex items-center justify-between">
          <Logo dark={onDark} />
          <nav aria-label="Main navigation" className="hidden lg:flex items-center gap-8">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={homeHref(l.href)}
                className={`text-[15px] font-medium transition-colors duration-300 ${
                  onDark ? "text-white/80 hover:text-white" : "text-ink-dim hover:text-gold"
                }`}
              >
                {l.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <a
              href={homeHref("#partner-form")}
              data-testid="nav-transact-btn"
              className={`hidden sm:inline-flex items-center gap-2 bg-gold text-white font-semibold text-[15px] px-5 py-2.5 rounded-full transition-colors duration-300 ${
                onDark ? "ring-1 ring-white/25 hover:bg-gold-glow" : "hover:bg-gold-dark"
              }`}
            >
              Discuss a partnership <ArrowRight size={15} strokeWidth={2.5} />
            </a>
            <button
              data-testid="nav-mobile-menu-toggle"
              onClick={() => setOpen(!open)}
              className={`lg:hidden p-2 ${onDark ? "text-white" : "text-ink-light"}`}
              aria-label={open ? "Close menu" : "Menu"}
              aria-expanded={open}
              aria-controls={open ? "mobile-navigation" : undefined}
            >
              {open ? <X size={22} /> : <Menu size={22} />}
            </button>
          </div>
        </div>
      </header>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            id="mobile-navigation" data-testid="mobile-menu-panel" role="dialog" aria-modal="true" aria-label="Menu"
            className="fixed inset-0 z-40 bg-espresso flex flex-col items-center justify-center gap-8 px-5 lg:hidden"
          >
            {[...LINKS, { label: "Discuss a partnership", href: "#partner-form" }].map((l, i) => (
              <motion.a
                key={l.href}
                href={homeHref(l.href)}
                onClick={() => setOpen(false)}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.06 * i, duration: 0.4 }}
                className="min-h-11 inline-flex items-center text-2xl sm:text-3xl leading-[1.3] text-center font-bold text-white hover:text-brass transition-colors"
              >
                {l.label}
              </motion.a>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

export default Nav;
