import { motion } from "framer-motion";
import { Send, Cpu, Smartphone, FileCheck2 } from "lucide-react";
import { SectionHeader } from "./SectionHeader";
import { fadeUp, stagger, viewport } from "@/lib/motion";

const STEPS = [
  { n: "01", title: "Send", body: "Submit your payout through the API or partner portal.", icon: Send },
  { n: "02", title: "Check", body: "We validate the instruction and your agreed controls.", icon: Cpu },
  { n: "03", title: "Deliver", body: "The selected local channel pays the recipient.", icon: Smartphone },
  { n: "04", title: "Track", body: "Follow status updates and reconcile each payout.", icon: FileCheck2 },
];

export const HowItWorks = () => (
  <section id="how-it-works" data-testid="how-it-works-section" className="relative py-20 sm:py-24">
    <div className="container-x">
      <SectionHeader className="how-heading" eyebrow="How Hubaal works" title="One connection. Four clear steps." lead="From your instruction to the recipient, with status updates along the way." />
      <motion.ol variants={stagger(0.14)} initial="hidden" whileInView="show" viewport={viewport} className="process-grid">
        {STEPS.map((step, index) => (
          <motion.li key={step.n} variants={fadeUp} data-testid={`how-it-works-step-${index + 1}`} className="process-step">
            <span className="process-icon"><step.icon size={30} strokeWidth={1.6} aria-hidden="true" /></span>
            <h3 className="process-title"><span className="process-number">{step.n}</span>{step.title}</h3>
            <p>{step.body}</p>
          </motion.li>
        ))}
      </motion.ol>
    </div>
  </section>
);
