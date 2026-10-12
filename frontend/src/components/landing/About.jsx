import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { fadeUp, viewport } from "@/lib/motion";

export const About = () => (
  <section id="about" data-testid="about-section" className="relative py-20 sm:py-24">
    <div className="container-x">
      <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={viewport} data-dark className="company-panel">
        <p className="eyebrow">About Hubaal Express</p>
        <h2 className="h2">Built around <span>Somalia.</span> Closer to its people.</h2>
        <p className="company-panel-copy">We are building the connection between payment businesses and the wallets people use in Somalia.</p>
        <div className="company-flow" aria-label="Your business connects through Hubaal to recipients in Somalia">
          <div className="company-flow-node">
            <span className="company-flow-number">01</span>
            <h3>Your business</h3>
            <p>Payment platform</p>
          </div>
          <ArrowRight className="company-flow-arrow" size={24} aria-hidden="true" />
          <div className="company-flow-node company-flow-hubaal">
            <span className="company-flow-number">02</span>
            <h3>Hubaal</h3>
            <p>Local connection</p>
          </div>
          <ArrowRight className="company-flow-arrow" size={24} aria-hidden="true" />
          <div className="company-flow-node">
            <span className="company-flow-number">03</span>
            <h3>Recipients</h3>
            <p>Somalia ? USD</p>
          </div>
        </div>
      </motion.div>
    </div>
  </section>
);
