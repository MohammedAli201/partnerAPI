import { MARKETING_COLORS as brand } from "@/marketing-colors";
import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";

const ORIGINS = [
  { label: "London", y: 60 },
  { label: "Dubai", y: 140 },
  { label: "Minneapolis", y: 220 },
  { label: "Nairobi", y: 300 },
];
const CHANNELS = [
  { label: "EVC Plus", sub: "Hormuud", y: 60, color: "#059669" },
  { label: "ZAAD", sub: "Telesom", y: 140, color: "#D97706" },
  { label: "eDahab", sub: "Somtel", y: 220, color: "#2563EB" },
  { label: "Bank transfer", sub: "Local banks", y: 300, color: "#4F46E5" },
];
const HUB = { x: 290, y: 180 };
const STATES = ["received", "processing", "dispatched", "delivered"];

const curve = (x1, y1, x2, y2) => `M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`;


export const PayoutDiagram = () => {
  const [state, setState] = useState(1);
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    if (reducedMotion) return;
    const timer = setInterval(() => setState(value => (value + 1) % STATES.length), 1800);
    return () => clearInterval(timer);
  }, [reducedMotion]);

  return (
  <div data-testid="hero-payout-diagram" className="hero-routing-layout">
    <div className="hero-status-row">
      <div data-testid="hero-status-pill" className="surface hero-delivery-card">
        <CheckCircle2 className="h-5 w-5 shrink-0 text-teal-600" aria-hidden="true" />
        <div>
          <p className="font-medium">Delivered · ZAAD</p>
          <p className="hero-example-reference">Example · ref HX-2041</p>
        </div>
      </div>
    </div>
        <div className="surface hero-routing-panel relative overflow-hidden p-4 sm:p-6">
          <div className="relative mb-2 flex items-center justify-between font-mono text-[11px] uppercase tracking-[0.16em] text-ink-4">
            <span className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                
                <span className="relative h-2 w-2 rounded-full bg-teal-500" />
              </span>
              Payout routing
            </span>
            <span className="rounded-full border border-line px-2 py-0.5 text-[10px]">Example</span>
          </div>

          <div className="routing-mobile">
            <p className="font-medium">Your payment platform</p>
            <p className="mt-3 text-teal-700">Hubaal connects your instruction to Somalia</p>
            <ul>{CHANNELS.map(c => <li key={c.label}><strong>{c.label}</strong><span className="block text-ink-3">{c.sub}</span></li>)}</ul>
          </div>
          <svg viewBox="0 0 580 340" role="img" aria-label="Example: sending partners connect through Hubaal to payout channels in Somalia" className="routing-desktop relative w-full" fill="none">

            {ORIGINS.map((o, i) => {
              const d = curve(134, o.y, HUB.x - 46, HUB.y);
              return (
                <g key={o.label}>
                  <path d={d} stroke={brand.apricot} strokeWidth="1.5" />
                  <path d={d} stroke={brand.apricot} strokeWidth="1.5" className="flow-line" opacity="0.5" />
                  <circle r="3.5" fill={brand.indigo}>
                    <animateMotion dur={`${2.4 + i * 0.3}s`} repeatCount="indefinite" path={d} begin={`${i * 0.5}s`} />
                  </circle>
                  <g transform={`translate(0 ${o.y})`}>
                    <rect x="4" y="-18" width="130" height="36" rx="18" fill="#fff" stroke={brand.line} />
                    <circle cx="24" cy="0" r="5.5" fill="#F8FAFC" stroke={brand.apricot} strokeWidth="1.5" />
                    <text x="38" y="4.5" fontFamily="Inter, sans-serif" fontSize="14" fontWeight="500" fill={brand.indigo}>
                      {o.label}
                    </text>
                  </g>
                </g>
              );
            })}

            {CHANNELS.map((c, i) => {
              const d = curve(HUB.x + 46, HUB.y, 436, c.y);
              return (
                <g key={c.label}>
                  <path d={d} stroke={brand.apricot} strokeWidth="1.5" />
                  <path d={d} stroke={brand.apricot} strokeWidth="1.5" className="flow-line" opacity="0.5" />
                  <circle r="3.5" fill={c.color}>
                    <animateMotion dur={`${2.6 + i * 0.25}s`} repeatCount="indefinite" path={d} begin={`${0.8 + i * 0.4}s`} />
                  </circle>
                  <g transform={`translate(436 ${c.y})`}>
                    <rect x="0" y="-24" width="140" height="48" rx="12" fill="#fff" stroke={brand.line} />
                    <rect x="10" y="-12" width="24" height="24" rx="6" fill={c.color} />
                    <text x="22" y="4.5" textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="14" fontWeight="700" fill="#fff">
                      {c.label[0]}
                    </text>
                    <text x="44" y="-2" fontFamily="Inter, sans-serif" fontSize="14" fontWeight="600" fill={brand.indigo}>
                      {c.label}
                    </text>
                    <text x="44" y="14" fontFamily="Inter, sans-serif" fontSize="14" fill={brand.muted}>
                      {c.sub}
                    </text>
                  </g>
                </g>
              );
            })}

            <circle cx={HUB.x} cy={HUB.y} r="58" fill="none" />
            <circle cx={HUB.x} cy={HUB.y} r="46" fill={brand.indigo} />
            <circle cx={HUB.x} cy={HUB.y} r="46" stroke={brand.apricot} strokeOpacity="0.4" strokeWidth="1" />
            <circle cx={HUB.x} cy={HUB.y} r="56" stroke={brand.apricot} strokeOpacity="0.25" strokeWidth="1" strokeDasharray="2 6" />
            <g transform={`translate(${HUB.x} ${HUB.y})`}>
              <rect x="-13" y="-14" width="5" height="28" rx="2.5" fill={brand.indigo} />
              <rect x="8" y="-14" width="5" height="28" rx="2.5" fill={brand.apricot} />
              <path d="M-8 -6 C 0 -6, 0 6, 8 6" stroke={brand.ivory} strokeWidth="2.4" strokeLinecap="round" />
            </g>
            <text x={HUB.x} y={HUB.y + 74} textAnchor="middle" fontFamily="Inter, sans-serif" fontSize="14" letterSpacing="0" fill={brand.muted}>
              Hubaal
            </text>
            <text x="4" y="18" fontFamily="Inter, sans-serif" fontSize="14" letterSpacing="0" fill={brand.muted}>
              Sending partners
            </text>
            <text x="576" y="18" textAnchor="end" fontFamily="Inter, sans-serif" fontSize="14" letterSpacing="0" fill={brand.muted}>
              Delivery · Somalia
            </text>
          </svg>
        </div>
    <div className="hero-transaction-row">
      <div data-testid="hero-transaction-card" className="surface hero-example-card">
        <div className="hero-example-top">
          <span>Example payout</span>
          <span className="hero-example-reference">po_8f2…c41</span>
        </div>
        <div className="hero-example-amount">
          <strong>$250.00</strong>
          <span>→ EVC Plus</span>
        </div>
        <div className="hero-example-states">
          {STATES.map((label, index) => (
            <div key={label}>
              <div className={`hero-example-progress ${index <= state ? "is-complete" : ""}`} />
              <span className={index === state ? "text-teal-700" : "text-ink-4"}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  </div>
  );
};
