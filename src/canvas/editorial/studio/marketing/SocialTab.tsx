import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { AlertTriangle, Check, Download, ImagePlus, Trash2 } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { Img, press } from '../shared';
import { marketingApi, type MarketingView, type SocialEffect, type SocialTemplate, type SocialVisual } from './api';
import { Approval, Section, field, ghostBtn, gradientBtn, label } from './parts';

const VISUALS: [SocialVisual, string, string][] = [
  ['cover', 'Kapak', 'Ön kapak, başlık ve kitap adı'],
  ['page', 'İç sayfa', 'Seçili iç sayfa resmi zemin olur'],
  ['quote', 'Alıntı kartı', 'Kitaptan kısa alıntı, paletten zemin'],
];
const EFFECTS: Record<SocialEffect, string> = { plain: 'Düz', shadow: 'Gölge', outline: 'Dış çizgi', burst: 'Patlama', rainbow: 'Renkli harf' };
const ICON: Record<SocialTemplate, { width: number; height: number }> = { kare: { width: 24, height: 24 }, dikey: { width: 17, height: 30 }, yatay: { width: 32, height: 17 } };
const TEMPLATE_TEXT: Record<SocialTemplate, string> = { kare: 'Kare', dikey: 'Dikey (hikâye)', yatay: 'Yatay (bağlantı)' };

