import { MapPin } from "lucide-react";
import Reveal from "./Reveal";
import "./About.css";

const About = () => (
  <section id="about" data-testid="about-section" className="hubaal-about" aria-labelledby="about-title">
    <div className="hubaal-about-container">
      <div className="hubaal-about-layout">
        <Reveal>
          <div className="hubaal-about-eyebrow">
            <span>About Hubaal</span>
            <span className="hubaal-about-rule" aria-hidden="true" />
          </div>
          <h2 id="about-title" className="hubaal-about-title">
            Your local team <span>in Mogadishu.</span>
          </h2>
          <p className="hubaal-about-copy">
            Our Somalia-based team is your contact for partnership enquiries,
            payout coordination and reconciliation.
          </p>
        </Reveal>
        <Reveal delay={0.12} className="hubaal-about-office-wrapper">
          <aside className="hubaal-about-office" aria-labelledby="about-location">
            <svg className="hubaal-about-orbits" width="360" height="240" viewBox="0 0 360 240" fill="none" aria-hidden="true">
              <circle cx="365" cy="-26" r="130" stroke="white" strokeOpacity="0.65" strokeWidth="0.7" />
              <circle cx="365" cy="-26" r="171" stroke="#C9A45C" strokeOpacity="0.85" strokeWidth="0.7" />
              <circle cx="365" cy="-26" r="228" stroke="#C9A45C" strokeOpacity="0.3" strokeWidth="0.7" />
            </svg>
            <p className="hubaal-about-office-label">Somalia operations</p>
            <h3 id="about-location" className="hubaal-about-location">Mogadishu,<br /> Somalia</h3>
            <div className="hubaal-about-contact">
              <div>
                <p className="hubaal-about-contact-label">Partnership enquiries</p>
                <a href="mailto:partners@hubaal.so">partners@hubaal.so</a>
              </div>
              <MapPin className="hubaal-about-pin" size={38} strokeWidth={1.4} aria-hidden="true" />
            </div>
          </aside>
        </Reveal>
      </div>
    </div>
  </section>
);

export default About;
