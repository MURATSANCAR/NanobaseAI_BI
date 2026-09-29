import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check as CheckIcon, Download, History, ImagePlus, Lightbulb, Pencil, Undo2, X } from 'lucide-react';
import { Note, btnGhost, btnPrimary, errText, field, label } from '../../admin/ui';
import { Img } from '../../editorial/studio/shared';
import { EmptyHint } from '../../components/Explain';
import { creativeApi, type Asset, type Meta, type RequestDetail, type VisualSetting } from './api';
import { ApprovalLine, Block, JobBar, chip, smallBtn } from './parts';
import { invalidateCreative } from './useMeta';
import { AskSheet } from '../../budget/parts';

/** Orta sütun: görsel varyantlar. Bir varyant = aynı dizim ayarı (kapak/iç sayfa/alıntı, başlık, renk, efekt) bütün
 *  biçimlerde. «Düzenle» ayarı değiştirip varyantın bütün biçimlerini yeni sürümle yeniden dizer (tek tasarım → her boyut). */

const VISUAL: Record<string, string> = { cover: 'Kapak', page: 'İç sayfa', quote: 'Alıntı kartı' };
const EFFECTS: Record<string, string> = { plain: 'Düz', shadow: 'Gölge', outline: 'Dış çizgi', burst: 'Patlama', rainbow: 'Renkli harf' };
const VISUAL_HELP: Record<string, string> = {
  cover: 'Kitabın kapağı, üstünde isteğe bağlı yazı.',
  page: 'Kitabın iç sayfasından bir resim; yalnız stüdyoda hazırlanmış kitaplarda vardır.',
  quote: 'Kitaptan bir cümle, renkli zemin üstünde.',
};
const hint = 'text-[11px] font-medium leading-snug text-canvas-muted';

function EditVariant({ a, palette, sources, quotes, onDone }: {
  a: Asset; palette: string[]; sources: Array<{ key: string; label: string; kind: string }>; quotes: string[]; onDone: () => void;
}) {
  const qc = useQueryClient();
  const s: VisualSetting = a.ayar ?? { visual: 'cover' };
  const [v, setV] = useState<VisualSetting>({ ...s });
  const run = useMutation({
    mutationFn: () => creativeApi.reviseVisual(a.id, { ...v, tumFormatlar: true }),
    onSuccess: (r) => { toast.success(`${r.hedef} biçim yeni ayarla yeniden hazırlanıyor; bitince yeni sürüm olarak görünür.`); onDone(); return invalidateCreative(qc); },
  });
  const pickable = sources.filter((x) => (v.visual === 'cover' ? x.kind === 'cover' : v.visual === 'page' ? x.kind !== 'cover' : false));
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-canvas-violet/30 bg-violet-50/40 p-2.5">
      <p className={hint}>Bu varyantın ayarını değiştirin; varyanttaki bütün biçimler aynı ayarla yeniden hazırlanır. Her biçim yeni bir sürüm olur; eski sürüm geçmişte kalır.</p>
      <span className={label}>Görsel türü</span>
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Görsel türü">
        {Object.entries(VISUAL).map(([k, t]) => (
          <button key={k} type="button" role="radio" aria-checked={v.visual === k} className={chip(v.visual === k)}
            onClick={() => setV((o) => ({ ...o, visual: k as VisualSetting['visual'], source: k === 'cover' ? 'kapak' : undefined }))}>{t}</button>
        ))}
      </div>
      <span className={hint}>{VISUAL_HELP[v.visual] ?? ''}</span>
      {v.visual === 'page' && (
        <label className="flex flex-col gap-1"><span className={label}>İç sayfa görseli</span>
          <select className={field} value={v.source ?? ''} onChange={(e) => setV((o) => ({ ...o, source: e.target.value }))}>
            <option value="">İç sayfa resmi seçin</option>
            {pickable.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
          </select>
          {pickable.length === 0 && <span className={hint}>Bu kitapta seçilecek iç sayfa resmi yok; iç sayfa resimleri yalnız Kitap Tasarım Stüdyosu'nda hazırlanan kitaplarda gelir. «Kapak» ya da «Alıntı kartı»nı deneyin.</span>}
        </label>
      )}
      {v.visual === 'quote' ? (
        <label className="flex flex-col gap-1"><span className={label}>Alıntı *</span>
          <textarea className={field} rows={3} value={v.quote ?? ''} onChange={(e) => setV((o) => ({ ...o, quote: e.target.value }))} maxLength={2000} placeholder="Ör. kitaptan kısa, etkileyici bir cümle; aşağıdaki listeden seçebilirsiniz" />
          <span className={hint}>Kitapta birebir geçen cümle olmalı; kitapta bulunmayan alıntı sorunlu işaretlenir ve mesaj onayı verilemez.</span>
          {quotes.length > 0 && (
            <ul className="flex max-h-36 flex-col gap-1 overflow-y-auto pr-1">
              {quotes.map((q) => (
                <li key={q}><button type="button" onClick={() => setV((o) => ({ ...o, quote: q }))}
                  className={`w-full rounded-lg border px-2 py-1 text-left text-[11.5px] leading-snug transition-transform duration-150 ease-out active:scale-[0.98] ${v.quote === q ? 'border-canvas-violet bg-white' : 'border-slate-200 bg-white/70'}`}>“{q}”</button></li>
              ))}
            </ul>
          )}
        </label>
      ) : (
        <>
          <label className="flex flex-col gap-1"><span className={label}>Görsel üstü yazı</span>
            <input className={field} value={v.headline ?? ''} onChange={(e) => setV((o) => ({ ...o, headline: e.target.value }))} maxLength={300} placeholder="Ör. Yeni baskısı raflarda (boş bırakılabilir)" /></label>
          <span className={label}>Yazı efekti</span>
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Yazı efekti">
            {Object.entries(EFFECTS).map(([k, t]) => (
              <button key={k} type="button" role="radio" aria-checked={(v.effect ?? 'plain') === k} className={chip((v.effect ?? 'plain') === k)}
                onClick={() => setV((o) => ({ ...o, effect: k }))}>{t}</button>
            ))}
          </div>
        </>
      )}
      {palette.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className={label}>Zemin rengi</span>
          <div role="radiogroup" aria-label="Zemin rengi" className="flex flex-wrap gap-2">
            {palette.map((c) => (
              <button key={c} type="button" role="radio" aria-checked={v.color === c} aria-label={c} title={c} onClick={() => setV((o) => ({ ...o, color: c }))}
                className={`h-9 w-9 rounded-full border border-black/10 transition-transform duration-150 ease-out active:scale-[0.95] ${v.color === c ? 'ring-2 ring-canvas-violet ring-offset-2' : ''}`}
                style={{ background: c }} />
            ))}
          </div>
        </div>
      )}
      {run.error && <Note tone="err">{errText(run.error, 'Görseller yeniden hazırlanamadı. Biraz sonra yeniden deneyin.')}</Note>}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className={btnGhost} onClick={onDone}>Vazgeç</button>
        <button type="button" className={btnPrimary} disabled={run.isPending || (v.visual === 'page' && !v.source) || (v.visual === 'quote' && !v.quote?.trim())}
          onClick={() => run.mutate()}>Bütün biçimleri bu ayarla yeniden hazırla</button>
      </div>
    </div>
  );
}

