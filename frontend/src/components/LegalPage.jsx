import { ArrowLeft } from "lucide-react";
import Logo from "./Logo";
import { useBusiness } from "../business";

const CONTENT = {
  privacy: {
    title: "Privacy Policy",
    sections: [
      {
        h: "What we collect",
        p: "When you submit a partnership enquiry through this website, we collect the details you provide in the form: your company name, operating country, contact person, business email address, expected monthly payout volume, and the delivery channels you require.",
      },
      {
        h: "How we use it",
        p: "We use enquiry details only to respond to your enquiry, discuss a potential payout partnership with you, and prepare onboarding information if you choose to proceed. We do not sell your data and we do not use it for advertising.",
      },
      {
        h: "Cookies",
        p: "This website uses cookies to support website security and partner sign-in.",
      },
      {
        h: "Enquiry data vs recipient data",
        p: "Information you provide through this website is website enquiry data. Data about individual recipients and individual transactions handled under an agreed payout service is processed separately, under the terms of the service agreement between Hubaal and the sending partner — not under this policy.",
      },
      {
        h: "Service providers and storage",
        p: "The website is hosted and the enquiry form is delivered using standard hosting and infrastructure providers. Enquiry submissions are stored in the website's database and are accessible to the Hubaal team responding to you.",
      },
      {
        h: "Retention",
        p: "We keep enquiry information only as long as necessary to handle your enquiry and any related partnership discussion.",
      },
      {
        h: "Questions",
        p: "Contact us with any privacy question, correction or deletion request.",
        contact: true,
      },
    ],
  },
  terms: {
    title: "Terms of Service",
    sections: [
      {
        h: "About these terms",
        p: "These terms apply to your use of this website and to partnership enquiries submitted through it.",
      },
      {
        h: "Partnership enquiries",
        p: "The enquiry form lets overseas remittance companies and payment businesses ask about Hubaal's Somalia payout delivery. Submitting an enquiry does not create a contract, an active payout partnership, or any obligation on either side.",
      },
      {
        h: "Commercial arrangements",
        p: "Payout services, pricing, prefunding, integration and service levels are agreed separately in a written agreement between Hubaal and the sending partner. Content on this website — including coverage channels and example payout data — is general information and is confirmed during onboarding, not an offer.",
      },
      {
        h: "No recipient transactions through this website",
        p: "This website does not process recipient payouts or personal transfers, and does not confirm exchange rates or fees for individual senders. Individuals who want to receive funds should contact the remittance company they use.",
      },
      {
        h: "Acceptable use",
        p: "Please don't submit false, misleading or third-party contact information through the enquiry form, and don't attempt to disrupt or probe the website.",
      },
      {
        h: "Contact",
        p: "Contact us with questions about these terms.",
        contact: true,
      },
    ],
  },
};

const LegalPage = ({ kind = "privacy" }) => {
  const { contact } = useBusiness();
  const page = CONTENT[kind] || CONTENT.privacy;
  return (
    <main id="main" tabIndex="-1" className="min-h-screen bg-void">
      <div className="max-w-2xl mx-auto px-5 py-16">
        <Logo />
        <h1 data-testid="legal-title" className="mt-12 font-extrabold text-[32px] sm:text-[40px] tracking-[-0.025em] leading-[1.2] text-ink-light">
          {page.title}
        </h1>
        <div className="mt-10 space-y-8">
          {page.sections.map((s) => (
            <div key={s.h}>
              <h2 className="text-xl font-semibold text-ink-light">{s.h}</h2>
              <p className="mt-2.5 text-base leading-[1.6] text-ink-dim">{s.p}</p>
              {s.contact && <a href={`mailto:${contact.email}`} className="mt-3 inline-block text-base text-gold underline underline-offset-4">{contact.email}</a>}
            </div>
          ))}
        </div>
        <a
          href="/"
          className="mt-12 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:text-gold-dark transition-colors"
        >
          <ArrowLeft size={15} /> Back to home
        </a>
      </div>
    </main>
  );
};

export default LegalPage;
