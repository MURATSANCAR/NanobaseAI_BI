import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, ChevronLeft, ChevronRight, Loader2, Sparkles, Wand2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay } from '../editorial/authors/shared';
import { GIFT_NEXT, fmtInt, fmtMonth, paApi, shiftMonth, type Book, type Gift, type GiftStatus, type Suggestion } from './api';
import { BookPicker } from './pickers';
import { BASE, Empty, GiftPill, PaFrame, invalidatePa, usePaMeta } from './parts';

/** Hediye programı: ay ay kitap × kişi listesi, gerekçe ve kişisel not, yönetim onayı (kamu görevlisine hukuk onayıyla),
 *  CRM tanıtım siparişinden gönderim durumu, geri dönüş. Gönderimi satış operasyonu CRM siparişiyle yapar. */

export default function PaGifts() {
  const qc = useQueryClient();
  const meta = usePaMeta();
  const [params, setParams] = useSearchParams();
  const month = params.get('ay') ?? meta.data?.month ?? '';
  const status = params.get('durum') ?? '';
  const setParam = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
  };
  const list = useQuery({
    queryKey: ['pa', 'gifts', month, status],
    queryFn: () => paApi.gifts({ month, status }),
    enabled: ENGINE_ENABLED && !!month,
    placeholderData: keepPreviousData,
  });
  const me = meta.data?.me;
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [legal, setLegal] = useState<Set<string>>(new Set());
  const [openRow, setOpenRow] = useState<Gift | null>(null);
  const [suggest, setSuggest] = useState(false);
  useEffect(() => {
    setSel(new Set());
    setLegal(new Set());
  }, [month, status]);

  const approve = useMutation({
    mutationFn: (decision: 'onay' | 'geri') => paApi.approveGifts({ ids: [...sel], decision, legalOk: [...legal] }),
    onSuccess: async (r) => {
      await invalidatePa(qc);
      setSel(new Set());
      setLegal(new Set());
      if (r.done.length) toast.success(`${r.done.length} satır işlendi.`);
      r.skipped.forEach((s) => toast.warning(`Atlandı: ${s.reason}`));
    },
    onError: (e) => toast.error(errText(e, 'Onaylanamadı.') ?? ''),
  });

  const items = list.data?.items ?? [];
  const selectable = (g: Gift) => (g.status === 'oneri' || g.status === 'onayli') && me?.canApprove;
  const toggle = (id: string) =>
    setSel((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <PaFrame
      title="Hediye programı"
      lead="Ayın kitapları kime gidecek: gerekçeli liste, kişisel not taslağı, yönetim onayı. Onaylanan satır CRM'de tanıtım siparişiyle gönderilir; sipariş numarası yazılınca durumu her sabah CRM'den okunur. Aynı kişiye aynı kitap ikinci kez yazılamaz."
      source={list.data ? `${fmtInt(list.data.books)} kitap · ${fmtInt(list.data.people)} kişi` : 'Portal + CRM'}
      aside={
        me?.canEdit ? (
          <button type="button" className={`${btnPrimary} w-full lg:w-auto`} onClick={() => setSuggest(true)}>
            <Sparkles aria-hidden className="h-4 w-4" />
            Kime gönderelim?
          </button>
        ) : undefined
      }
    >
      <div className="glass-panel flex flex-wrap items-center justify-between gap-2 rounded-2xl p-3 shadow-glass-float">
        <div className="flex items-center gap-1">
          <button type="button" aria-label="Önceki ay" className={`${btnGhost} !px-2`} onClick={() => month && setParam('ay', shiftMonth(month, -1))}>
            <ChevronLeft aria-hidden className="h-4 w-4" />
          </button>
          <span className="min-w-[128px] text-center text-[14px] font-extrabold">{month ? fmtMonth(month) : '—'}</span>
          <button type="button" aria-label="Sonraki ay" className={`${btnGhost} !px-2`} onClick={() => month && setParam('ay', shiftMonth(month, 1))}>
            <ChevronRight aria-hidden className="h-4 w-4" />
          </button>
        </div>
        <SqlInfo k={list.data?.kaynaklar} alan="counts" label="Hediye programı: durum, kitap ve kişi sayıları" />
        <select aria-label="Durum" value={status} onChange={(e) => setParam('durum', e.target.value)} className={`${field} w-auto`}>
          <option value="">Bütün durumlar</option>
          {(meta.data?.giftStatus ?? []).map((s) => (
            <option key={s.key} value={s.key}>
              {s.label} {list.data ? `(${list.data.counts[s.key as GiftStatus] ?? 0})` : ''}
            </option>
          ))}
        </select>
      </div>

      {me?.canApprove && sel.size > 0 && (
        <div className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-canvas-violet/30 bg-white/95 p-3 shadow-glass-float">
          <span className="text-[12.5px] font-extrabold">{sel.size} satır seçili</span>
          <div className="flex gap-2">
            <button type="button" className={btnGhost} disabled={approve.isPending} onClick={() => approve.mutate('geri')}>
              Onayı geri al
            </button>
            <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate('onay')}>
              <Check aria-hidden className="h-4 w-4" />
              Onayla
            </button>
          </div>
        </div>
      )}

      {list.error && <Note tone="err">{errText(list.error, 'Program okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data &&
        (items.length === 0 ? (
          <Empty title="Bu ayın programı boş">«Kime gönderelim?» ile ayın yeni kitapları için gerekçeli öneri alın ya da kişi kartından hediye ekleyin.</Empty>
        ) : (
          <ul className="grid gap-2 lg:grid-cols-2">
            {items.map((g) => (
              <li key={g.id} className="glass-panel flex gap-3 rounded-2xl p-3 shadow-glass-float">
                {selectable(g) && (
                  <input type="checkbox" aria-label={`${g.personName} · ${g.bookName} seç`} className="mt-1 h-5 w-5 shrink-0" checked={sel.has(g.id)} onChange={() => toggle(g.id)} />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="break-words font-extrabold">{g.bookName ?? g.stockCode}</span>
                    <GiftPill status={g.status} label={g.statusLabel} />
                  </div>
                  <div className="text-[12px]">
                    <Link to={`${BASE}/kisi/${g.personId}`} className="font-semibold text-canvas-violet hover:underline">
                      {g.personName}
                    </Link>
                    {g.personTitle && <span className="text-canvas-muted"> · {g.personTitle}</span>}
                  </div>
                  {g.reason && <p className="mt-0.5 text-[11.5px] text-canvas-muted">Gerekçe: {g.reason}</p>}
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px]">
                    {g.isPublicOfficial && (
                      <Pill tone={g.legalOk ? 'ok' : 'warn'}>{g.legalOk ? 'Kamu görevlisi · hukuk onaylı' : 'Kamu görevlisi · hukuk onayı gerekli'}</Pill>
                    )}
                    {g.crmOrderNo && (
                      <Pill tone={g.crmOrderStatusLabel === "CRM'de bulunamadı" ? 'err' : 'muted'}>
                        CRM {g.crmOrderNo}
                        {g.crmOrderStatusLabel ? ` · ${g.crmOrderStatusLabel}` : ''}
                      </Pill>
                    )}
                    {g.crmBookInOrder === false && <Pill tone="warn">Kitap siparişte yok</Pill>}
                    {g.noteText ? <Pill tone="violet">Kişisel not var</Pill> : <span className="text-canvas-muted">Not yazılmadı</span>}
                  </div>
                  {selectable(g) && g.isPublicOfficial && !g.legalOk && sel.has(g.id) && (
                    <label className="mt-2 flex min-h-11 items-center gap-2 rounded-xl bg-amber-50 px-2.5 text-[12px] font-semibold text-amber-900">
                      <input
                        type="checkbox"
                        checked={legal.has(g.id)}
                        onChange={(e) =>
                          setLegal((s) => {
                            const n = new Set(s);
                            if (e.target.checked) n.add(g.id);
                            else n.delete(g.id);
                            return n;
                          })
                        }
                      />
                      Hukuk onayı alındı (kamu görevlisine hediye)
                    </label>
                  )}
                </div>
                <button type="button" className={`${btnGhost} !min-h-10 shrink-0 self-start !py-1`} onClick={() => setOpenRow(g)}>
                  Aç
                </button>
              </li>
            ))}
          </ul>
        ))}

      {openRow && <GiftSheet gift={items.find((x) => x.id === openRow.id) ?? openRow} onClose={() => setOpenRow(null)} />}
      {month && <SuggestSheet open={suggest} month={month} onClose={() => setSuggest(false)} />}
    </PaFrame>
  );
}

function GiftSheet({ gift, onClose }: { gift: Gift; onClose: () => void }) {
  const qc = useQueryClient();
  const meta = usePaMeta();
  const canEdit = !!meta.data?.me.canEdit;
  const [f, setF] = useState({ reason: gift.reason ?? '', noteText: gift.noteText ?? '', crmOrderNo: gift.crmOrderNo ?? '', feedback: gift.feedback ?? '' });
  useEffect(() => setF({ reason: gift.reason ?? '', noteText: gift.noteText ?? '', crmOrderNo: gift.crmOrderNo ?? '', feedback: gift.feedback ?? '' }), [gift]);
  const save = useMutation({
    mutationFn: (b: Record<string, unknown>) => paApi.updateGift(gift.id, b),
    onSuccess: async () => {
      await invalidatePa(qc);
      toast.success('Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const draft = useMutation({
    mutationFn: () => paApi.draftNote(gift.id),
    onSuccess: async (g) => {
      setF((p) => ({ ...p, noteText: g.noteText ?? '' }));
      await invalidatePa(qc);
      toast.success('Zeki AI taslağı yazıldı; gözden geçirip düzeltin.');
    },
    onError: (e) => toast.error(errText(e, 'Taslak alınamadı.') ?? ''),
  });
  const labels = Object.fromEntries((meta.data?.giftStatus ?? []).map((s) => [s.key, s.label]));
  return (
    <Sheet open onClose={onClose} modal title={gift.bookName ?? 'Hediye'} subtitle={`${gift.personName ?? ''} · ${fmtMonth(gift.month)}`}>
      <div className="space-y-3 text-[12.5px]">
        <div className="flex flex-wrap items-center gap-1.5">
          <GiftPill status={gift.status} label={gift.statusLabel} />
          {gift.approvedBy && <span className="text-canvas-muted">Onaylayan {gift.approvedBy}</span>}
          {gift.shippedOn && <span className="text-canvas-muted">· sevk {fmtDay(gift.shippedOn)}</span>}
        </div>
        <label className="block">
          <span className={label}>Gerekçe</span>
          <input maxLength={500} value={f.reason} disabled={!canEdit} onChange={(e) => setF((p) => ({ ...p, reason: e.target.value }))} className={`${field} mt-1`} />
        </label>
        <label className="block">
          <span className={label}>Kişisel not</span>
          <textarea rows={4} maxLength={4000} value={f.noteText} disabled={!canEdit} onChange={(e) => setF((p) => ({ ...p, noteText: e.target.value }))} className={`${field} mt-1 resize-y leading-snug`} />
        </label>
        {canEdit && (
          <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={draft.isPending} onClick={() => draft.mutate()}>
            {draft.isPending ? <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> : <Wand2 aria-hidden className="h-3.5 w-3.5" />}
            {draft.isPending ? 'Zeki AI yazıyor…' : 'Zeki AI ile not taslağı'}
          </button>
        )}
        <label className="block">
          <span className={label}>CRM tanıtım sipariş numarası</span>
          <input maxLength={40} value={f.crmOrderNo} disabled={!canEdit} onChange={(e) => setF((p) => ({ ...p, crmOrderNo: e.target.value }))} placeholder="Satış operasyonunun açtığı sipariş" className={`${field} mt-1`} />
          {gift.crmSyncedAt && <span className="mt-1 block text-[11px] text-canvas-muted">CRM'den son okuma {fmtDay(gift.crmSyncedAt)}</span>}
        </label>
        {['sevk', 'teslim', 'donus'].includes(gift.status) && (
          <label className="block">
            <span className={label}>Geri dönüş</span>
            <textarea rows={2} maxLength={4000} value={f.feedback} disabled={!canEdit} onChange={(e) => setF((p) => ({ ...p, feedback: e.target.value }))} placeholder="ör. Teşekkür etti, ders listesine aldı" className={`${field} mt-1 resize-y`} />
          </label>
        )}
        {canEdit && (
          <div className="flex flex-wrap justify-between gap-2 pt-1">
            <div className="flex flex-wrap gap-1.5">
              {GIFT_NEXT[gift.status].map((s) => (
                <button key={s} type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={save.isPending} onClick={() => save.mutate({ status: s })}>
                  {labels[s] ?? s}
                </button>
              ))}
            </div>
            <button
              type="button"
              className={btnPrimary}
              disabled={save.isPending}
              onClick={() => save.mutate({ reason: f.reason || null, noteText: f.noteText || null, crmOrderNo: f.crmOrderNo || null, ...(['sevk', 'teslim', 'donus'].includes(gift.status) ? { feedback: f.feedback || null } : {}) })}
            >
              {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
            </button>
          </div>
        )}
      </div>
    </Sheet>
  );
}

/** Kitap(lar) → kime gönderelim: ayın yeni kitapları ya da seçilen kitaplar; kural puanı ve gerekçesiyle kişiler. */
function SuggestSheet({ open, month, onClose }: { open: boolean; month: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [books, setBooks] = useState<Book[]>([]);
  const [useMonth, setUseMonth] = useState(true);
  const [all, setAll] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (open) {
      setBooks([]);
      setUseMonth(true);
      setPicked(new Set());
      setAll(false);
    }
  }, [open]);
  const run = useMutation({
    mutationFn: () => paApi.suggest(useMonth ? { month, all } : { bookIds: books.map((b) => b.id as string), all }),
    onSuccess: () => setPicked(new Set()),
    onError: (e) => toast.error(errText(e, 'Öneri alınamadı.') ?? ''),
  });
  const add = useMutation({
    mutationFn: async (rows: Suggestion[]) => {
      const out = { ok: 0, fail: [] as string[] };
      for (const r of rows) {
        try {
          await paApi.addGift({ personId: r.personId, crmBookId: r.bookId, bookName: r.bookName, stockCode: r.stockCode, author: r.author, month, reason: r.reason.slice(0, 500) });
          out.ok += 1;
        } catch (e) {
          out.fail.push(`${r.personName}: ${errText(e, 'eklenemedi')}`);
        }
      }
      return out;
    },
    onSuccess: async (r) => {
      await invalidatePa(qc);
      if (r.ok) toast.success(`${r.ok} satır programa eklendi (öneri).`);
      r.fail.forEach((m) => toast.warning(m));
      if (!r.fail.length) onClose();
    },
  });
  const key = (s: Suggestion) => `${s.bookId}:${s.personId}`;
  const groups = useMemo(() => {
    const m = new Map<string, Suggestion[]>();
    (run.data?.items ?? []).forEach((s) => m.set(s.bookId, [...(m.get(s.bookId) ?? []), s]));
    return [...m.entries()];
  }, [run.data]);

  return (
    <Sheet open={open} onClose={onClose} modal wide title="Kime gönderelim?" subtitle={`${fmtMonth(month)} programı · puan kuraldır: kişinin alanı, ilgi alanları ve CRM uzmanlığı × kitabın türü ve konusu`}>
      <div className="space-y-3 text-[12.5px]">
        <div className="grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Kitaplar">
          {[true, false].map((m) => (
            <button
              key={String(m)}
              type="button"
              role="tab"
              aria-selected={useMonth === m}
              onClick={() => setUseMonth(m)}
              className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${useMonth === m ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}
            >
              {m ? `${fmtMonth(month)} yeni kitapları` : 'Kitap seç'}
            </button>
          ))}
        </div>
        {!useMonth && (
          <>
            <BookPicker picked={books.map((b) => b.id as string)} action="Ekle" onPick={(b) => setBooks((x) => [...x, b])} />
            {books.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {books.map((b) => (
                  <button key={b.id} type="button" className="rounded-lg bg-violet-50 px-2 py-1 text-[11.5px] font-bold text-violet-800" onClick={() => setBooks((x) => x.filter((y) => y.id !== b.id))}>
                    {b.name} ×
                  </button>
                ))}
              </div>
            )}
          </>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex min-h-11 items-center gap-2 font-semibold">
            <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
            Konu örtüşmesi olmayanları da göster
          </label>
          <button type="button" className={btnPrimary} disabled={run.isPending || (!useMonth && books.length === 0)} onClick={() => run.mutate()}>
            {run.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            Önerileri getir
          </button>
        </div>
        {run.data && (
          <>
            <p className="flex flex-wrap items-center gap-1 text-canvas-muted">
              {fmtInt(run.data.books.length)} kitap × {fmtInt(run.data.people)} kişi kartı → {fmtInt(run.data.total)} öneri. Kitabı daha önce almış kişi listede yok.
              <SqlInfo k={run.data.kaynaklar} alan="items" label="Hediye önerisi" />
            </p>
            {groups.length === 0 && <Empty title="Öneri yok">{run.data.books.length === 0 ? 'Bu ay ilk baskısı yapılan kitap yok; «Kitap seç» ile seçin.' : 'Kişi kartlarında konu örtüşmesi yok; «örtüşmesi olmayanları da göster»i açın.'}</Empty>}
            {groups.map(([bookId, rows]) => (
              <section key={bookId} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
                <h3 className="text-[13px] font-extrabold">
                  {rows[0].bookName}
                  {rows[0].author && <span className="font-normal text-canvas-muted"> · {rows[0].author}</span>}
                </h3>
                <ul className="mt-1 divide-y divide-slate-100">
                  {rows.map((s) => (
                    <li key={key(s)} className="flex items-start gap-2 py-1.5">
                      <input
                        type="checkbox"
                        aria-label={`${s.personName} seç`}
                        className="mt-1 h-5 w-5 shrink-0"
                        checked={picked.has(key(s))}
                        onChange={() =>
                          setPicked((p) => {
                            const n = new Set(p);
                            if (n.has(key(s))) n.delete(key(s));
                            else n.add(key(s));
                            return n;
                          })
                        }
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-extrabold">{s.personName}</span>
                          <span className="font-mono text-[11px] tabular-nums text-canvas-muted">puan {s.score}</span>
                          {s.isPublicOfficial && <Pill tone="warn">Kamu görevlisi</Pill>}
                        </div>
                        <div className="text-[11.5px] text-canvas-muted">{[s.personTitle, s.orgName, s.fieldLabel].filter(Boolean).join(' · ')}</div>
                        <div className="text-[11.5px]">{s.reason}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
            {picked.size > 0 && (
              <div className="sticky bottom-0 flex justify-end bg-white/95 py-2">
                <button type="button" className={btnPrimary} disabled={add.isPending} onClick={() => add.mutate((run.data?.items ?? []).filter((s) => picked.has(key(s))))}>
                  {add.isPending ? 'Ekleniyor…' : `${picked.size} satırı programa ekle`}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </Sheet>
  );
}
