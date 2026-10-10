import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

const Hero = () => (
  <section
    id="top"
    data-testid="hero-container"
    className="relative bg-espresso pt-[110px] sm:pt-[130px] pb-20 sm:pb-24 overflow-hidden"
  >
    <div
      aria-hidden="true"
      className="absolute inset-0 pointer-events-none"
      style={{
        backgroundImage: "radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px)",
        backgroundSize: "26px 26px",
      }}
    />

    <div className="relative max-w-[1200px] mx-auto px-5 sm:px-8 text-center">
      <motion.p
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        data-testid="hero-label"
        className="font-mono text-[11px] sm:text-xs tracking-[0.2em] uppercase mb-8"
      >
        <span className="inline-block w-2 h-2 rounded-full bg-brass mr-3 align-middle" />
        <span className="text-white font-bold">Somalia payout partner</span>
        <span className="text-white/40"> / USD payouts</span>
      </motion.p>

      <motion.h1
        data-testid="hero-title"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.08 }}
        className="font-extrabold tracking-[-0.02em] leading-[1.1] text-[2.5rem] sm:text-[3.25rem] lg:text-[4.25rem] text-white max-w-5xl mx-auto"
      >
        Your payout partner in Somalia<span className="text-brass">.</span>
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.18 }}
        className="mt-6 max-w-2xl mx-auto text-base sm:text-lg leading-[1.65] text-white/70"
      >
        USD payouts for overseas remittance companies and payment businesses
        through Somali mobile wallets, bank accounts and cash pickup.
      </motion.p>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.45 }}
        className="mt-8 flex flex-wrap items-center justify-center gap-4"
      >
        <a
          href="#partner-form"
          data-testid="hero-transact-cta"
          className="group inline-flex items-center gap-2.5 bg-gold text-white font-semibold text-base px-7 py-3.5 rounded-full ring-1 ring-white/25 hover:bg-gold-glow transition-colors duration-300"
        >
          Discuss a partnership
          <ArrowRight size={17} strokeWidth={2.5} className="transition-transform duration-300 group-hover:translate-x-1" />
        </a>
        <a
          href="#channels"
          data-testid="hero-secondary-cta"
          className="inline-flex items-center gap-2 border border-white/25 text-white font-medium text-base px-7 py-3.5 rounded-full hover:border-brass hover:text-brass transition-colors duration-300"
        >
          View payout channels
        </a>
      </motion.div>
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.5 }}
        data-testid="hero-service-status"
        className="mt-7 max-w-xl mx-auto text-sm leading-[1.65] text-white/75"
      >
        Partnership enquiries are open. Payout services are not yet live.
      </motion.p>
    </div>
  </section>
);

export default Hero;

export { ReceivingPanel } from "./ReceivingPanel";
