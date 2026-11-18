import type { ReactNode } from 'react';
import { CARD_PAD, MUTED } from '../ui';

/** Titled card section used by Settings and other form-heavy pages. */
export default function CardSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className={CARD_PAD}>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-[#f5f5f5]">{title}</h2>
      {description && <p className={`mt-1 text-xs ${MUTED}`}>{description}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}
