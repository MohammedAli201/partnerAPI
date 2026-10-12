import { motion } from "framer-motion";
import { SectionHeader } from "./SectionHeader";
import { fadeUp, stagger, viewport } from "@/lib/motion";

const REASONS = [
  { title: "Based in Mogadishu", body: "Our local team knows the wallets people use and follows up when payouts need attention." },
  { title: "A team you can reach", body: "A dedicated contact, with coverage, funding and pricing agreed up front." },
];

export const WhyHubaal = () => (
  <section id="why-hubaal" data-testid="why-hubaal-section" className="why-section relative py-20 sm:py-24">
    <div className="container-x">
      <SectionHeader eyebrow="Why Hubaal" title="Local knowledge. Direct support." lead="Local expertise and a team you can reach." align="center" className="why-heading" />
      <motion.div variants={stagger(0.1)} initial="hidden" whileInView="show" viewport={viewport} className="why-cards">
        {REASONS.map((reason, index) => (
          <motion.article key={reason.title} variants={fadeUp} data-dark data-testid={`why-item-${index + 1}`} className="why-card">
            <h3>{reason.title}</h3>
            <p>{reason.body}</p>
          </motion.article>
        ))}
      </motion.div>
    </div>
  </section>
);
