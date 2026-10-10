import {useBusiness} from '../business';
export default function Ticker(){const {copy,preview}=useBusiness();return <div className="border-y border-stroke bg-surface px-5 py-4 text-center text-sm text-ink-dim" data-testid="editorial-marquee-ticker">{preview?copy.illustrative:copy.receiving_label} &middot; {copy.method_condition}</div>;}
