import { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, CheckCircle2, Loader2 } from "lucide-react";
import Reveal from "./Reveal";
import { partnershipChannelOptions } from "../channels";

const API = "/api";

const VOLUMES = ["Under $10k / month", "$10k – $100k / month", "$100k – $1M / month", "Over $1M / month"];
const CHANNELS = partnershipChannelOptions;

const inputCls =
  "w-full bg-white border border-line rounded-xl px-4 py-3.5 text-base text-ink-light placeholder:text-ink-muted outline-none focus:border-brass focus-visible:ring-2 focus-visible:ring-brass focus-visible:ring-offset-2 focus-visible:ring-offset-espresso transition-colors duration-300";

const Field = ({ label, children }) => (
  <label className="block">
    <span className="block text-[13px] font-semibold text-white/80 mb-2">{label}</span>
    {children}
  </label>
);

const INITIAL_FORM = {
  company_name: "",
  country: "",
  contact_name: "",
  email: "",
  monthly_volume: VOLUMES[1],
  channels: CHANNELS[0],
};

const PartnershipForm = () => {
  const [form, setForm] = useState(INITIAL_FORM);
  const [status, setStatus] = useState("idle");
  const [reference, setReference] = useState("");

  const submission = useRef(null);
  const showReceipt = useCallback((node) => {
    if (!node) return;
    node.focus({ preventScroll: true });
    node.scrollIntoView({ block: "center", behavior: "auto" });
  }, []);

  const set = (k) => (e) => { submission.current = null; setForm({ ...form, [k]: e.target.value }); };

  const submit = async (e) => {
    e.preventDefault();
    if (status === "loading") return;
    setStatus("loading");
    try {
      submission.current ||= crypto.randomUUID();
      const csrf = document.cookie.split('; ').find(value => value.startsWith('csrf_token='))?.slice('csrf_token='.length);
      const res = await fetch(`${API}/partnerships`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": submission.current, ...(csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {}) },
        credentials: "same-origin",
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok || data.received !== true || typeof data.reference !== "string") throw new Error(data.detail || "Failed");
      setReference(data.reference);
      setStatus("success");
    } catch {
      setStatus("error");
    }
  };

  return (
    <section id="partner-form" className="py-16 sm:py-24 bg-void">
      <div className="max-w-[1200px] mx-auto px-5 sm:px-8 grid lg:grid-cols-2 gap-12 items-center">
        <Reveal>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-gold mb-4">Partnership enquiry</p>
          <h2 className="font-bold tracking-[-0.01em] leading-[1.1] text-[1.75rem] sm:text-[2.375rem] lg:text-[2.75rem] text-ink-light max-w-md">
            Discuss your Somalia corridor
          </h2>
          <p className="mt-5 text-base sm:text-[17px] leading-[1.6] text-ink-dim max-w-md">
            Share your business details and receiving requirements. Our partnership
            team will review your enquiry.
          </p>
        </Reveal>

        <Reveal delay={0.12}>
          <div className="bg-espresso rounded-[24px] p-7 sm:p-9 ring-1 ring-white/10 shadow-[0_24px_60px_-24px_rgba(22,32,47,0.45)]">
            <AnimatePresence mode="wait">
              {status === "success" ? (
                <motion.div
                  key="success"
                  data-testid="partner-success-message" role="status" ref={showReceipt} tabIndex={-1}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-center py-10"
                >
                  <CheckCircle2 size={48} className="text-brass mx-auto" />
                  <h3 className="mt-5 text-2xl font-bold text-white">Enquiry received</h3>
                  <p className="mt-3 text-base text-white/70 max-w-xs mx-auto">
                    Reference <span className="font-mono text-sm text-brass">{reference}</span> —
                    your enquiry has been recorded for our partnership team.
                  </p>
                  <button
                    onClick={() => {
                      submission.current = null;
                      setReference("");
                      setForm(INITIAL_FORM);
                      setStatus("idle");
                    }}
                    data-testid="partner-new-enquiry-btn"
                    className="mt-7 text-sm font-semibold text-brass border border-brass/50 rounded-full px-6 py-2.5 hover:bg-white/5 transition-colors"
                  >
                    New enquiry
                  </button>
                </motion.div>
              ) : (
                <motion.form
                  key="form"
                  data-testid="partner-form-element"
                  aria-busy={status === "loading"}
                  onSubmit={submit}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="space-y-4"
                >
                  <div className="grid sm:grid-cols-2 gap-4">
                    <Field label="Company name">
                      <input
                        name="company_name" autoComplete="organization" disabled={status === "loading"}
                        required
                        data-testid="partner-input-company" minLength={2} maxLength={160}
                        value={form.company_name}
                        onChange={set("company_name")}
                        className={inputCls}
                        placeholder="Global Remit Ltd"
                      />
                    </Field>
                    <Field label="Operating country">
                      <input
                        name="country" autoComplete="country-name" disabled={status === "loading"}
                        required
                        data-testid="partner-input-country" minLength={2} maxLength={100}
                        value={form.country}
                        onChange={set("country")}
                        className={inputCls}
                        placeholder="United Kingdom"
                      />
                    </Field>
                  </div>
                  <div className="grid sm:grid-cols-2 gap-4">
                    <Field label="Contact person">
                      <input
                        name="contact_name" autoComplete="name" disabled={status === "loading"}
                        required
                        data-testid="partner-input-contact" minLength={2} maxLength={100}
                        value={form.contact_name}
                        onChange={set("contact_name")}
                        className={inputCls}
                        placeholder="Fatima Ali"
                      />
                    </Field>
                    <Field label="Business email">
                      <input
                        name="email" autoComplete="email" disabled={status === "loading"}
                        required
                        type="email"
                        data-testid="partner-input-email" minLength={5} maxLength={254}
                        value={form.email}
                        onChange={set("email")}
                        className={inputCls}
                        placeholder="partnerships@yourcompany.com"
                      />
                    </Field>
                  </div>
                  <div className="grid sm:grid-cols-2 gap-4">
                    <Field label="Expected monthly volume">
                      <select
                        name="monthly_volume" disabled={status === "loading"}
                        data-testid="partner-input-volume"
                        value={form.monthly_volume}
                        onChange={set("monthly_volume")}
                        className={inputCls + " cursor-pointer"}
                      >
                        {VOLUMES.map((v) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Required channels">
                      <select
                        name="channels" disabled={status === "loading"}
                        data-testid="partner-input-channels"
                        value={form.channels}
                        onChange={set("channels")}
                        className={inputCls + " cursor-pointer"}
                      >
                        {CHANNELS.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </Field>
                  </div>
                  {status === "error" && (
                    <p data-testid="partner-error-message" role="alert" className="text-sm text-red-300">
                      We couldn’t send your enquiry. Your details are still in the form.
                      Try again or email <a href="mailto:partners@hubaal.so" className="underline underline-offset-4">partners@hubaal.so</a>.
                    </p>
                  )}
                  <button
                    type="submit"
                    data-testid="partner-submit-btn"
                    disabled={status === "loading"}
                    className="w-full inline-flex items-center justify-center gap-2.5 bg-gold text-white font-semibold text-base px-7 py-4 rounded-full ring-1 ring-white/25 hover:bg-gold-glow transition-colors duration-300 disabled:opacity-60"
                  >
                    {status === "loading" ? (
                      <><Loader2 size={18} className="animate-spin" aria-hidden="true" /> Sending enquiry</>
                    ) : (
                      <>
                        Send enquiry <ArrowRight size={17} strokeWidth={2.5} aria-hidden="true" />
                      </>
                    )}
                  </button>
                  <p className="text-xs leading-[1.65] text-white/70">
                    We use these details to respond to your enquiry. <a href="/privacy" className="text-white underline underline-offset-4 hover:text-brass">Privacy Policy</a>
                  </p>
                </motion.form>
              )}
            </AnimatePresence>
          </div>
        </Reveal>
      </div>
    </section>
  );
};

export default PartnershipForm;
