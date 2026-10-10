import evcPlus from "./assets/channel-logos/evc-plus.png";
import zaad from "./assets/channel-logos/zaad.png";
import edahab from "./assets/channel-logos/edahab.png";
import salaamBank from "./assets/channel-logos/salaam-bank.png";
import premierBank from "./assets/channel-logos/premier-bank.png";

// User-supplied receiving-channel artwork. Shared by cards and coverage.
export const payoutChannels = [
  { name: "EVC Plus", type: "Mobile wallet", logo: evcPlus, width: 1972, height: 798, frame: [115, 192, 1721, 433] },
  { name: "ZAAD", type: "Mobile wallet", logo: zaad, width: 1254, height: 1254, frame: [109, 168, 1036, 951] },
  { name: "eDahab", type: "Mobile wallet", logo: edahab, width: 2076, height: 758, frame: [154, 184, 1768, 405] },
  { name: "Salaam Bank", type: "Bank", logo: salaamBank, width: 1774, height: 887, frame: [125, 171, 1559, 634] },
  { name: "Premier Bank", type: "Bank", logo: premierBank, width: 1546, height: 1017, frame: [93, 126, 1372, 853] },
  { name: "Cash pickup", type: "Cash pickup" },
];

export const partnershipChannelOptions = ["All channels", "Wallets only", "Banks only", "Cash pickup only", "Wallets + banks", "Wallets + banks + cash pickup"];
