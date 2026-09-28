import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { NumField } from '../budget/parts';
import { SOURCE_LABEL, fmtMoney, fmtPct, fmtShortDay, mktApi, parseNum, type Line, type Meta, type Plan } from './api';
import { Block } from './parts';

type Draft = Omit<Line, 'tutar'> & { tutar: string; key: string };

const pick = (l: Line) => ({ id: l.id, kanal: l.kanal, altKanal: l.altKanal, aciklama: l.aciklama, tutar: l.tutar, baslangic: l.baslangic, bitis: l.bitis });
const toLine = (r: Draft): Line => pick({ ...r, tutar: parseNum(r.tutar) });

const toDraft = (l: Line, i: number): Draft => ({ ...l, tutar: l.tutar === null ? '' : String(l.tutar).replace('.', ','), key: l.id ?? `n${i}` });

/** Kanal ve bütçe satırları. Zeki AI satırında tutar/tarih değişirse «elle düzeltildi» olur ve yeniden öneride korunur. */
export default function ChannelsTab({ plan, meta, editable: planEditable, onSaved }: { plan: Plan; meta: Meta; editable: boolean; onSaved: (p: Plan) => void }) {
  const canBudget = meta.me.canSeeBudget;
  // Tutarı görmeyen kişi satırları kaydedemez (köprü de reddeder): tutarlar sıfırlanırdı.
  const editable = planEditable && canBudget;
  const [rows, setRows] = useState<Draft[]>(() => plan.lines.map(toDraft));
  const [frame, setFrame] = useState(plan.butceCerceve === null ? '' : String(plan.butceCerceve).replace('.', ','));
  useEffect(() => {
    setRows(plan.lines.map(toDraft));
    setFrame(plan.butceCerceve === null ? '' : String(plan.butceCerceve).replace('.', ','));
  }, [plan]);

  const total = useMemo(() => rows.reduce((s, r) => s + (parseNum(r.tutar) ?? 0), 0), [rows]);
  const dirty = JSON.stringify(rows.map(toLine)) !== JSON.stringify(plan.lines.map(pick));

  const save = useMutation({
    mutationFn: () => mktApi.lines(plan.id, rows.map((r) => ({ ...toLine(r), tutar: parseNum(r.tutar) ?? 0 }))),
    onSuccess: (p) => { onSaved(p); toast.success('Kanal ve bütçe kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const saveFrame = useMutation({
    mutationFn: () => mktApi.update(plan.id, { butceCerceve: parseNum(frame) }),
    onSuccess: (p) => { onSaved(p); toast.success('Bütçe çerçevesi kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });

  const set = (i: number, patch: Partial<Draft>) => setRows((xs) => xs.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const hedefCiro = plan.hedef?.ciro ?? null;
  const cf = plan.butceCerceveKaynak;

  return (
    <div className="flex flex-col gap-3">
      <Block title="Bütçe çerçevesi" help={cf?.gerekce ?? 'Çerçeve henüz hesaplanmadı: «Zeki AI önerisi al» ile kurulur ya da elle girilir.'}>
        {canBudget ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="sm:w-[220px]">
              <NumField id="mkt-frame" label="Çerçeve" value={frame} onChange={setFrame} suffix="₺" />
            </div>
            {editable && (
              <button type="button" className={btnGhost} onClick={() => saveFrame.mutate()} disabled={saveFrame.isPending}>
                Çerçeveyi kaydet
              </button>
            )}
            <div className="flex flex-wrap gap-2 text-[12px] sm:ml-auto">
              <Pill tone={plan.butceCerceve !== null && total > plan.butceCerceve ? 'warn' : 'muted'}>Satır toplamı {fmtMoney(total)}</Pill>
              {hedefCiro ? <Pill tone="muted">Hedef cironun {fmtPct(total / hedefCiro)}</Pill> : <Pill tone="muted">Onaylı hedef ciro yok</Pill>}
              {cf?.oran?.oran != null && <Pill tone="violet">Oran {fmtPct(cf.oran.oran)}{cf.oran.yil ? ` (${cf.oran.yil})` : ''}</Pill>}
              {plan.ustOnayGerekli && <Pill tone="violet">Üst onay eşiğinin üstünde</Pill>}
            </div>
          </div>
        ) : (
          <Note tone="info">Bütçe tutarlarını görme yetkiniz yok; kanal ve tarihleri görebilirsiniz.</Note>
        )}
      </Block>

      <Block
        title="Kanallar"
        help="Kanal payı emsal kitapların CRM pazarlama bütçe kayıtlarından (yoksa şirket geneli) hesaplanır. Satırlar CRM'e yazılmaz; «Onay ve geçmiş» sekmesindeki listeyle CRM'e elle işlenir."
        action={editable && (
          <button type="button" className={btnGhost}
            onClick={() => setRows((xs) => [...xs, { key: `n${Date.now()}`, kanal: 'diger', altKanal: null, aciklama: null, tutar: '', baslangic: plan.yayinTarihi, bitis: null, kaynak: 'kullanici' }])}>
            <Plus aria-hidden className="h-4 w-4" />Satır ekle
          </button>
        )}
      >
        {rows.length === 0 && <Note tone="info">Henüz satır yok. «Zeki AI önerisi al» kanal ve bütçe satırlarını kurar.</Note>}
        <ul className="flex flex-col gap-2">
          {rows.map((r, i) => (
            <li key={r.key} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[180px_1fr_150px_150px_150px]">
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Kanal</span>
                  <select className={field} value={r.kanal} disabled={!editable} onChange={(e) => set(i, { kanal: e.target.value })}>
                    {Object.entries(meta.channels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
                <label className="flex min-w-0 flex-col gap-1">
                  <span className={labelCls}>Açıklama / mecra</span>
                  <input className={field} value={r.aciklama ?? ''} disabled={!editable} onChange={(e) => set(i, { aciklama: e.target.value || null })} />
                </label>
                {canBudget && (
                  <NumField id={`mkt-l-${r.key}`} label="Tutar" value={r.tutar} onChange={(v) => editable && set(i, { tutar: v })} suffix="₺" />
                )}
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Başlangıç</span>
                  <input type="date" className={field} value={r.baslangic ?? ''} disabled={!editable} onChange={(e) => set(i, { baslangic: e.target.value || null })} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={labelCls}>Bitiş</span>
                  <input type="date" className={field} value={r.bitis ?? ''} disabled={!editable} onChange={(e) => set(i, { bitis: e.target.value || null })} />
                </label>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-canvas-muted">
                <Pill tone={r.kaynak === 'zeki' ? 'violet' : 'muted'}>{SOURCE_LABEL(r.kaynak)}</Pill>
                {r.elleDuzeltildi && <Pill tone="warn">Elle düzeltildi</Pill>}
                {!editable && <span>{fmtShortDay(r.baslangic)} – {fmtShortDay(r.bitis)}</span>}
                {r.gerekce && <span className="min-w-0 flex-1 leading-snug">{r.gerekce}</span>}
                {editable && (
                  <button type="button" aria-label="Satırı sil" className={`${btnGhost} ml-auto`} onClick={() => setRows((xs) => xs.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
        {editable && (
          <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
            {dirty && <span className="text-[11.5px] font-semibold text-amber-800">Kaydedilmemiş değişiklik var</span>}
            <button type="button" className={btnPrimary} onClick={() => save.mutate()} disabled={!dirty || save.isPending}>Kaydet</button>
          </div>
        )}
      </Block>
    </div>
  );
}
