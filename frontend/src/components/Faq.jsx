import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown } from "lucide-react";
import Reveal from "./Reveal";
import { PayoutEyebrow } from "./PayoutSections";

export const FAQS = [
  [
    "Is Hubaal accepting live payouts?",
    "Not yet. Approval is in progress. Partnership enquiries are open while we prepare for launch.",
  ],
  [
    "Who is Hubaal’s service for?",
    "Overseas remittance companies and payment businesses that need a local payout partner in Somalia.",
  ],
  [
    "Does an enquiry establish a partnership?",
    "No. An enquiry starts the discussion. Commercial terms and service arrangements are agreed separately.",
  ],
];

const Faq = () => {
  const [open, setOpen] = useState(0);

  return (
    <section id="faq" data-testid="faq-section" aria-labelledby="faq-title" className="py-16 sm:py-24 bg-surface font-sans">
      <div className="max-w-[1200px] mx-auto px-5 sm:px-8 grid lg:grid-cols-12 gap-8 sm:gap-10 lg:gap-16 items-start">
        <div className="lg:col-span-5 min-w-0" data-testid="faq-introduction">
          <Reveal>
            <PayoutEyebrow>FAQ</PayoutEyebrow>
            <h2 id="faq-title" className="mt-7 font-sans font-extrabold tracking-[-0.025em] leading-[1.2] text-[2rem] sm:text-[2.5rem] lg:text-[3rem] text-ink-light">
              Partner questions
            </h2>
          </Reveal>
        </div>

        <div className="lg:col-span-7 min-w-0 space-y-4" data-testid="faq-list">
          {FAQS.map(([q, a], i) => {
            const isOpen = open === i;
            return (
              <Reveal key={q} delay={i * 0.04}>
                <div
                  className={`bg-white rounded-2xl border transition-colors duration-300 ${
                    isOpen ? "border-gold/40" : "border-line"
                  }`}
                >
                  <button
                    id={`faq-question-${i + 1}`}
                    aria-controls={isOpen ? `faq-answer-${i + 1}` : undefined}
                    data-testid={`faq-item-${i + 1}`}
                    aria-expanded={isOpen}
                    onClick={() => setOpen(isOpen ? -1 : i)}
                    className="w-full flex items-center justify-between gap-5 px-6 sm:px-7 py-6 text-left font-sans"
                  >
                    <span className="min-w-0 text-[15px] sm:text-base font-semibold leading-[1.6] text-ink-light">{q}</span>
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
                        id={`faq-answer-${i + 1}`} role="region" aria-labelledby={`faq-question-${i + 1}`}
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                        className="overflow-hidden"
                      >
                        <p className="px-6 sm:px-7 pb-6 font-sans text-[15px] leading-[1.75] text-ink-dim">{a}</p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
};

export default Faq;
