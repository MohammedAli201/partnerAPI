import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, Globe, LogIn, Menu, X } from "lucide-react";
import { Logo } from "./Logo";
import { scrollToId } from "@/hooks/useLenis";
import { ease } from "@/lib/motion";
import { COMPANY } from "@/content/site";

const LINKS = [
  { label: "Coverage", href: "#coverage", id: "coverage" },
  { label: "Why Hubaal", href: "#why-hubaal", id: "why" },
  { label: "Process", href: "#how-it-works", id: "process" },
  { label: "Company", href: "#about", id: "about" },
];

export const Nav = () => {
  const dark = true;
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if(!open)return;
    const menu=document.querySelector('[data-testid="nav-mobile-menu"]');
    const main=document.getElementById('main'),footer=document.querySelector('footer');
    const overflow=document.body.style.overflow;document.body.style.overflow='hidden';
    if(main)main.inert=true;if(footer)footer.inert=true;window.__lenis?.stop();
    menu?.querySelector('button')?.focus();
    const key=e=>{
      if(e.key==='Escape'){e.preventDefault();setOpen(false);return;}
      if(e.key!=='Tab')return;
      const items=[...menu.querySelectorAll('a,button')];
      const i=items.indexOf(document.activeElement);e.preventDefault();items[(i+(e.shiftKey?-1:1)+items.length)%items.length]?.focus();
    };
    const desktop=window.matchMedia('(min-width:1200px)');const resize=()=>{if(desktop.matches)setOpen(false);};desktop.addEventListener('change',resize);
    document.addEventListener('keydown',key);
    return ()=>{desktop.removeEventListener('change',resize);document.removeEventListener('keydown',key);document.body.style.overflow=overflow;if(main)main.inert=false;if(footer)footer.inert=false;window.__lenis?.start();document.querySelector('[data-testid="nav-mobile-toggle"]')?.focus();};
  },[open]);

  const go = (href) => (e) => {
    e.preventDefault();
    setOpen(false);
    scrollToId(href);
  };

  return (
    <>
      <motion.header
        initial={{ y: -24, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, ease, delay: 0.1 }}
        data-testid="site-nav"
        className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-ink text-white"
      >
        <div className="container-x flex h-[72px] items-center justify-between">
          <Logo dark={dark} />
          <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary">
            {LINKS.map((l) => (
              <a
                key={l.id}
                href={l.href}
                onClick={go(l.href)}
                data-testid={`nav-item-${l.id}`}
                className={`group relative whitespace-nowrap rounded-full px-3.5 py-2 text-[14px] font-medium transition-colors duration-300 ${dark ? "text-slate-300 hover:text-white" : "text-ink-3 hover:text-ink"}`}
              >
                {l.label}
                <span className="absolute inset-x-4 -bottom-px h-px origin-left scale-x-0 bg-teal-500 transition-transform duration-300 group-hover:scale-x-100" />
              </a>
            ))}
          </nav>
          <div className="hidden items-center gap-2 lg:flex">
            <a
              href="/?lang=en" aria-label="English page"
              data-testid="nav-lang-switcher"
              className={`inline-flex h-10 items-center gap-1.5 rounded-full px-3 font-mono text-[12px] font-medium transition-colors ${dark ? "text-slate-300 hover:bg-white/10 hover:text-white" : "text-ink-3 hover:bg-white hover:text-ink"}`}
            >
              <Globe className="h-3.5 w-3.5" /> EN
            </a>
            <a
              href="/login"
              data-testid="nav-portal-link"
              className={`inline-flex h-10 items-center gap-1.5 whitespace-nowrap rounded-full px-3 text-[14px] font-medium transition-colors ${dark ? "text-white hover:bg-white/10" : "text-ink hover:bg-white"}`}
            >
              <LogIn className="h-3.5 w-3.5" /> Sign in
            </a>
            <a href="#enquiry" onClick={go("#enquiry")} data-testid="nav-cta-btn" className={`btn-primary !h-10 whitespace-nowrap !px-5 text-[14px] ${dark ? "!bg-teal-500 !text-white hover:!bg-teal-400" : ""}`}>
              Partner with us <ArrowUpRight className="h-4 w-4" />
            </a>
          </div>
          <button
            type="button"
            aria-label="Open menu"
            data-testid="nav-mobile-toggle" aria-expanded={open} aria-controls={open?"landing-mobile-menu":undefined}
            onClick={() => setOpen(true)}
            className={`inline-flex h-10 w-10 items-center justify-center rounded-full border lg:hidden ${dark ? "border-white/15 bg-white/10 text-white" : "border-line bg-white"}`}
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>
      </motion.header>

      <AnimatePresence>
        {open && (
          <motion.div
            id="landing-mobile-menu" data-testid="nav-mobile-menu" role="dialog" aria-modal="true" aria-label="Main navigation"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="fixed inset-0 z-[60] flex flex-col bg-ink text-white lg:hidden"
          >
            <div className="container-x flex h-[72px] items-center justify-between">
              <Logo dark testId="mobile-brand-logo" />
              <button
                type="button"
                aria-label="Close menu"
                data-testid="nav-mobile-close"
                onClick={() => setOpen(false)}
                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/15"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="container-x flex flex-1 flex-col justify-between pb-10 pt-6">
              <ul className="space-y-1">
                {LINKS.map((l, i) => (
                  <motion.li
                    key={l.id}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.08 + i * 0.06, duration: 0.6, ease }}
                  >
                    <a
                      href={l.href}
                      onClick={go(l.href)}
                      data-testid={`nav-mobile-item-${l.id}`}
                      className="flex items-center justify-between border-b border-white/10 py-5 text-[32px] font-semibold tracking-[-0.03em]"
                    >
                      {l.label}
                      <ArrowUpRight className="h-6 w-6 text-teal-400" />
                    </a>
                  </motion.li>
                ))}
              </ul>
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.45, duration: 0.6, ease }}
                className="space-y-3"
              >
                <a href="#enquiry" onClick={go("#enquiry")} data-testid="nav-mobile-cta" className="btn-primary w-full !bg-teal-500 hover:!bg-teal-400">
                  Partner with us <ArrowUpRight className="h-4 w-4" />
                </a>
                <a href={`mailto:${COMPANY.email}`} data-testid="nav-mobile-email" className="btn-secondary w-full !border-white/20 !bg-transparent !text-white">
                  {COMPANY.email}
                </a>
                <a href="/login" className="block text-center text-sm text-slate-300">Partner sign in</a>
                <p className="pt-4 text-center font-mono text-[11px] uppercase tracking-[0.18em] text-slate-500">EN · English</p>
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};
