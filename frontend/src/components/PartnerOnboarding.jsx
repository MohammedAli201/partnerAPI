import Reveal from './Reveal';
import { useBusiness } from '../business';

export default function PartnerOnboarding() {
 const { copy } = useBusiness();
 return <section id="onboarding" className="py-20 sm:py-28 bg-surface border-y border-espresso/10">
  <div className="max-w-7xl mx-auto px-5 sm:px-8">
   <Reveal className="mb-14"><h2 className="font-display font-semibold tracking-tight leading-[1.1] text-3xl sm:text-4xl lg:text-5xl text-ink-light">{copy.onboarding_title}</h2></Reveal>
   <div className="grid md:grid-cols-3 gap-5">{[1,2,3].map(n => <Reveal key={n} className="h-full">
    <article className="h-full rounded-3xl bg-elevated border border-espresso/10 p-8 sm:p-10">
     <p className="font-display font-semibold text-5xl text-gold/70 tracking-tight">0{n}</p>
     <h3 className="mt-6 font-display font-semibold text-xl sm:text-2xl text-ink-light tracking-tight">{copy['onboard_'+n]}</h3>
     <p className="mt-3 text-base leading-relaxed text-ink-dim">{copy['onboard_'+n+'_text']}</p>
    </article>
   </Reveal>)}</div>
  </div>
 </section>;
}
