import { Handshake, ShieldCheck, Zap, Users, Globe2, Heart } from "lucide-react";
import Reveal from "./Reveal";
import { PayoutEyebrow } from "./PayoutSections";

const VALUES = [
  { icon: Handshake, title: "Trust through clarity", text: "Be clear about what is agreed, what is confirmed and what still needs attention." },
  { icon: ShieldCheck, title: "Care with information", text: "Treat partner information and recipient details with the care they deserve." },
  { icon: Zap, title: "Purposeful progress", text: "Keep responsibilities and next steps clear, so each handoff can move forward." },
  { icon: Users, title: "People behind the payout", text: "Remember the person waiting to receive, not only the instruction on a screen." },
  { icon: Globe2, title: "Global understanding", text: "Understand the sending partner's context while staying grounded in Somalia." },
  { icon: Heart, title: "Partnership with attention", text: "Listen first. Shape the working relationship around the requirements we agree together." },
];

export default function CoreValues() {
  return <section id="values" className="site-section core-values" aria-labelledby="values-title" data-testid="core-values-section">
    <div className="site-container">
      <Reveal><div className="site-section-heading"><div><PayoutEyebrow>The Hubaal standard</PayoutEyebrow><h2 id="values-title" className="site-heading">Our core values.</h2></div><p className="site-copy">The principles we bring to our work and to every partner relationship.</p></div></Reveal>
      <div className="values-grid">{VALUES.map(({ icon: Icon, title, text }, index) => <Reveal key={title} delay={index * 0.04}>
        <article className="value-card"><div className="value-card-top"><span className="value-icon"><Icon size={23} strokeWidth={1.5} aria-hidden="true"/></span><span className="site-number">0{index + 1}</span></div><h3>{title}</h3><p>{text}</p></article>
      </Reveal>)}</div>
    </div>
  </section>;
}
