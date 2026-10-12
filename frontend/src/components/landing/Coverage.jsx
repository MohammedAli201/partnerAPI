import { motion } from "framer-motion";
import { Check, Landmark } from "lucide-react";
import { SectionHeader } from "./SectionHeader";
import { fadeUp, viewport } from "@/lib/motion";
import { CHANNELS, STATUS_LABEL } from "@/content/site";
import ChannelLogo from "@/components/ChannelLogo";
import { payoutChannels } from "@/channels";

export const Coverage = () => (
  <section id="coverage" data-testid="coverage-section" className="relative py-20 sm:py-24">
    <div className="container-x coverage-layout">
      <div className="coverage-copy">
        <SectionHeader className="coverage-heading" eyebrow="Payout channels" title="Reach local wallets." lead="One USD payout connection for Somalia. Wallet integrations are in testing." />
        <ul className="coverage-benefits">
          <li><Check size={16} aria-hidden="true" /><span>One API connection</span></li>
          <li><Check size={16} aria-hidden="true" /><span>Payout status updates</span></li>
        </ul>
        <p className="coverage-note">Wallets must be registered and beneficiary names must match. Limits and delivery timing will be confirmed during pilot testing.</p>
      </div>
      <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={viewport} className="coverage-channel-card">
        <ul className="coverage-channel-list" aria-label="Somalia payout channels in USD and their availability">
          {CHANNELS.map(channel => (
            <li key={channel.id} className="coverage-channel-row" data-testid={`channel-card-${channel.id}`}>
              <span className="coverage-provider-logo">
                {channel.id === "banks" ? <Landmark size={30} strokeWidth={1.5} aria-hidden="true" /> : <ChannelLogo channel={payoutChannels.find(provider => provider.name === channel.name)} />}
              </span>
              <div className="coverage-channel-identity">
                <h3>{channel.name}</h3>
                <p>{channel.provider}</p>
                <span className="sr-only" data-testid={`channel-currency-${channel.id}`}>{channel.method}, {channel.currency}</span>
              </div>
              <span data-testid={`channel-status-${channel.id}`} data-status={channel.status} className="coverage-status">{STATUS_LABEL[channel.status]}</span>
            </li>
          ))}
        </ul>
      </motion.div>
    </div>
  </section>
);