export default function SocialTab({ jobId, v, refresh }: { jobId: string; v: MarketingView; refresh: () => void }) {
  const s = v.social;
  const [template, setTemplate] = useState<SocialTemplate>('kare');
  const [visual, setVisual] = useState<SocialVisual>('cover');
  const [source, setSource] = useState<string | null>(null);
  const [headline, setHeadline] = useState('');
  const [effect, setEffect] = useState<SocialEffect>('plain');
  const [color, setColor] = useState<string | null>(null);
  const [quote, setQuote] = useState('');
  useEffect(() => { if (!color && s.palette.length) setColor(s.palette[0]); }, [s.palette, color]);

  const pickable = useMemo(() => s.sources.filter((x) => (visual === 'cover' ? x.kind === 'cover' : x.kind !== 'cover')), [s.sources, visual]);
  useEffect(() => {
    if (visual === 'quote') return;
    if (!source || !pickable.some((x) => x.key === source)) setSource(pickable[0]?.key ?? null);
  }, [visual, pickable, source]);
  const chosen = s.sources.find((x) => x.key === (visual === 'quote' ? 'kapak' : source));
  const draftSelected = !!chosen?.draft;

  const add = useMutation({
    mutationFn: () => marketingApi.addSocial(jobId, { template, visual, source: visual === 'quote' ? null : source, headline, effect, color, quote: visual === 'quote' ? quote : null }),
    onSuccess: refresh,
  });
  const approve = useMutation({ mutationFn: (x: { id: string; ok: boolean }) => marketingApi.approveSocial(jobId, x.id, x.ok), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => marketingApi.deleteSocial(jobId, id), onSuccess: refresh });
  const err = errText(add.error || approve.error || remove.error, '');
  const approvedCount = s.items.filter((x) => x.approved).length;
  const canMake = visual === 'quote' ? !!quote.trim() : !!source;

  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-3">
        <Section title="Yeni görsel">
          <div role="radiogroup" aria-label="Şablon" className="grid grid-cols-3 gap-2">
            {s.templates.map((t) => (
              <button key={t.key} type="button" role="radio" aria-checked={template === t.key} onClick={() => setTemplate(t.key)}
                className={`flex min-w-0 flex-col items-center gap-1.5 rounded-2xl border p-2 ${press} ${template === t.key ? 'border-canvas-violet bg-violet-50/60 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/70'}`}>
                <span className="flex h-10 items-center" aria-hidden>
                  <span className="block rounded-[3px] border-2 border-canvas-violet/70" style={ICON[t.key]} />
                </span>
                <span className="text-[12px] font-extrabold">{TEMPLATE_TEXT[t.key]}</span>
                <span className="font-mono text-[10.5px] text-canvas-muted">{t.w}×{t.h}</span>
              </button>
            ))}
          </div>
          <div role="radiogroup" aria-label="Görsel türü" className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
            {VISUALS.map(([k, t, help]) => (
              <button key={k} type="button" role="radio" aria-checked={visual === k} onClick={() => setVisual(k)}
                className={`rounded-2xl border p-2.5 text-left ${press} ${visual === k ? 'border-canvas-violet bg-violet-50/60 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/70'}`}>
                <span className="block text-[13px] font-extrabold">{t}</span>
                <span className="block text-[11px] leading-snug text-canvas-muted">{help}</span>
              </button>
            ))}
          </div>

          {visual !== 'quote' && (
            <div className="flex flex-col gap-1">
              <span className={label}>Görsel</span>
              {pickable.length === 0 ? (
                <p className="text-[12px] text-canvas-muted">{visual === 'cover' ? 'Kapak henüz dizilmedi.' : 'Seçilebilir iç sayfa resmi ya da fotoğraf yok.'}</p>
              ) : (
                <ul className="grid max-h-64 grid-cols-3 gap-2 overflow-y-auto pr-1 sm:grid-cols-4 lg:grid-cols-3">
                  {pickable.map((x) => (
                    <li key={x.key}>
                      <button type="button" onClick={() => setSource(x.key)} aria-pressed={source === x.key} title={x.label}
                        className={`relative block w-full overflow-hidden rounded-xl border ${press} ${source === x.key ? 'border-canvas-violet ring-2 ring-canvas-violet/30' : 'border-slate-200'}`}>
                        <Img src={marketingApi.sourceUrl(jobId, x.key, 200)} alt={x.label} fallback={x.label} className="aspect-square w-full bg-white object-cover" />
                        <span className="absolute inset-x-0 bottom-0 truncate bg-black/55 px-1 text-[10px] text-white">{x.label}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {visual === 'quote' ? (
            <div className="flex flex-col gap-1">
              <span className={label}>Alıntı · kitapta birebir geçmeli</span>
              <textarea className={field} rows={4} value={quote} onChange={(e) => setQuote(e.target.value)} maxLength={2000}
                placeholder="Kitaptan bir cümle; aşağıdaki önerilerden de seçebilirsiniz" />
              {v.quotes.length > 0 ? (
                <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto pr-1">
                  {v.quotes.map((q) => (
                    <li key={q}>
                      <button type="button" onClick={() => setQuote(q)}
                        className={`w-full rounded-xl border px-2.5 py-1.5 text-left text-[12px] leading-snug ${press} ${quote === q ? 'border-canvas-violet bg-violet-50/60' : 'border-slate-200 bg-white/70'}`}>
                        “{q}”
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[11.5px] text-canvas-muted">Alıntı önerileri, herhangi bir metin üretimi (arka kapak, ürün sayfası ya da kılavuz) kitabı okuyunca gelir.</p>
              )}
            </div>
          ) : (
            <>
              <label className="flex flex-col gap-1">
                <span className={label}>Başlık yazısı (isteğe bağlı)</span>
                <input className={field} value={headline} onChange={(e) => setHeadline(e.target.value)} maxLength={300} placeholder="Ör. Yeni kitabımız raflarda!" />
              </label>
              <div role="radiogroup" aria-label="Yazı efekti" className="flex flex-wrap gap-1.5">
                {s.effects.map((e) => (
                  <button key={e} type="button" role="radio" aria-checked={effect === e} onClick={() => setEffect(e)}
                    className={`rounded-full border px-3 py-1.5 text-[12px] font-bold ${press} ${effect === e ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/80'}`}>
                    {EFFECTS[e] ?? e}
                  </button>
                ))}
              </div>
            </>
          )}

          <div className="flex flex-col gap-1">
            <span className={label}>Zemin rengi · kitabın paletinden</span>
            <div role="radiogroup" aria-label="Zemin rengi" className="flex flex-wrap gap-2">
              {s.palette.map((c) => (
                <button key={c} type="button" role="radio" aria-checked={color === c} aria-label={c} title={c} onClick={() => setColor(c)}
                  className={`h-9 w-9 rounded-full border border-black/10 ${press} ${color === c ? 'ring-2 ring-canvas-violet ring-offset-2' : ''}`}
                  style={{ background: c }} />
              ))}
            </div>
          </div>

          {draftSelected && (
            <Note tone="warn">
              <span className="inline-flex items-start gap-1.5"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />{s.draft_note}: seçilen görsel Zeki AI ile çizildi.</span>
            </Note>
          )}
          {err && <Note tone="err">{err}</Note>}
          <button type="button" className={gradientBtn} disabled={!canMake || add.isPending} onClick={() => add.mutate()}>
            <ImagePlus className="h-4 w-4" aria-hidden />{add.isPending ? 'Diziliyor…' : 'Görseli diz'}
          </button>
        </Section>
      </div>

      <Section title={`Görseller (${s.items.length})`} aside={
        approvedCount > 0 ? <a className={ghostBtn} href={marketingApi.socialZipUrl(jobId)}><Download className="h-4 w-4" aria-hidden />Onaylıları indir ({approvedCount}, zip)</a> : null}>
        {s.items.length === 0 ? (
          <p className="text-[12.5px] text-canvas-muted">Henüz görsel yok. Soldan şablon ve görsel seçip dizin; her görsel onaylanınca indirilebilir.</p>
        ) : (
          <ul className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {s.items.map((it) => (
              <li key={it.id} className="flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-200 bg-white/80 p-2">
                <a href={marketingApi.socialUrl(jobId, it.id)} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-xl bg-slate-100">
                  <Img src={marketingApi.socialUrl(jobId, it.id, 520)} alt={`${TEMPLATE_TEXT[it.template]} ${VISUALS.find((x) => x[0] === it.visual)?.[1] ?? ''}`}
                    fallback="görsel" className="mx-auto max-h-72 w-auto object-contain" />
                </a>
                <div className="flex flex-wrap items-center justify-between gap-1.5">
                  <span className="text-[11.5px] font-bold">{TEMPLATE_TEXT[it.template]} · {VISUALS.find((x) => x[0] === it.visual)?.[1]}</span>
                  <Approval approved={it.approved} />
                </div>
                {it.draft && (
                  <p className="flex items-start gap-1 rounded-lg bg-amber-50 px-2 py-1 text-[11px] font-bold text-amber-800">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{s.draft_note}
                  </p>
                )}
                <div className="flex flex-wrap gap-1.5">
                  <button type="button" disabled={approve.isPending} onClick={() => approve.mutate({ id: it.id, ok: !it.approved })}
                    className={`inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl border-2 px-3 text-[12.5px] font-bold disabled:opacity-50 ${press} ${it.approved ? 'border-slate-200 bg-white text-canvas-muted' : 'border-emerald-500 bg-white text-emerald-700'}`}>
                    <Check className="h-4 w-4" aria-hidden />{it.approved ? 'Onayı geri al' : 'Onayla'}
                  </button>
                  {it.approved && <a className={ghostBtn} href={marketingApi.socialDownloadUrl(jobId, it.id)}><Download className="h-4 w-4" aria-hidden />İndir</a>}
                  <button type="button" className={ghostBtn} aria-label="Görseli sil" disabled={remove.isPending}
                    onClick={() => { if (window.confirm('Bu görsel silinsin mi?')) remove.mutate(it.id); }}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
