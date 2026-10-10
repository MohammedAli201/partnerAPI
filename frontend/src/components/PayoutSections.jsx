import { ArrowRight } from "lucide-react";
import "./PayoutSections.css";

export const PayoutEyebrow = ({ children }) => <p className="payout-section-eyebrow">{children}</p>;

export const PartnershipAction = ({ testid }) => (
  <a href="#partner-form" className="payout-section-cta" data-testid={testid}>
    Discuss a partnership <ArrowRight size={21} strokeWidth={1.8} aria-hidden="true" />
  </a>
);
