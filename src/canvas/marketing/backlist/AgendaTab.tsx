import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { fmtDay, fmtShortDay } from '../api';
import { Block, DaysLeft } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { blApi, fmtN, fmtOne, type AgendaBook, type BlMeta } from './api';

/** Gündem: önümüzdeki N haftanın özel günleri (bağlı kitaplar, stok, geçen yılın aynı ayı), yazarı yeni kitap çıkaran
 *  backlist kitaplar, Zeki AI konu eşleşmeleri (onay). Bir günün kitapları seçilip tek planda aktive edilir. */
export default function AgendaTab({ meta }: { meta: BlMeta }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [weeks, setWeeks] = useState(meta.settings.agendaWeeks);
  const [picked, setPicked] = useState<Record<string, Set<string>>>({});
  const q = useQuery({ queryKey: ['bl', 'agenda', weeks], queryFn: () => blApi.agenda(weeks), enabled: ENGINE_ENABLED });
  const create = useMutation({
    mutationFn: ({ codes, start }: { codes: string[]; start?: string }) => blApi.createPlan(codes.map((stokKodu) => ({ stokKodu })), start),
    onSuccess: (plan) => {
      qc.invalidateQueries({ queryKey: ['bl'] });
      toast.success('Aktivasyon planı taslağı açıldı.');
      nav(`/pazarlama/plan/${encodeURIComponent(plan.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Plan açılamadı.') ?? ''),
  });
  const decide = useMutation({
    mutationFn: ({ id, karar }: { id: string; karar: 'kabul' | 'red' }) => blApi.decide(id, karar),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bl', 'agenda'] }),
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  const me = meta.me;
  const d = q.data;
  const toggle = (group: string, code: string) =>
    setPicked((p) => {
      const s = new Set(p[group] ?? []);
      if (s.has(code)) s.delete(code);
      else s.add(code);
      return { ...p, [group]: s };
    });

  const bookList = (group: string, books: AgendaBook[], showLastYear: boolean) => (
    <ul className="flex flex-col divide-y divide-slate-100">
      {books.map((b) => {
        const inStock = (b.stok ?? 0) > 0;
        return (
          <li key={b.stokKodu} className="flex min-h-11 items-center gap-2 py-1.5">
            {me.canWrite && (
              <input type="checkbox" className="h-5 w-5 shrink-0" disabled={!inStock} checked={picked[group]?.has(b.stokKodu) ?? false}
                onChange={() => toggle(group, b.stokKodu)} aria-label={`${b.ad ?? b.stokKodu} seç`} />
            )}
            <div className="min-w-0 flex-1">
              <div className="break-words font-bold leading-snug">{b.ad ?? b.stokKodu}</div>
              <div className="text-[11px] text-canvas-muted">
                {b.stokKodu}{b.yazar ? ` · ${b.yazar}` : ''} · stok {fmtN(b.stok)}{b.tukenmeAy !== null ? ` (${fmtOne(b.tukenmeAy)} ay)` : ''}
                {showLastYear ? ` · geçen yıl aynı ay ${fmtN(b.gecenYilAyAdet)} adet` : ''}
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap justify-end gap-1">
              {b.sapmaAcik && <Pill tone="err">Sapma</Pill>}
              {!inStock && <Pill tone="muted">Stok yok</Pill>}
              {b.planlar[0] && <Pill tone="ok">{b.planlar[0].durumAdi}</Pill>}
            </div>
          </li>
        );
      })}
    </ul>
  );
  const action = (group: string, start?: string) => {
    const n = picked[group]?.size ?? 0;
    if (!me.canWrite || !n) return undefined;
    return (
      <button type="button" className={btnPrimary} disabled={create.isPending} onClick={() => create.mutate({ codes: [...(picked[group] ?? [])], start })}>
        {create.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}{n} kitapla plan aç
      </button>
    );
  };

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <div className="flex flex-wrap items-end gap-2 px-1">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Önümüzdeki</span>
          <select className={`${field} w-auto`} value={weeks} onChange={(e) => setWeeks(Number(e.target.value))}>
            {[4, 6, 8, 12, 16, 26].map((w) => <option key={w} value={w}>{w} hafta</option>)}
          </select>
        </label>
        <p className="max-w-[80ch] text-[11.5px] leading-snug text-canvas-muted">
          Önümüzdeki haftalarda backlist kitaplarını gündeme taşıyabilecek fırsatlar: yaklaşan özel günler, yazarın yeni kitabı ve konu eşleşmeleri. Bağlar CRM'den gelir; kitapları seçip plan açabilirsiniz.
          Özel güne {meta.settings.remindWeeks} hafta kala, bağlı ve stoklu ama planı olmayan kitaplar e-postayla hatırlatılır.
        </p>
      </div>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Gündem açılamadı.')}</Note>}
      {d && !d.gunler.length && !d.yazarlar.length && !d.konular.length && <Note tone="info">Seçtiğiniz süre içinde backlist kitaplarına bağlı özel gün, yazarın yeni kitabı ya da konu eşleşmesi yok. Süreyi uzatmayı deneyin.</Note>}

      {d?.gunler.map((g) => (
        <Block key={`${g.id}-${g.baslangic}`} title={g.ad ?? 'Özel gün'} info={<SqlInfo k={d?.kaynaklar} alan="gunler[]" label="Stok, tükenme ve geçen yıl aynı ay" />}
          help={<>{fmtDay(g.baslangic)}{g.bitis && g.bitis !== g.baslangic ? ` – ${fmtDay(g.bitis)}` : ''} · {g.yontem ?? ''}{g.kesinlik === 'yaklasik' ? ' (yaklaşık)' : ''} · bağlı {g.kitaplar.length} kitap, stokta {g.stokta}, planı olmayan {g.aktivasyonsuz}</>}
          action={<div className="flex items-center gap-2"><DaysLeft days={g.kalanGun} />{action(`gun:${g.id}`, g.baslangic ?? undefined)}</div>}>
          {bookList(`gun:${g.id}`, g.kitaplar, true)}
        </Block>
      ))}

      {!!d?.yazarlar.length && (
        <Block title="Yazarı yeni kitap çıkaranlar" info={<SqlInfo k={d?.kaynaklar} alan="yazarlar[]" label="Yazarı yeni kitap çıkaranlar" />} help="Yeni kitabın ilk yayını son 30 gün ya da pencere içinde; aynı yazarın backlist kitapları çapraz satış adayıdır.">
          <div className="flex flex-col gap-3">
            {d.yazarlar.map((a) => (
              <div key={a.stokKodu}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-extrabold">{a.ad} <span className="font-normal text-canvas-muted">· {a.yazar ?? '—'} · {fmtShortDay(a.tarih)}</span></div>
                  {action(`yazar:${a.stokKodu}`)}
                </div>
                {bookList(`yazar:${a.stokKodu}`, a.kitaplar, false)}
              </div>
            ))}
          </div>
        </Block>
      )}

      {!!d?.konular.length && (
        <Block title="Konu eşleşmeleri" info={<SqlInfo k={d?.kaynaklar} alan="konular[]" label="Konu eşleşmesi ve skor" />} help="Özel günün adı kitabın CRM'deki anahtar kelime ve temalarında geçiyor. Zeki AI eşleşmenin ilgili olup olmadığını tahmin etti; kararı siz verirsiniz.">
          <ul className="flex flex-col divide-y divide-slate-100">
            {d.konular.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-2 py-2">
                <div className="min-w-0 flex-1">
                  <div className="font-bold">{m.kitap.ad ?? m.stokKodu} ↔ {m.etiket}</div>
                  <div className="text-[11px] text-canvas-muted">
                    {fmtShortDay(m.tarih)} · Zeki AI {String(m.detay.karar ?? '—').toLocaleLowerCase('tr')}
                    {m.skor !== null ? ` (%${Math.round(m.skor * 100)})` : ''} · stok {fmtN(m.kitap.stok)}
                  </div>
                </div>
                {m.onay === 'bekliyor' && me.canWrite ? (
                  <div className="flex gap-1.5">
                    <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ id: m.id, karar: 'kabul' })}>Kabul</button>
                    <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => decide.mutate({ id: m.id, karar: 'red' })}>Red</button>
                  </div>
                ) : (
                  <Pill tone={m.onay === 'kabul' ? 'ok' : m.onay === 'red' ? 'muted' : 'warn'}>
                    {m.onay === 'kabul' ? 'Kabul' : m.onay === 'red' ? `Red${m.onaylayan ? ` · ${m.onaylayan}` : ''}` : 'Onay bekliyor'}
                  </Pill>
                )}
              </li>
            ))}
          </ul>
        </Block>
      )}
    </div>
  );
}
