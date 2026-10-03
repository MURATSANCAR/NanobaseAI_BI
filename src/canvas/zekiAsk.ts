import { useLocation } from 'react-router-dom';
import { NAV, matchActive } from '@/canvas/nav/navModel';

/**
 * ZEKİ'ye soru adresi (2026-09-30 kullanıcı kararı). Cevap her zaman Genel bakış'taki ZEKİ kartında açılır; soru bir
 * modül ekranından geliyorsa modül kimliği (`modul`, menü ana modülü) de taşınır ve köprü soruyu yalnız o modülün
 * konularıyla cevaplar (chat_topics.json `scopes`). Kampüs ve genel arama kutuları modülsüzdür: soru konusuna göre
 * ilgili modülün verisine gider.
 */
export function zekiAskHref(question: string, module?: string | null): string {
  const q = new URLSearchParams({ soru: question });
  if (module) q.set('modul', module);
  return `/genel-bakis?${q.toString()}`;
}

/** Adresin ait olduğu menü ana modülü; Kampüs ve menü dışı adreste null (kapsamsız, ana ZEKİ). */
export function moduleOfPath(pathname: string, search = ''): string | null {
  const id = matchActive(NAV, pathname, search)?.group.id;
  return id && id !== 'kampus' ? id : null;
}

/** Ekranın modülüne bağlı ZEKİ adresi: modül ekranındaki öneri soruları yalnız o modülde cevaplanır. */
export function useZekiAskHref(): (question: string) => string {
  const { pathname, search } = useLocation();
  const module = moduleOfPath(pathname, search);
  return (question) => zekiAskHref(question, module);
}

/** Modül kimliğinin ekrandaki adı («Pazarlama»); bilinmeyen kimlikte null. */
export function moduleLabel(module: string | null | undefined): string | null {
  return (module && NAV.find((g) => g.id === module)?.label) || null;
}
