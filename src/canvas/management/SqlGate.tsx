import type { ReactNode } from 'react';
import { useCan } from '../useAdmin';

/** Çocukları yalnız «SQL'i göster ve kopyala» rolde varsa çizer. */
export default function SqlGate({ children }: { children: ReactNode }) {
  return useCan('kart.sql-goster') ? <>{children}</> : null;
}
