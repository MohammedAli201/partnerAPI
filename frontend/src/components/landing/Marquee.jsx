import { useState } from "react";
import { Pause, Play } from "lucide-react";
import { CHANNELS } from "@/content/site";

export const Marquee = () => {
  const [paused, setPaused] = useState(false);
  return (
    <div id="payout-channels" data-testid="channel-strip" className="payout-marquee" data-paused={paused}>
      <div className="container-x payout-marquee-inner">
        <span className="payout-marquee-label">Payout channels</span>
        <div className="payout-marquee-window">
          <div className="payout-marquee-track">
            {[0, 1].map(copy => (
              <div key={copy} className="payout-marquee-set" aria-hidden={copy === 1}>
                {CHANNELS.map(channel => (
                  <span key={channel.id} data-testid={copy === 0 ? `strip-channel-${channel.id}` : undefined} className="payout-marquee-channel">
                    <span className="payout-marquee-mark" style={{ background: channel.color }} aria-hidden="true">{channel.mark}</span>
                    {channel.name}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
        <button type="button" onClick={() => setPaused(value => !value)} className="payout-marquee-control" aria-label={paused ? "Resume channel scrolling" : "Pause channel scrolling"} aria-pressed={paused}>
          {paused ? <Play size={16} aria-hidden="true" /> : <Pause size={16} aria-hidden="true" />}
        </button>
      </div>
    </div>
  );
};
