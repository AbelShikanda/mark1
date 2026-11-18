import type { ReactNode } from 'react';
import { MUTED } from '../ui';

/** Page title + optional description and trailing actions, one per page. */
export default function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-2 border-b border-slate-200 pb-3 dark:border-[#222]">
      <div>
        <h1 className="text-xl font-bold text-slate-900 dark:text-[#f5f5f5]">{title}</h1>
        {description && <p className={`mt-0.5 text-xs ${MUTED}`}>{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
