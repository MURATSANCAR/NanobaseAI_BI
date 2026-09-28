/** Rehber metni ve tarih biçimleri: kabuktaki «Nasıl kullanılır» bağlantısı da kullandığı için ağır bağımlılığı yok. */

type Block = { kind: 'h'; text: string } | { kind: 'p'; text: string } | { kind: 'ol'; items: string[] } | { kind: 'ul'; items: string[] };

/** Rehber metnini bloklara ayırır: «## başlık», numaralı ve madde listeleri, paragraflar. */
export function parseGuide(body: string): Block[] {
  const out: Block[] = [];
  for (const raw of body.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    const ol = /^\d+[.)]\s+(.*)$/.exec(line);
    const ul = /^[-*•]\s+(.*)$/.exec(line);
    const h = /^#{1,4}\s+(.*)$/.exec(line);
    const plain = (t: string) => t.replace(/\*\*/g, '');
    if (ol || ul) {
      const kind = ol ? 'ol' : 'ul';
      const text = plain((ol ?? ul)![1]);
      const last = out[out.length - 1];
      if (last && (last.kind === 'ol' || last.kind === 'ul') && last.kind === kind) last.items.push(text);
      else out.push({ kind, items: [text] });
    } else if (h) out.push({ kind: 'h', text: plain(h[1]) });
    else out.push({ kind: 'p', text: plain(line) });
  }
  return out;
}

/** Rehber metni. HTML yorumlanmaz; yalnız düz metin blokları. */
export function GuideText({ body }: { body: string }) {
  return (
    <div className="flex flex-col gap-2 text-[13px] leading-relaxed">
      {parseGuide(body).map((b, i) =>
        b.kind === 'h' ? (
          <h3 key={i} className="mt-1 text-[13.5px] font-extrabold">{b.text}</h3>
        ) : b.kind === 'p' ? (
          <p key={i}>{b.text}</p>
        ) : b.kind === 'ol' ? (
          <ol key={i} className="flex list-decimal flex-col gap-1 pl-5">{b.items.map((t, j) => <li key={j}>{t}</li>)}</ol>
        ) : (
          <ul key={i} className="flex list-disc flex-col gap-1 pl-5">{b.items.map((t, j) => <li key={j}>{t}</li>)}</ul>
        ),
      )}
    </div>
  );
}

const dtf = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: 'numeric', month: 'short', year: 'numeric' });
const dttf = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
/** YYYY-AA-GG (gün) ya da ISO zaman. Gün değeri saat dilimiyle kaydırılmaz. */
export const fmtDay = (v: string | null | undefined) => {
  if (!v) return '—';
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) {
    const [y, m, d] = v.split('-').map(Number);
    return new Intl.DateTimeFormat('tr-TR', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(Date.UTC(y, m - 1, d)));
  }
  return dtf.format(new Date(v));
};
export const fmtWhen = (v: string | null | undefined) => (v ? dttf.format(new Date(v)) : '—');
