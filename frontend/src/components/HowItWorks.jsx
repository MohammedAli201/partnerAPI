import sourcePhoto from "../assets/new-photos/photo-1687422809654-579d81c29d32.jpg";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ArrowRight } from "lucide-react";
import Reveal from "./Reveal";

const STEPS = [
  {
    title: "Discuss your requirements",
    body: "Tell us which payout methods you need, your expected volumes and your integration requirements.",
  },
  {
    title: "Agree how we work",
    body: "Agree commercial terms, operational responsibilities and reporting requirements.",
  },
  {
    title: "Test before launch",
    body: "Test payout instructions and outcome reporting before starting live transactions.",
  },
];

const HowItWorks = () => {
  const [open, setOpen] = useState(0);

  return (
    <section id="how-it-works" className="py-16 sm:py-24 bg-surface">
      <div className="max-w-[1200px] mx-auto px-5 sm:px-8 grid lg:grid-cols-12 gap-12 lg:gap-16 items-center">
        <div className="lg:col-span-5" data-testid="how-visual">
          <Reveal>
            <div className="relative max-w-[420px] mx-auto">
              <span
                aria-hidden="true"
                className="absolute -top-8 -left-4 w-[320px] h-[320px] bg-gold"
                style={{ borderRadius: "58% 42% 45% 55% / 52% 48% 52% 48%" }}
              />
              <img
                src={sourcePhoto}
                alt="Woman seated at a market stall"
                width={420} height={480} loading="lazy" decoding="async"
                className="relative w-full h-[420px] sm:h-[480px] object-cover rounded-[2rem] shadow-[0_32px_70px_-24px_rgba(22,32,47,0.35)]"
              />
            </div>
          </Reveal>
        </div>

        <div className="lg:col-span-7" data-testid="how-it-works-grid">
          <Reveal>
            <p className="inline-block text-sm font-bold text-ink-light border-b-2 border-gold pb-1">
              Partner onboarding
            </p>
            <h2 className="mt-5 font-bold tracking-[-0.01em] leading-[1.12] text-[1.75rem] sm:text-[2.375rem] lg:text-[2.75rem] text-ink-light text-balance">
              Start your partnership with Hubaal.
            </h2>
            <p className="mt-5 text-base sm:text-[17px] leading-[1.6] text-ink-dim">
              Agree the requirements, set up the connection and test before launch.
            </p>
          </Reveal>

          <div className="mt-8 space-y-3.5">
            {STEPS.map((s, i) => {
              const isOpen = open === i;
              return (
                <Reveal key={s.title} delay={i * 0.06}>
                  <div
                    className={`bg-white rounded-2xl border transition-colors duration-300 ${
                      isOpen ? "border-gold/40" : "border-line"
                    }`}
                  >
                    <button
                      id={`onboarding-step-${i + 1}`}
                      aria-controls={isOpen ? `onboarding-details-${i + 1}` : undefined}
                      data-testid={`how-step-${i + 1}`}
                      aria-expanded={isOpen}
                      onClick={() => setOpen(isOpen ? -1 : i)}
                      className="w-full flex items-center justify-between gap-5 px-6 sm:px-7 py-5 text-left"
                    >
                      <span className="text-base sm:text-lg font-bold text-ink-light">
                        {i + 1} — {s.title}
                      </span>
                      <span className="w-8 h-8 rounded-full bg-gold flex items-center justify-center shrink-0">
                        <ChevronDown
                          size={15}
                          strokeWidth={2.75}
                          className={`text-white transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`}
                        />
                      </span>
                    </button>
                    <AnimatePresence initial={false}>
                      {isOpen && (
                        <motion.div
                          id={`onboarding-details-${i + 1}`} role="region" aria-labelledby={`onboarding-step-${i + 1}`}
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                          className="overflow-hidden"
                        >
                          <p className="px-6 sm:px-7 pb-6 text-[15px] leading-[1.65] text-ink-dim">
                            {s.body}
                          </p>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </Reveal>
              );
            })}
          </div>

          <Reveal delay={0.15}>
            <a
              href="#partner-form"
              data-testid="how-cta"
              className="group mt-8 inline-flex items-center gap-2.5 bg-gold text-white font-semibold text-base px-7 py-3.5 rounded-full hover:bg-gold-dark transition-colors duration-300"
            >
              Discuss a partnership
              <ArrowRight
                size={17}
                strokeWidth={2.5}
                className="transition-transform duration-300 group-hover:translate-x-1"
              />
            </a>
          </Reveal>
        </div>
      </div>
    </section>
  );
};

export default HowItWorks;
