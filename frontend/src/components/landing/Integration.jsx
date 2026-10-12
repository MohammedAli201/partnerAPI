import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Copy } from "lucide-react";
import { toast } from "sonner";
import { ease } from "@/lib/motion";
import onboardingImage from "@/assets/onboarding/hubaal-phone-user.png";

const SNIPPETS = {
  post: {
    label: "POST /payouts-create",
    code: `{
  "partner_tx_id": "00000000-0000-4000-8000-000000000001",
  "amount": 10,
  "currency": "USD",
  "recipient": "+2526XXXXXXXX",
  "provider": "EVC",
  "request_payload": {
    "beneficiary": {
      "name": "Recipient's registered name",
      "mobile": "+2526XXXXXXXX",
      "network": "Hormuud"
    },
    "reference": "Partner reference",
    "callback_url": "https://partner.example/webhooks/hubaal"
  }
}`,
  },
  webhook: {
    label: "Webhook / payout status",
    code: `{
  "event_id": "00000000-0000-4000-8000-000000000002",
  "partner_tx_id": "00000000-0000-4000-8000-000000000001",
  "status": "Paid",
  "provider": "EVC",
  "provider_reference": "00000000-0000-4000-8000-000000000003",
  "amount": 10,
  "currency": "USD",
  "recipient": "+2526XXXXXXXX",
  "payout_channel": "evc",
  "timestamp": "2026-10-12T12:00:00Z"
}`,
  },
};

const ONBOARDING = [
  { title: "Agree the scope", body: "Confirm channels, funding, pricing and responsibilities with our team." },
  { title: "Connect your platform", body: "Use the integration guide to set up authentication, payout requests and signed callbacks." },
  { title: "Test and review", body: "Test the agreed workflow and review operational readiness before a pilot." },
];

const highlight = (line) =>
  line.split(/("(?:[^"\\]|\\.)*"|\b\d+(?:\.\d+)?\b|[{}[\],:])/g).filter(Boolean).map((tok, i) => {
    if (/^"/.test(tok)) {
      const after = line.slice(line.indexOf(tok) + tok.length, line.indexOf(tok) + tok.length + 1);
      return <span key={i} className={after === ":" ? "text-teal-300" : "text-amber-200"}>{tok}</span>;
    }
    if (/^\d/.test(tok)) return <span key={i} className="text-cobalt-300">{tok}</span>;
    if (/^[{}[\],:]$/.test(tok)) return <span key={i} className="text-slate-500">{tok}</span>;
    return <span key={i} className="text-slate-300">{tok}</span>;
  });

export const Integration = () => {
  const [tab, setTab] = useState("post");
  const [onboarding, setOnboarding] = useState(0);
  const [open, setOpen] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(SNIPPETS[tab].code);
      toast.success("Example copied");
    } catch {
      toast.message("Copy unavailable in this browser");
    }
  };

  return (
    <section id="integration" data-testid="integration-section" className="relative py-20 sm:py-24">
      <div className="container-x">
        <div className="onboarding-grid">
          <motion.div initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.8, ease }} className="onboarding-visual">
            <img src={onboardingImage} alt="A person using a phone" width="1024" height="1536" loading="lazy" />
          </motion.div>
          <div>
            <p className="eyebrow">Getting started</p>
            <h2 className="h2 mt-5">Connect with Hubaal.</h2>
            <p className="lead mt-6">Build your Somalia connection with hands-on support from our team.</p>
            <div className="onboarding-steps">
              {ONBOARDING.map((step, index) => (
                <article key={step.title} className="onboarding-step">
                  <button type="button" onClick={() => setOnboarding(active => active === index ? null : index)} aria-expanded={onboarding === index} aria-controls={`onboarding-step-${index}`} className="onboarding-summary">
                    <span><span className="onboarding-number">{index + 1}</span>{step.title}</span>
                    <ChevronDown size={20} aria-hidden="true" />
                  </button>
                  <div id={`onboarding-step-${index}`} hidden={onboarding !== index} className="onboarding-body"><p>{step.body}</p></div>
                </article>
              ))}
            </div>
          </div>
        </div>

        <div className="integration-actions">
        <a href="/partners/integration" className="mt-7 inline-flex text-sm text-teal-300 underline underline-offset-4">Read the integration guide</a>
        <button type="button" data-testid="api-toggle-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="mt-10 inline-flex items-center gap-2 rounded-full border border-white/15 px-5 py-2.5 text-[14px] font-medium text-white transition-colors hover:border-teal-400/60 hover:bg-white/5">
          {open ? "Hide example payloads" : "View example payloads"} <ChevronDown className={`h-4 w-4 transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
        </button>
        </div>

        <AnimatePresence initial={false}>
          {open && (
            <motion.div key="panel" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.5, ease }} className="overflow-hidden">
              <p className="integration-example-note mt-5 text-xs leading-relaxed text-slate-400">Replace the illustrative recipient details and references before use. These examples contain no credentials and do not submit payments. The callback URL must match your registered partner endpoint; webhook signatures are supplied in HTTP headers.</p>
              <div data-dark data-testid="api-code-panel" className="mt-6 overflow-hidden rounded-2xl border border-white/10 bg-[#0F1627]">
                <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
                  <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto [scrollbar-width:none]">
                    {Object.entries(SNIPPETS).map(([k, v]) => (
                      <button key={k} type="button" data-testid={`api-tab-${k}`} onClick={() => setTab(k)} className={`shrink-0 rounded-full px-3 py-1.5 font-mono text-[11px] transition-colors duration-300 ${tab === k ? "bg-white/10 text-white" : "text-slate-400 hover:text-white"}`}>
                        {v.label}
                      </button>
                    ))}
                  </div>
                  <span className="hidden font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500 sm:inline" data-testid="api-illustrative-note">Illustrative data</span>
                  <button type="button" data-testid="api-copy-btn" onClick={copy} aria-label="Copy example" className="rounded-md p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"><Copy className="h-3.5 w-3.5" /></button>
                </div>
                <pre data-testid="api-code-block" className="overflow-x-auto px-5 py-5 font-mono text-[12.5px] leading-[1.75] sm:text-[13px]">
                  {SNIPPETS[tab].code.split("\n").map((line, i) => (
                    <div key={i} className="flex">
                      <span className="w-8 shrink-0 select-none pr-4 text-right text-slate-600">{i + 1}</span>
                      <code>{highlight(line)}</code>
                    </div>
                  ))}
                </pre>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
};
