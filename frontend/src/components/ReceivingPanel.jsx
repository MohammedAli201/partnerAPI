import { ArrowRight, Smartphone, Check } from "lucide-react";
import { Link } from "react-router-dom";
import { useBusiness, useLink } from "../business";
export function ReceivingPanel() {
 const {copy}=useBusiness(),link=useLink();
 return <aside className="receiving-panel" aria-labelledby="service-title"><h2 id="service-title" className="font-display font-semibold text-xl mt-4">{copy.panel_title}</h2><div className="service-field"><span>{copy.receiving_country}</span><strong>{copy.somalia}</strong></div><div className="service-field"><span>{copy.method}</span><strong className="flex gap-2 items-center"><Smartphone size={19}/>{copy.mobile_wallet}</strong><small>{copy.method_condition}</small></div><p className="mt-5 font-semibold text-sm">{copy.recipient_needs}</p><ul className="space-y-2 mt-3 text-sm text-ink-dim">{['req_name','req_phone','req_provider'].map(key=><li key={key} className="flex gap-2"><Check className="text-accent shrink-0" size={17}/>{copy[key]}</li>)}</ul><p className="text-xs text-ink-dim leading-relaxed my-5">{copy.panel_note}</p><Link to={link('/receive#checklist')} className="button-primary w-full justify-center">{copy.how_receive}<ArrowRight size={17}/></Link></aside>;
}
