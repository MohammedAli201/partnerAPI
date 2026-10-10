const SectionHeader = ({ eyebrow, title, copy, copyTestid, linkLabel, linkHref, testid }) => (
  <div
    data-testid={testid}
    className="grid lg:grid-cols-12 gap-6 lg:gap-12 lg:items-end mb-12 sm:mb-16"
  >
    <div className="lg:col-span-7">
      <p className="inline-block text-xs font-bold uppercase tracking-[0.18em] text-gold border-b-2 border-gold/30 pb-1.5 mb-4">{eyebrow}</p>
      <h2 className="font-bold tracking-[-0.01em] leading-[1.12] text-[1.75rem] sm:text-[2.375rem] text-ink-light max-w-xl text-balance">
        {title}
      </h2>
    </div>
    {(copy || linkLabel) && (
      <div className="lg:col-span-5 lg:max-w-sm lg:justify-self-end">
        {copy && (
          <p data-testid={copyTestid} className="text-base leading-[1.6] text-ink-dim">
            {copy}
          </p>
        )}
        {linkLabel && (
          <a
            href={linkHref}
            data-testid={testid ? `${testid}-link` : undefined}
            className="mt-4 inline-block text-[13px] font-bold uppercase tracking-[0.14em] text-ink-light border-b-2 border-gold pb-1 hover:text-gold transition-colors duration-300"
          >
            {linkLabel}
          </a>
        )}
      </div>
    )}
  </div>
);

export default SectionHeader;
