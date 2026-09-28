/**
 * Sorgu bilgisi: köprünün `kaynaklar` sözleşmesi (backend/semantic_bridge/provenance.py) ve saf yardımcılar.
 * Bileşen `SqlInfo.tsx`; yayılım kılavuzu `docs/analiz/sorgu-bilgisi-kilavuz.md`.
 */

export type KaynakSorgu = {
  id: string;
  connection: 'logo' | 'crm' | 'portal';
  connectionLabel: string;
  database: string | null;
  title: string;
  description: string;
  /** Çalışan metnin tamamı, değerler yerine konmuş; kopyala-çalıştır. */
  sql: string;
  stats: { rows: number | null; dbMs: number | null; ranAt: string | null } | null;
  dataEnd: string | null;
  period: string | null;
  /** Portal tablosu okumasıysa tabloyu dolduran asıl sorgular. */
  origin: string[];
};

export type KaynakHesap = {
  name: string;
  text: string;
  inputs: string[];
  /** Rakam veritabanı sorgusundan gelmiyorsa kaynağın işlev adı (anlık okunan kutu, yüklenen dosya, dış servis). */
  external?: string | null;
};

export type Kaynaklar = {
  sources: Record<string, KaynakSorgu>;
  formulas: Record<string, KaynakHesap>;
  fields: Record<string, string>;
  dataEnd?: string | null;
  asOf?: string | null;
  /** Kayıt kurulamadıysa: rakamlar etkilenmez, pencere nedenini yazar. */
  error?: string;
};

/** Yolu bir adım kısaltır: `a.b[].c` → `a.b[]` → `a.b` → `a` → null. */
export function parentPath(path: string): string | null {
  if (path.endsWith('[]')) return path.slice(0, -2) || null;
  const dot = path.lastIndexOf('.');
  if (dot > 0) return path.slice(0, dot);
  return null;
}

/** Alanın kaynağı: önce satıra özel anahtar (`alan:row`), sonra alan, sonra yolu yukarı doğru kısaltarak. */
export function resolveRef(k: Kaynaklar | null | undefined, alan: string, row?: string | number | null): string | null {
  if (!k?.fields) return null;
  let path: string | null = alan;
  while (path) {
    if (row != null && row !== '') {
      const own = k.fields[`${path}:${row}`];
      if (own) return own;
    }
    const ref = k.fields[path];
    if (ref) return ref;
    path = parentPath(path);
  }
  return null;
}

export type Collected = {
  formulas: KaynakHesap[];
  sources: Array<KaynakSorgu & { isOrigin: boolean }>;
};

/** Bir kaynağın bütün zinciri: hesap → girdileri → sorgular → tabloyu dolduran sorgular (tekrarsız, sırayla). */
export function collect(k: Kaynaklar | null | undefined, ref: string | null): Collected {
  const out: Collected = { formulas: [], sources: [] };
  if (!k || !ref) return out;
  const seen = new Set<string>();
  const visit = (r: string, asOrigin: boolean) => {
    if (seen.has(r)) return;
    seen.add(r);
    if (r.startsWith('hesap:')) {
      const f = k.formulas?.[r.slice(6)];
      if (!f) return;
      out.formulas.push(f);
      f.inputs.forEach((i) => visit(i, false));
      return;
    }
    const s = k.sources?.[r];
    if (!s) return;
    out.sources.push({ ...s, isOrigin: asOrigin });
    (s.origin ?? []).forEach((o) => visit(o, true));
  };
  visit(ref, false);
  return out;
}

/** «Hepsini kopyala» metni: her sorgunun başında adı ve bağlantısı açıklama satırı olarak. */
export function allSqlText(sources: KaynakSorgu[]): string {
  return sources
    .filter((s) => s.sql)
    .map((s) => `-- ${s.title} · ${s.connectionLabel}${s.database ? ` · ${s.database}` : ''}\n${s.sql.trim()}`)
    .join('\n\n');
}

type ClipboardEnv = {
  clipboard?: { writeText: (t: string) => Promise<void> } | null;
  secure?: boolean;
  doc?: Pick<Document, 'createElement' | 'execCommand'> & { body: Pick<HTMLElement, 'appendChild' | 'removeChild'> } | null;
};

/**
 * Panoya kopyalama. Pano API'si yalnız güvenli bağlamda (https/localhost) var; müşteri VM'i http üzerinden açılır,
 * orada gizli bir metin alanı seçilip eski kopyala komutu kullanılır. Kopyalanan metin gösterilenle değil sorgunun
 * kendisiyle aynıdır. `env` yalnız testte verilir.
 */
export async function copyText(text: string, env?: ClipboardEnv): Promise<boolean> {
  const clip = env ? env.clipboard : typeof navigator !== 'undefined' ? navigator.clipboard : null;
  const secure = env ? env.secure : typeof window !== 'undefined' && window.isSecureContext;
  try {
    if (clip && secure) {
      await clip.writeText(text);
      return true;
    }
  } catch {
    /* aşağıdaki yola düş */
  }
  const doc = env ? env.doc : typeof document !== 'undefined' ? document : null;
  if (!doc) return false;
  const ta = doc.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.top = '-1000px';
  ta.style.opacity = '0';
  doc.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = doc.execCommand('copy');
  } catch {
    ok = false;
  }
  doc.body.removeChild(ta);
  return ok;
}

export function fmtMs(ms: number | null | undefined): string | null {
  if (ms == null) return null;
  return ms < 1000 ? `${ms.toLocaleString('tr-TR')} ms` : `${(ms / 1000).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} sn`;
}

export function fmtWhen(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return iso.length <= 10
    ? d.toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })
    : d.toLocaleString('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
