import { useState } from "react";
import { motion } from "framer-motion";
import { Scale, ChevronDown } from "lucide-react";
import { SectionHeader } from "./SectionHeader";
import { fadeUp, viewport } from "@/lib/motion";
import { COMPANY } from "@/content/site";

const PILLARS = [
  { title: "Payout checks", body: "Eligibility and funding are checked before each payout." },
  { title: "Clear tracking", body: "Follow each payout by your reference and its status history." },
  { title: "Controlled access", body: "Scoped credentials and signed callbacks protect your operations." },
  { title: "Careful retries", body: "Duplicate requests keep one identity. Uncertain outcomes are reviewed before retrying." },
];

export const Trust = () => {
  const [expanded, setExpanded] = useState(0);
  return (
    <section id="trust" data-testid="trust-section" className="relative py-20 sm:py-24">
      <div className="container-x">
        <div className="trust-accordion-layout">
          <div>
            <SectionHeader className="trust-heading" eyebrow="Safeguards" title="Confidence in every step." lead="Clear records, controlled access and careful handling when a payout needs review." />
          </div>
          <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={viewport} className="trust-accordion">
            {PILLARS.map((pillar, index) => (
              <article key={pillar.title} data-testid={`trust-pillar-${index + 1}`} className="trust-accordion-item">
                <button type="button" onClick={() => setExpanded(active => active === index ? null : index)} aria-expanded={expanded === index} aria-controls={`trust-panel-${index}`} className="trust-accordion-summary">
                  <span>{pillar.title}</span><ChevronDown size={20} aria-hidden="true" />
                </button>
                <div id={`trust-panel-${index}`} hidden={expanded !== index} className="trust-accordion-body"><p>{pillar.body}</p></div>
              </article>
            ))}
          </motion.div>
        </div>
        <motion.article variants={fadeUp} initial="hidden" whileInView="show" viewport={viewport} data-testid="trust-regulatory-badge" className="trust-card trust-regulatory trust-license-note">
          <Scale className="h-6 w-6 text-amber-800" aria-hidden="true" />
          <h3>{COMPANY.regulatoryStatus}</h3>
          <p>{COMPANY.regulatoryDetail}</p>
        </motion.article>
      </div>
    </section>
  );
};
