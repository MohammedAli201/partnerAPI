import { MapPin, MessagesSquare, Handshake } from "lucide-react";
import Reveal from "./Reveal";
import { PayoutEyebrow } from "./PayoutSections";

const CAPABILITIES = [
  { icon: MapPin, title: "A local counterpart", desc: "Coordinate the Somalia side of your operation with a team based at the destination." },
  { icon: MessagesSquare, title: "One working relationship", desc: "Discuss delivery requirements, operational responsibilities and support with Hubaal." },
  { icon: Handshake, title: "Your customers stay yours", desc: "Hubaal's role is local payout coordination. Your team owns the sending-side relationship." },
];

const PartnerBand = () => (
  <section id="why-hubaal" data-testid="partner-band" className="payout-section premium-why" aria-labelledby="why-hubaal-title">
    <div className="payout-section-container">
      <Reveal>
        <PayoutEyebrow>Why Hubaal</PayoutEyebrow>
        <div className="why-payout-heading">
          <h2 id="why-hubaal-title" className="payout-section-heading">Focused on <span>your destination.</span></h2>
          <div>
            <p className="payout-section-copy">A dedicated local partner for the part of your operation that happens in Somalia.</p>
          </div>
        </div>
      </Reveal>
      <div className="payout-capabilities" data-testid="capabilities-grid">
        {CAPABILITIES.map((capability, i) => (
          <Reveal key={capability.title} delay={i * 0.06} className="payout-capability">
            <article data-testid={`capability-card-${i + 1}`}>
              <div className="capability-top"><span>0{i + 1}</span><capability.icon className="payout-capability-icon" strokeWidth={1.4} aria-hidden="true" /></div>
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
