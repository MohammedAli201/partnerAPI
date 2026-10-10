import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { useBusiness, useLink } from '../business';
import { createLatestRequester } from '../api';
import { ReceivingPanel } from './Hero';
import Stats from './Stats';
import About from './About';
import { FAQS } from './Faq';
import Partners from './Partners';
import TransactForm from './TransactForm';
import PartnerOnboarding from './PartnerOnboarding';

export function FAQs({ searchable = false }) {
  const { copy, lang } = useBusiness(), link = useLink();
  const [term, setTerm] = useState('');
  const questions = lang === 'en' ? FAQS : [1,2,3,4,5,6].map(n => [copy[`faq_${n}_q`], copy[`faq_${n}_a`]]);
  const items = questions.filter(([question, answer]) => (question + answer).toLocaleLowerCase().includes(term.trim().toLocaleLowerCase()));
  return <div className="max-w-4xl"><p className="eyebrow mb-5">{lang === 'en' ? 'FAQ' : copy.faq_label}</p><h2 className="section-title">{lang === 'en' ? 'Partner questions' : copy.faq_title}</h2>
    {searchable && <div className="form-field mt-8"><label htmlFor="help-search">{copy.search_help}</label><input id="help-search" type="search" value={term} onChange={event => setTerm(event.target.value)} placeholder={copy.search_placeholder} /><p id="search-status" role="status" className="text-sm text-ink-dim mt-2">{copy.search_results}: {items.length}</p></div>}
    <div id="faq-list" className="mt-8">{items.map(([question, answer]) => <details key={question} className="faq-item"><summary>{question}<span aria-hidden="true">+</span></summary><p>{answer}</p></details>)}</div>
    {!items.length && <p id="no-results" className="mt-5 text-ink-dim">{copy.no_results} <Link to={link('/contact')} className="text-accent underline">{copy.contact}</Link></p>}
    <Link to={link(searchable ? '/contact' : '/help')} className="inline-flex items-center gap-3 text-accent min-h-11 mt-6">{searchable ? copy.contact : copy.all_help}<ArrowRight size={17}/></Link>
  </div>;
}

