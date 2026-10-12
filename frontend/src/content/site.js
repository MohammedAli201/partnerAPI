// Single source of truth for claims shown on the landing page. Edit here, not in components.

export const COMPANY = {
  brand: "Hubaal Express",
  legalName: "Hubaal Express Money Transfer",
  registrationNumber: "3896961",
  jurisdiction: "Mogadishu, Somalia",
  city: "Mogadishu, Somalia",
  email: "partner@hubaalexpress.com",
  phone: "+252 61 500 0000",
  regulatoryStatus: "Licence application in progress",
  regulatoryDetail:
    "Our Somalia payout licence application is awaiting a decision. Payout services are not yet live.",
  why: "We are building a Somalia payout connection around the wallets people use, so funds can reach the families they are meant for.",
};

export const LEADERSHIP = [
  {
    name: "Mohamed Ali Abdullahi",
    role: "Founder & Technical Lead",
    bio: "Software engineer with a master's in ICT, building Hubaal's payment integrations and payout automation.",
  },
];

// Status vocabulary: "live" | "pilot" | "testing" | "planned"
export const STATUS_LABEL = {
  live: "Live",
  pilot: "Available for pilot",
  testing: "In testing",
  planned: "Planned",
};

export const STATUS_STYLE = {
  live: "border-teal-200 bg-teal-50 text-teal-700",
  pilot: "border-cobalt-200 bg-cobalt-50 text-cobalt-700",
  testing: "border-amber-200 bg-amber-50 text-amber-700",
  planned: "border-line bg-canvas text-ink-4",
};

const TIMING_PENDING = "Delivery timing will be assessed during pilot testing";

export const CHANNELS = [
  { id: "evc", name: "EVC Plus", provider: "Hormuud Telecom", method: "Mobile wallet", currency: "USD", status: "testing", restrictions: "Registered EVC Plus wallets; per-transaction limits apply", timing: TIMING_PENDING, color: "#059669", mark: "EVC+" },
  { id: "zaad", name: "ZAAD", provider: "Telesom", method: "Mobile wallet", currency: "USD", status: "testing", restrictions: "Registered ZAAD wallets; per-transaction limits apply", timing: TIMING_PENDING, color: "#D97706", mark: "ZAAD" },
  { id: "edahab", name: "eDahab", provider: "Somtel", method: "Mobile wallet", currency: "USD", status: "testing", restrictions: "Registered eDahab wallets; per-transaction limits apply", timing: TIMING_PENDING, color: "#2563EB", mark: "eDahab" },
  { id: "banks", name: "Bank transfer", provider: "Bank coverage to be confirmed", method: "Bank account", currency: "USD", status: "planned", restrictions: "Account-holder name must match beneficiary", timing: TIMING_PENDING, color: "#4F46E5", mark: "Bank" },
];

export const VALUES = [
  { title: "Accountability", text: "We own each payout through to its final outcome, including exceptions." },
  { title: "Transparency", text: "Partners see status, charges, balances and reconciliation without asking." },
  { title: "Careful execution", text: "Instructions are checked, access is scoped and duplicates are prevented." },
  { title: "Local understanding", text: "We know the channels, and the people receiving the money." },
];

export const EXCEPTIONS = {
  intro: "Our Mogadishu team follows up delayed, rejected or missing payouts with the channel provider.",
  partner: "You receive the outcome, reason and case reference for your records.",
  note: "Response times and procedures are agreed during onboarding.",
};

export const DUE_DILIGENCE = [
  "Registration and licence status",
  "Security and access controls",
  "Operations and compliance responsibilities",
  "Coverage, funding and pricing",
];
