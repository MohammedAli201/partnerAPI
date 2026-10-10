import "./ChannelLogo.css";

// Keep the supplied PNG intact; fit its visible artwork instead of empty margins.
export default function ChannelLogo({ channel }) {
  const [x, y, width, height] = channel.frame;
  return (
    <span className="channel-logo" aria-hidden="true">
      <span className="channel-logo-frame" style={{ "--channel-logo-ratio": width / height }}>
        <img
          src={channel.logo}
          alt=""
          data-channel-logo={channel.name}
          width={channel.width}
          height={channel.height}
          loading="lazy"
          decoding="async"
          style={{
            width: `${channel.width / width * 100}%`,
            height: `${channel.height / height * 100}%`,
            left: `${-x / width * 100}%`,
            top: `${-y / height * 100}%`,
          }}
        />
      </span>
    </span>
  );
}
