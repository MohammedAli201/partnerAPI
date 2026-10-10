import { Share2, MapPin, FileOutput, CopyCheck } from "lucide-react";
import Reveal from "./Reveal";
import { PayoutEyebrow } from "./PayoutSections";

const CAPABILITIES = [
  { icon: Share2, title: "Integration", desc: "Submit payout instructions from your system to Hubaal." },
  { icon: MapPin, title: "Local delivery", desc: "Pay recipients in USD through Somali mobile wallets, bank accounts and cash pickup." },
  { icon: FileOutput, title: "Outcome reporting", desc: "Receive the outcome of each payout with your reference attached." },
  { icon: CopyCheck, title: "Reconciliation", desc: "Match payout records with your transactions using your references." },
];

const PartnerBand = () => (
  <section id="why-hubaal" data-testid="partner-band" className="payout-section" aria-labelledby="why-hubaal-title">
    <div className="payout-section-container">
      <Reveal>
        <PayoutEyebrow>Why Hubaal</PayoutEyebrow>
        <div className="why-payout-heading">
          <h2 id="why-hubaal-title" className="payout-section-heading">Local delivery.<br /> Clear payout outcomes.</h2>
          <div>
            <p className="payout-section-copy">You manage your customers. Hubaal handles payouts in Somalia and returns the outcome with your transaction reference.</p>
            <a href="#partner-form" data-testid="why-cta" className="payout-section-cta">Discuss a partnership</a>
          </div>
        </div>
      </Reveal>
      <div className="payout-capabilities" data-testid="capabilities-grid">
        {CAPABILITIES.map((capability, i) => (
          <Reveal key={capability.title} delay={i * 0.06} className="payout-capability">
            <article data-testid={`capability-card-${i + 1}`}>
              <capability.icon className="payout-capability-icon" strokeWidth={1.5} aria-hidden="true" />
              <h3>{capability.title}</h3>
              <p>{capability.desc}</p>
            </article>
          </Reveal>
        ))}
      </div>
    </div>
  </section>
);

export default PartnerBand;