function Tracking() {
  const { copy, preview, portal_url } = useBusiness();
  const [scenario, setScenario] = useState('processing'), [data, setData] = useState(null), [failed, setFailed] = useState(false);
  const request = useMemo(() => createLatestRequester(), []);
  useEffect(() => {
    if (!preview) return;
    let active = true; setData(null); setFailed(false);
    request('/api/public/tracking/examples/' + scenario).then(result => {
      if (!active || !result) return;
      if (result.synthetic !== true || result.mode !== 'preview') throw Error();
      setData(result);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [request, scenario, preview]);
  return <div className="grid lg:grid-cols-2 gap-7"><article className="content-card"><h2 className="font-display text-xl">{copy.track_gate}</h2><p className="text-ink-dim mt-5 leading-relaxed">{copy.track_gate_text}</p>{portal_url && <a href={portal_url} className="button-primary mt-7">{copy.portal}<ArrowRight size={17}/></a>}</article>
    {preview && <article className="content-card tracking-panel"><span className="preview-tag">{copy.illustrative}</span><h2 className="font-display text-xl mt-5">{copy.track_sample}</h2><div className="form-field mt-6"><label htmlFor="scenario">{copy.sample_scenario}</label><select id="scenario" value={scenario} onChange={event => setScenario(event.target.value)}>{[['processing','status_processing'],['action','status_unknown'],['delivered','status_sent'],['failed','status_failed']].map(([value,key]) => <option key={value} value={value}>{copy[key]}</option>)}</select></div>
      <div id="tracking-status" role="status" aria-live="polite">{failed ? copy.tracking_unavailable : !data ? copy.tracking_loading : <><h3 className="tracking-title font-display text-xl mt-6">{copy['status_'+data.status.toLowerCase()]}</h3><p className="text-xs text-ink-dim mt-2">{data.reference}</p><ol className="status-timeline my-6">{data.steps.map(([status,time],i) => <li key={i} className="flex justify-between gap-5 py-3 border-b border-stroke text-sm"><span>{copy['status_'+status.toLowerCase()]}</span><time className="text-ink-dim">{time}</time></li>)}</ol><p className={'tracking-note rounded-xl border p-4 text-sm leading-relaxed '+(data.status==='UNKNOWN'?'action border-accent/40 text-accent':'border-stroke text-ink-dim')}>{copy['status_'+data.status.toLowerCase()+'_note']}</p></>}</div>
    </article>}
  </div>;
}

export function PublicPage({ path }) {
  const { copy, api_docs, policies, contact, lang } = useBusiness(), link = useLink();
  const page = path === '/partners/integration' ? 'integration' : path.slice(1);
  const titles = { receive:'receive_title', partners:'partners_page_title', about:'about_title', help:'help_page_title', contact:'contact_title', track:'track_title', integration:'integration_guide_title', privacy:'privacy', terms:'terms', complaints:'complaints' };
  const intros = { receive:'receive_intro', partners:'partners_page_intro', about:'about_intro', help:'help_page_intro', contact:'contact_intro', track:'track_intro', integration:'integration_security' };
  const policy = ['privacy','terms','complaints'].includes(page);
  const companyTitles = {about: 'About Hubaal', help: 'Partner support', contact: 'Contact partner operations'};
  const heading = lang === 'en' && companyTitles[page] ? companyTitles[page] : copy[titles[page]];
  const intro = page === 'about' ? null : lang === 'en' && page === 'help' ? 'Find answers about Hubaal’s service and partnership enquiries.' : lang === 'en' && page === 'contact' ? 'Speak with our Mogadishu team about your Somalia payout requirements.' : copy[intros[page] || 'policy_intro'];
  return <>
    <section className="section-shell page-hero"><h1 className="page-title">{heading}</h1>
      {intro && (intros[page] || (policy && !policies[page]?.length)) && <p className="mt-6 text-base text-ink-dim leading-relaxed max-w-3xl">{intro}</p>}
      {page === 'partners' && <div className="flex flex-wrap gap-4 mt-8"><Link to={link('/partners#enquiry')} className="button-primary">{copy.discuss}<ArrowRight size={17}/></Link><Link to={link('/partners/integration')} className="button-secondary">{copy.api_docs}</Link></div>}
    </section>
    {page === 'receive' && <><section className="section-shell pt-0 grid lg:grid-cols-2 gap-12"><div><h2 className="section-title">{copy.wallet_title}</h2><p className="mt-5 text-ink-dim leading-relaxed">{copy.wallet_text}</p><p className="mt-5 text-ink-dim">{copy.receiving_availability}</p><Link to={link('/receive#checklist')} className="button-secondary mt-7">{copy.view_checklist}</Link></div><ReceivingPanel/></section><section id="checklist" className="section-shell"><h2 className="section-title">{copy.checklist_heading}</h2><div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-8 mt-10">{['name','number','cost','reference'].map((key,i) => <article key={key}><span className="text-accent font-mono text-sm">0{i+1}</span><h3 className="font-display text-xl mt-4">{copy['check_'+key]}</h3><p className="text-ink-dim mt-3 leading-relaxed">{copy['check_'+key+'_text']}</p></article>)}</div><p className="text-accent mt-8">{copy.never_pin}</p></section><Stats/></>}
    {page === 'partners' && <><section className="section-shell pt-0 grid lg:grid-cols-2 gap-12"><div><h2 className="section-title">{copy.coverage_title}</h2><p className="mt-5 text-ink-dim leading-relaxed">{copy.coverage_text}</p><span className="preview-tag mt-6">{copy.somalia}</span></div><div><h2 className="font-display text-xl">{copy.summary_title}</h2><dl className="mt-6">{['currency','methods','recipient','delivery','reporting','support'].map(key => <div className="grid grid-cols-[1fr_1.5fr] gap-5 border-t border-stroke py-4 text-sm" key={key}><dt className="text-ink-dim">{copy['summary_'+key]}</dt><dd>{copy['summary_'+key+'_value']}</dd></div>)}</dl></div></section><PartnerOnboarding/><Partners/><TransactForm/></>}
    {page === 'about' && <About/>}
    {page === 'help' && <section className="section-shell pt-0"><FAQs searchable/></section>}
    {page === 'contact' && <section className="section-shell pt-0 grid md:grid-cols-2 gap-6">
      <article className="content-card"><h2 className="text-xl font-bold">Partnership enquiries</h2><p className="mt-4 text-ink-dim leading-relaxed">Discuss your receiving methods, expected volumes and integration requirements.</p><a href="mailto:partners@hubaal.so" className="inline-block mt-5 text-accent underline underline-offset-4">partners@hubaal.so</a><div><Link to={link('/#partner-form')} className="button-primary mt-6">{copy.discuss}<ArrowRight size={17} aria-hidden="true"/></Link></div></article>
      <article className="content-card"><h2 className="text-xl font-bold">Company contact</h2><p className="mt-4 text-ink-dim">{contact.address}</p><a href={'mailto:'+contact.email} className="inline-block mt-5 text-accent underline underline-offset-4">{contact.email}</a>{contact.hours && <p className="mt-4 text-ink-dim">{contact.hours} · {contact.timezone}</p>}<div><Link to={link('/help')} className="button-secondary mt-6">Partner questions</Link></div></article>
    </section>}
    {page === 'track' && <section className="section-shell pt-0"><Tracking/></section>}
    {page === 'integration' && <section className="section-shell pt-0 max-w-4xl">{api_docs && <a href={api_docs} className="button-primary">{copy.api_reference}<ArrowRight size={17}/></a>}<div className="my-8 space-y-6">{[['POST /payouts-create',copy.partner_cap_1],['GET /payouts/{payout_id}',copy.delivery_title],[copy.callbacks_label,copy.partner_cap_2]].map(([route,label]) => <div key={route} className="content-card"><code className="text-accent break-words">{route}</code><p className="mt-3 text-ink-dim">{label}</p></div>)}</div><p className="text-ink-dim leading-relaxed">{copy.partner_cap_note}</p><Link to={link('/#partner-form')} className="button-secondary mt-6">{copy.discuss}</Link></section>}
    {policy && <section className="section-shell pt-0 max-w-4xl">{policies[page]?.length ? policies[page].map((paragraph,i) => <p className="text-ink-dim leading-relaxed my-5" key={i}>{paragraph}</p>) : [1,2].map(n => <article key={n} className="mb-8"><h2 className="font-display text-xl">{copy[`${page}_outline_${n}`]}</h2><p className="text-ink-dim mt-5 leading-relaxed">{copy[`${page}_outline_${n}_text`]}</p></article>)}<Link to={link('/contact')} className="button-secondary">{copy.contact}</Link></section>}
  </>;
}