export function AssetActions({ a, meta, onVersions }: { a: Asset; meta: Meta | undefined; onVersions: (a: Asset) => void }) {
  const qc = useQueryClient();
  const me = meta?.me;
  const done = () => invalidateCreative(qc);
  const fail = (e: unknown) => toast.error(errText(e, 'İşlem yapılamadı. Sayfayı yenileyip yeniden deneyin.') ?? 'İşlem yapılamadı.');
  const approve = useMutation({ mutationFn: (s: 'tasarim' | 'mesaj') => creativeApi.approve(a.id, s), onSuccess: done, onError: fail });
  const withdraw = useMutation({ mutationFn: (s: 'tasarim' | 'mesaj') => creativeApi.withdraw(a.id, s), onSuccess: done, onError: fail });
  const reject = useMutation({ mutationFn: (n: string) => creativeApi.reject(a.id, n), onSuccess: done, onError: fail });
  const busy = approve.isPending || withdraw.isPending || reject.isPending;
  const [rejecting, setRejecting] = useState(false);
  const mine = (x: { by: string } | null) => !!x && !!me && (me.admin || x.by.toLowerCase() === me.username.toLowerCase());
  const hatali = a.dogrulama?.durum === 'hata';
  return (
    <div className="flex flex-wrap gap-1.5">
      {!a.red && a.tur === 'gorsel' && !a.tasarimOnay && me?.tasarimOnay && (
        <button type="button" className={smallBtn('ok')} disabled={busy} onClick={() => approve.mutate('tasarim')}><CheckIcon className="h-4 w-4" aria-hidden />Tasarım onayı</button>
      )}
      {!a.red && !a.mesajOnay && (a.tur === 'metin' || a.tasarimOnay) && me?.mesajOnay && (
        <button type="button" className={smallBtn('ok')} disabled={busy || hatali} title={hatali ? 'Önce sınır/alıntı sorununu düzeltin' : undefined}
          onClick={() => approve.mutate('mesaj')}><CheckIcon className="h-4 w-4" aria-hidden />Mesaj onayı</button>
      )}
      {a.mesajOnay && mine(a.mesajOnay) && (
        <button type="button" className={smallBtn()} disabled={busy} onClick={() => withdraw.mutate('mesaj')}><Undo2 className="h-4 w-4" aria-hidden />Mesaj onayını geri al</button>
      )}
      {a.tasarimOnay && !a.mesajOnay && mine(a.tasarimOnay) && (
        <button type="button" className={smallBtn()} disabled={busy} onClick={() => withdraw.mutate('tasarim')}><Undo2 className="h-4 w-4" aria-hidden />Tasarım onayını geri al</button>
      )}
      {!a.red && (me?.tasarimOnay || me?.mesajOnay) && (
        <button type="button" className={smallBtn('err')} disabled={busy} onClick={() => setRejecting(true)}><X className="h-4 w-4" aria-hidden />Reddet</button>
      )}
      {a.onayli && <a className={smallBtn()} href={creativeApi.downloadUrl(a.id)}><Download className="h-4 w-4" aria-hidden />İndir</a>}
      {a.surum > 1 && <button type="button" className={smallBtn()} onClick={() => onVersions(a)}><History className="h-4 w-4" aria-hidden />v{a.surum}</button>}
      <AskSheet open={rejecting} title={a.tur === 'gorsel' ? 'Görseli reddet' : 'Metni reddet'}
        message="Ret nedenini yazın; talebi açan kişi bu notu görür. Neden yazılmadan reddedilmez."
        input="Ret nedeni *" required confirm="Reddet" danger busy={reject.isPending}
        onClose={() => setRejecting(false)}
        onConfirm={(n) => reject.mutate(n, { onSuccess: () => setRejecting(false) })} />
    </div>
  );
}

