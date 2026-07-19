import type { ReactNode } from 'react';
import EmptyState from '@/components/EmptyState';

type Props = {
  children?: ReactNode;
  ctaTo?: string;
};

export default function BiSchemaEmptyGate({ children, ctaTo = '/bi/sources' }: Props) {
  return (
    <div className="bi-schema-panel p-6 sm:p-8">
      <EmptyState
        emoji="🗂️"
        titleKey="empty.bi.schema.title"
        descriptionKey="empty.bi.schema.description"
        ctaLabelKey="empty.bi.schema.cta"
        ctaTo={ctaTo}
      >
        <p className="mt-2 text-sm text-slate-500">Henüz tarama yok — önce bağlantıyı test edip şemayı tarayın.</p>
        {children}
      </EmptyState>
    </div>
  );
}
