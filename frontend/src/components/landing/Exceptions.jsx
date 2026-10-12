import { motion } from "framer-motion";
import { SectionHeader } from "./SectionHeader";
import { fadeUp, viewport } from "@/lib/motion";
import { EXCEPTIONS } from "@/content/site";

export const Exceptions = () => (
  <section id="exceptions" data-testid="exceptions-section" className="relative py-20 sm:py-24">
    <div className="container-x">
      <SectionHeader className="support-heading" eyebrow="Payout support" title="When a payout needs attention." />
      <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={viewport} data-dark className="payout-support-card" data-testid="exceptions-card">
        <p className="payout-support-intro">{EXCEPTIONS.intro}</p>
        <p className="payout-support-outcome">{EXCEPTIONS.partner}</p>
        <p className="payout-support-note">{EXCEPTIONS.note}</p>
      </motion.div>
    </div>
  </section>
);