export default function VisualPanel({ r, meta, onVersions }: { r: RequestDetail; meta: Meta | undefined; onVersions: (a: Asset) => void }) {
  const qc = useQueryClient();
  const me = meta?.me;
  const visuals = r.varliklar.filter((a) => a.tur === 'gorsel');
  const job = r.isler.find((j) => j.tur === 'gorsel');
  const lastDone = r.isler.find((j) => j.tur === 'gorsel' && j.sonuc?.palet);
  const [formats, setFormats] = useState<string[]>(r.formatlar);
  const reqFormats = r.formatlar.join(',');
  // Talebin biçimleri değişince seçim ona döner; yoklama sırasında gelen aynı liste seçimi sıfırlamaz.
  useEffect(() => setFormats(reqFormats ? reqFormats.split(',') : []), [reqFormats]);
  const [editing, setEditing] = useState<string | null>(null);
  const [heads, setHeads] = useState<string[]>([]);
  const groups = useMemo(() => {
    const m = new Map<string, Asset[]>();
    for (const a of visuals) m.set(a.varyant, [...(m.get(a.varyant) ?? []), a]);
    return [...m.entries()].sort(([x], [y]) => x.localeCompare(y));
  }, [visuals]);

  const produce = useMutation({
    mutationFn: () => creativeApi.produce(r.id, { formatlar: formats }),
    onSuccess: () => { toast.success('Görseller hazırlanıyor; bitince aşağıda varyant olarak görünür.'); return invalidateCreative(qc); },
  });
  const suggest = useMutation({ mutationFn: () => creativeApi.headlines(r.id), onSuccess: (x) => setHeads(x.items.map((i) => i.metin)) });
  const setHeadline = useMutation({
    mutationFn: (h: string) => creativeApi.update(r.id, { gorselBasligi: h }),
    onSuccess: () => { toast.success('Görsel üstü yazı kaydedildi; sonraki dizimde A varyantında kullanılır.'); return invalidateCreative(qc); },
  });
  const approveAll = useMutation({
    mutationFn: async (items: Asset[]) => { for (const a of items) await creativeApi.approve(a.id, 'tasarim'); },
    onSuccess: () => invalidateCreative(qc),
    onError: (e) => { toast.error(errText(e, 'Onay verilemedi.') ?? ''); return invalidateCreative(qc); },
  });
  const running = job?.durum === 'suruyor';
  const allFormats = meta?.formatlar ?? [];

  return (
    <Block title={`Görseller (${visuals.length})`} aside={
      me?.uret ? (
        <button type="button" className={btnPrimary} disabled={running || produce.isPending || formats.length === 0} onClick={() => produce.mutate()}>
          <ImagePlus className="h-4 w-4" aria-hidden />{visuals.length ? 'Yeni varyantları hazırla' : 'Görselleri hazırla'}
        </button>
      ) : null}>
      {me?.uret && (
        <div className="flex flex-col gap-1.5">
          <span className={label}>Hazırlanacak biçimler</span>
          <span className={hint}>Her seçili biçim için tam ölçüsünde bir görsel gelir; talepte istenen biçimler seçili başlar. En az biri seçili olmalı.</span>
          <div className="flex flex-wrap gap-1.5">
            {allFormats.map((x) => (
              <button key={x.key} type="button" aria-pressed={formats.includes(x.key)} className={chip(formats.includes(x.key))}
                onClick={() => setFormats((o) => (o.includes(x.key) ? o.filter((y) => y !== x.key) : [...o, x.key]))}>{x.label}</button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={btnGhost} disabled={suggest.isPending} onClick={() => suggest.mutate()}>
              <Lightbulb className="h-4 w-4" aria-hidden />{suggest.isPending ? 'Zeki AI yazıyor…' : 'Görsel üstü yazı öner'}
            </button>
            <span className="text-[11.5px] text-canvas-muted">A varyantı: kapak + görsel üstü yazı; B varyantı: kitaptan alıntı kartı.</span>
          </div>
          {heads.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {heads.map((h) => (
                <button key={h} type="button" className={chip(r.gorselBasligi === h)} onClick={() => setHeadline.mutate(h)}>{h}</button>
              ))}
            </div>
          )}
          {heads.length > 0 && <span className={hint}>Birine dokunun: görsel üstü yazı olarak kaydedilir ve sonraki hazırlamada A varyantında kullanılır.</span>}
          {suggest.error && <Note tone="err">{errText(suggest.error, 'Zeki AI öneri veremedi. Biraz sonra yeniden deneyin.')}</Note>}
        </div>
      )}
      {produce.error && <Note tone="err">{errText(produce.error, 'Görseller hazırlanamadı. Biraz sonra yeniden deneyin.')}</Note>}
      <JobBar job={job} what="Görsel hazırlama" k={r.kaynaklar} />

      {groups.length === 0 && !running && (
        <EmptyHint title="Henüz görsel yok" why={me?.uret ? 'Yukarıdan biçimleri seçip «Görselleri hazırla»ya basın; her biçim tam ölçüsünde gelir.' : 'Görselleri üretim yetkisi olan ekip hazırlar; hazırlanınca burada görünür.'} />
      )}
      {groups.map(([letter, items]) => {
        const s = items[0].ayar;
        const waiting = items.filter((a) => !a.red && !a.tasarimOnay);
        return (
          <section key={letter} className="flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-200 bg-white/70 p-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="min-w-0 text-[13px] font-extrabold">
                Varyant {letter} · {VISUAL[s?.visual ?? 'cover']}
                {s?.headline ? <span className="font-semibold text-canvas-muted"> · “{s.headline}”</span> : null}
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {me?.tasarimOnay && waiting.length > 1 && (
                  <button type="button" className={smallBtn('ok')} disabled={approveAll.isPending} onClick={() => approveAll.mutate(waiting)}>
                    <CheckIcon className="h-4 w-4" aria-hidden />{waiting.length} biçime tasarım onayı
                  </button>
                )}
                {me?.uret && (
                  <button type="button" className={smallBtn()} disabled={running} onClick={() => setEditing(editing === letter ? null : letter)}>
                    <Pencil className="h-4 w-4" aria-hidden />Düzenle
                  </button>
                )}
              </div>
            </div>
            {editing === letter && (
              <EditVariant a={items[0]} palette={lastDone?.sonuc?.palet ?? []} sources={lastDone?.sonuc?.kaynaklar ?? []}
                quotes={lastDone?.sonuc?.alintilar ?? []} onDone={() => setEditing(null)} />
            )}
            <ul className="grid min-w-0 grid-cols-1 gap-2.5 sm:grid-cols-2 2xl:grid-cols-3">
              {items.map((a) => (
                <li key={a.id} className="flex min-w-0 flex-col gap-1.5 rounded-xl border border-slate-100 bg-white p-2">
                  <a href={creativeApi.fileUrl(a.id)} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-lg bg-slate-100">
                    <Img src={creativeApi.fileUrl(a.id, 480)} alt={`Varyant ${a.varyant} ${a.formatAdi ?? ''}`} fallback="görsel"
                      className="mx-auto max-h-60 w-auto object-contain" />
                  </a>
                  <div className="flex flex-wrap items-center justify-between gap-1">
                    <span className="min-w-0 truncate text-[11.5px] font-bold">{a.formatAdi}</span>
                    <span className="font-mono text-[10.5px] text-canvas-muted">{a.genislik}×{a.yukseklik} · v{a.surum}</span>
                  </div>
                  <ApprovalLine a={a} />
                  {a.red?.not && <p className="text-[11.5px] text-red-700">Ret notu: {a.red.not}</p>}
                  <AssetActions a={a} meta={meta} onVersions={onVersions} />
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </Block>
  );
}
