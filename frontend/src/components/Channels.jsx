import CashPickupIcon from "./CashPickupIcon";
import Reveal from "./Reveal";
import ChannelLogo from "./ChannelLogo";
import { PayoutEyebrow } from "./PayoutSections";
import { payoutChannels } from "../channels";

const LogoGroup = ({ title, type }) => (
  <div className="payout-channel-group" data-testid={`channel-group-${type === "Bank" ? "banks" : "wallets"}`}>
    <h3>{title}</h3>
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
  <section id="channels" data-testid="channels-section" className="payout-section" aria-labelledby="channels-title">
    <div className="payout-section-container">
      <Reveal>
        <PayoutEyebrow>Payout channels</PayoutEyebrow>
        <div className="channels-heading-row">
          <h2 id="channels-title" className="payout-section-heading">Three payout methods.<br /> One local partner.</h2>
          <p className="payout-section-copy">Deliver funds to your recipients through supported Somali mobile wallets, bank accounts and cash pickup. All recipient payouts are in USD.</p>
        </div>
      </Reveal>
      <Reveal delay={0.1}>
        <div className="payout-channel-panel" data-testid="channels-grid">
          <div className="payout-channel-groups">
            <LogoGroup title="Mobile wallets" type="Mobile wallet" />
            <LogoGroup title="Bank accounts" type="Bank" />
            <div className="payout-channel-group payout-channel-cash" data-testid="channel-group-cash">
              <h3>Cash pickup</h3>
              <CashPickupIcon className="payout-channel-cash-icon" />
              <p>Recipients collect their payout in USD.</p>
            </div>
          </div>
          <div className="payout-channel-currency"><span>Recipient payout currency:</span><strong>USD</strong></div>
        </div>
      </Reveal>
    </div>
  </section>
);

export default Channels;
