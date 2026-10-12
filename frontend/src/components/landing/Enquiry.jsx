import { useState, useRef, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, CheckCircle2, ChevronDown, Loader2, Mail, HelpCircle, BookOpen } from "lucide-react";
import { toast } from "sonner";
import { ease, fadeUp, viewport } from "@/lib/motion";
import { COMPANY } from "@/content/site";

const API = "/api";
const VOLUMES = ["Under $10k / month", "$10k \u2013 $100k / month", "$100k \u2013 $1M / month", "Over $1M / month"];
const CHANNELS = ["EVC Plus", "ZAAD", "eDahab", "Bank transfer"];
const TYPES = ["Remittance / MTO", "Payment institution / EMI", "Fintech platform", "Bank", "Other"];
const field = "enquiry-field w-full border outline-none transition-colors";
const label = "enquiry-label block";

export const Enquiry = () => {
  const [sent, setSent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submission = useRef(null);
  const receipt = useCallback(node => { if(node){node.focus({preventScroll:true});node.scrollIntoView({block:"center",behavior:"auto"});} }, []);
  const [picked, setPicked] = useState(["EVC Plus"]);
  const [form, setForm] = useState({ full_name: "", work_email: "", company: "", business_type: TYPES[0], country: "", monthly_volume: "", message: "" });

  const set = (k) => (e) => { submission.current=null; setForm((f) => ({ ...f, [k]: e.target.value })); };
  const toggle = (c) => { submission.current=null; setPicked((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c])); };

  const submit = async (e) => {
    e.preventDefault();
    if(busy)return;
    if(!picked.length){setError("Select at least one channel.");return;}
    setError("");setBusy(true);
    try {
      submission.current ||= crypto.randomUUID();
      const csrf=document.cookie.split('; ').find(x=>x.startsWith('csrf_token='))?.slice(11);
      const response=await fetch(`${API}/enquiries`,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","Idempotency-Key":submission.current,...(csrf?{"X-CSRF-Token":decodeURIComponent(csrf)}:{})},body:JSON.stringify({...form,channels:picked})});
      const data=await response.json();
      if(!response.ok || data.received!==true || typeof data.reference!=="string")throw new Error(Array.isArray(data.detail)?data.detail[0]?.msg:data.detail||"Please try again or email us directly.");
      setSent({...data,full_name:form.full_name.trim(),work_email:form.work_email.trim()});
      toast.success("Enquiry received", { description: "Our partnerships team will reply by email." });
    } catch (err) {
      const detail=err.message||"Please try again or email us directly.";
      setError(detail);toast.error("Could not send enquiry",{description:detail});
    } finally {
      setBusy(false);
    }
  };

  return (
    <section id="enquiry" data-dark data-testid="enquiry-section" className="relative overflow-hidden bg-ink py-20 text-white sm:py-24 grain">
      <div className="pointer-events-none absolute left-1/2 top-0 h-px w-[80%] -translate-x-1/2 bg-gradient-to-r from-transparent via-teal-400/60 to-transparent" />
      <div className="pointer-events-none absolute -bottom-60 left-1/2 h-[600px] w-[900px] -translate-x-1/2 rounded-full bg-teal-600/15 blur-[160px]" />
      <div className="container-x relative enquiry-layout">
        <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={viewport} className="enquiry-intro">
          <p className="eyebrow text-teal-300">Partner with Hubaal</p>
          <h2 className="h2 mt-5 text-white">Let's work together.</h2>
          <p className="lead mt-6 text-slate-400">Tell us about your business and your Somalia payout needs. Our team will share availability, pricing and next steps.</p>
          <a href={`mailto:${COMPANY.email}`} data-testid="enquiry-email-link" className="mt-8 inline-flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-5 py-4 transition-colors hover:border-teal-400/50 hover:bg-white/10">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-500 text-white"><Mail className="h-4 w-4" /></span>
            <span>
              <span className="block font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400">Prefer email?</span>
              <span className="block text-[15px] font-medium text-white">{COMPANY.email}</span>
            </span>
          </a>
          <div className="enquiry-resources">
            <a href="/help"><HelpCircle size={22} aria-hidden="true" /><span>Partner support</span></a>
            <a href="/partners/integration"><BookOpen size={22} aria-hidden="true" /><span>Integration guide</span></a>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={viewport} transition={{ duration: 0.9, ease, delay: 0.1 }} className="enquiry-form-column">
          <div className="enquiry-panel">
            <AnimatePresence mode="wait">
              {sent ? (
                <motion.div key="done" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} data-testid="enquiry-success" role="status" ref={receipt} tabIndex={-1} className="flex min-h-[420px] flex-col items-start justify-center">
                  <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-500 text-white"><CheckCircle2 className="h-6 w-6" /></span>
                  <h3 className="mt-6 text-[28px] font-semibold tracking-[-0.03em]">Thank you, {sent.full_name.split(" ")[0]}.</h3>
                  <p className="mt-3 max-w-[440px] text-slate-400">Your enquiry has been recorded. We will reply to <span className="text-white">{sent.work_email}</span>.</p>
                  <p className="mt-2 font-mono text-[11px] text-slate-500" data-testid="enquiry-reference">Reference {sent.reference}</p>
                  <button type="button" data-testid="enquiry-reset-btn" onClick={() => {setSent(null);submission.current=null;}} className="mt-8 text-[14px] font-medium text-teal-300 underline-offset-4 hover:underline">Submit another enquiry</button>
                </motion.div>
              ) : (
                <motion.form key="form" exit={{ opacity: 0 }} onSubmit={submit} data-testid="enquiry-form" aria-busy={busy} className="enquiry-form">
                  <div className="enquiry-name-row">
                    <label className="block"><span className={label}>Full name</span><input required name="full_name" autoComplete="name" minLength={2} maxLength={100} disabled={busy} value={form.full_name} onChange={set("full_name")} data-testid="form-name-input" className={field} placeholder="Ayaan Mohamed" /></label>
                    <label className="block"><span className={label}>Work email</span><input required type="email" name="work_email" autoComplete="email" maxLength={254} disabled={busy} value={form.work_email} onChange={set("work_email")} data-testid="form-email-input" className={field} placeholder="you@company.com" /></label>
                  </div>
                  <label className="block"><span className={label}>Company</span><input required name="company" autoComplete="organization" minLength={2} maxLength={160} disabled={busy} value={form.company} onChange={set("company")} data-testid="form-company-input" className={field} placeholder="Company name" /></label>
                  <label className="block"><span className={label}>Business type</span>
                    <select name="business_type" disabled={busy} value={form.business_type} onChange={set("business_type")} data-testid="form-type-select" className={field}>
                      {TYPES.map((o) => <option key={o} className="text-ink">{o}</option>)}
                    </select>
                  </label>
                  <label className="block"><span className={label}>Operating country</span><input required name="country" autoComplete="country-name" minLength={2} maxLength={100} disabled={busy} value={form.country} onChange={set("country")} data-testid="form-country-input" className={field} placeholder="Country of operation"/></label>
                  <label className="block"><span className={label}>Expected monthly volume</span><select required name="monthly_volume" disabled={busy} value={form.monthly_volume} onChange={set("monthly_volume")} data-testid="form-volume-select" className={field}><option value="" disabled className="text-ink">Select a volume</option>{VOLUMES.map(v=><option key={v} className="text-ink">{v}</option>)}</select></label>
                  <fieldset className="enquiry-channel-fieldset" disabled={busy}>
                    <legend className={label}>Channels of interest</legend>
                    <div className="enquiry-channel-grid" data-testid="form-channels-checkboxes">
                      {CHANNELS.map((c) => {
                        const on = picked.includes(c);
                        return (
                          <label key={c} className="enquiry-channel-option" data-selected={on}>
                            <input type="checkbox" name="channels" value={c} checked={on} onChange={() => toggle(c)} data-testid={`form-channel-${c.toLowerCase().replace(/\s+/g, "-")}`} />
                            <span>{c}</span>
                          </label>
                        );
                      })}
                    </div>
                  </fieldset>
                  <details className="enquiry-message-details">
                    <summary>Add payout details (optional)<ChevronDown size={18} aria-hidden="true" /></summary>
                    <label className="block"><span className="sr-only">Your payout needs</span><textarea name="message" maxLength={4096} disabled={busy} rows={3} value={form.message} onChange={set("message")} data-testid="form-message-textarea" className={field} placeholder="Corridors, use case, timeline…" /></label>
                  </details>
                  {error && <p role="alert" data-testid="enquiry-error" className="text-sm text-red-300">{error}</p>}
                  <div className="enquiry-submit-row">
                    <p className="enquiry-privacy">Your details are used to reply. <a href="/privacy" className="underline underline-offset-4">Privacy policy</a></p>
                    <button type="submit" disabled={busy} data-testid="form-submit-btn" className="btn-primary !bg-teal-500 !text-white hover:!bg-teal-400 disabled:opacity-70">
                      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Send enquiry <ArrowRight className="h-4 w-4" />
                    </button>
                  </div>
                </motion.form>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
