import { Smartphone, Landmark, Banknote } from "lucide-react";
import CashPickupIcon from "./CashPickupIcon";
import Reveal from "./Reveal";
import ChannelLogo from "./ChannelLogo";
import { PayoutEyebrow } from "./PayoutSections";
import { payoutChannels } from "../channels";

const LogoGroup = ({ title, type }) => (
  <div className="payout-channel-group" data-testid={`channel-group-${type === "Bank" ? "banks" : "wallets"}`}>
    <div className="channel-card-top"><span className="channel-index">{type === "Bank" ? "02" : "01"} / PAYOUT METHOD</span>{type === "Bank" ? <Landmark size={24} strokeWidth={1.4} aria-hidden="true"/> : <Smartphone size={24} strokeWidth={1.4} aria-hidden="true"/>}</div>
    <h3>{title}</h3>
    <p className="channel-description">{type === "Bank" ? "Direct to a recipient account." : "Through a supported mobile wallet."}</p>
    <ul className="payout-channel-logos" aria-label={title}>
      {payoutChannels.filter(channel => channel.type === type).map(channel => (
        <li key={channel.name} data-testid="channel-logo-item">
          <ChannelLogo channel={channel} />
          <span className="sr-only">{channel.name}</span>
        </li>
      ))}
    </ul>
  </div>
);

const Channels = () => (
  <section id="channels" data-testid="channels-section" className="payout-section premium-channels" aria-labelledby="channels-title">
    <div className="payout-section-container">
      <Reveal>
        <PayoutEyebrow>Payout channels</PayoutEyebrow>
        <div className="channels-heading-row">
          <h2 id="channels-title" className="payout-section-heading">Three ways <span>to receive.</span></h2>
          <p className="payout-section-copy">Choose the delivery method that fits your recipients. Channel availability is confirmed during onboarding.</p>
        </div>
      </Reveal>
      <Reveal delay={0.1}>
        <div className="payout-channel-panel" data-testid="channels-grid">
          <div className="payout-channel-groups">
            <LogoGroup title="Mobile wallets" type="Mobile wallet" />
            <LogoGroup title="Bank accounts" type="Bank" />
            <div className="payout-channel-group payout-channel-cash" data-testid="channel-group-cash">
              <div className="channel-card-top"><span className="channel-index">03 / PAYOUT METHOD</span><Banknote size={24} strokeWidth={1.4} aria-hidden="true"/></div><h3>Cash pickup</h3><p className="channel-description">Collection through local coordination.</p>
              <CashPickupIcon className="payout-channel-cash-icon" />
            </div>
          </div>
          <div className="payout-channel-currency"><span><span className="currency-dot" aria-hidden="true"/> Recipient payout currency</span><strong>USD <span>United States dollar</span></strong></div>
        </div>
      </Reveal>
    </div>
  </section>
);

export default Channels;
