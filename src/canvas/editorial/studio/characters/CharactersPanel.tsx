import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ChevronLeft, ChevronRight, Loader2, Pencil, Plus, ScanSearch, Sparkles, UserRound } from 'lucide-react';
import { studioApi } from '../../../engine';
import { Loading, Note, Pill, errText, field } from '../../../admin/ui';
import { Img, ghostBtn, gradientBtn, press } from '../shared';
import { Section } from '../elements/controls';
import CardEditor from './CardEditor';
import { cardsApi, cardsKey, useCardsView, type Card, type CardsView, type CheckItem } from './api';

/** «Karakterler» paneli: dizinin karakter kartları (görünüş ve renkler bir kez kaydedilir, dizinin her kitabında
 *  kullanılır), bu kitabın karakterleri ve karta uymayan resimler. Liste ile kart düzenleyici arasında geçiş
 *  anlık (sık yapılan bir gezinme; hareket eklenmedi). */

const TASK_TEXT = { queued: 'sırada', running: 'sürüyor', done: 'bitti', fail: 'başarısız' } as const;
const num = (v: number) => v.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function SeriesBox({ jobId, view }: { jobId: string; view: CardsView }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(!view.series);
  const [name, setName] = useState(view.series?.name ?? '');
  const save = useMutation({
    mutationFn: (v: string) => cardsApi.setSeries(jobId, v),
    onSuccess: () => { setEditing(false); qc.invalidateQueries({ queryKey: cardsKey(jobId) }); },
  });
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-white/70 bg-white/70 p-3">
      {view.series && !editing ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Dizi</div>
            <div className="truncate text-[14px] font-extrabold">{view.series.name}{view.series.number ? ` · ${view.series.number}. kitap` : ''}</div>
            <div className="text-[11.5px] text-canvas-muted">Kaynak: {view.series.source}{view.series.exists ? '' : ' · bu dizide henüz kart yok'}</div>
          </div>
          <button type="button" className={`${ghostBtn} !min-h-10 shrink-0 whitespace-nowrap`} onClick={() => { setName(view.series?.name ?? ''); setEditing(true); }}>
            <Pencil className="h-4 w-4" aria-hidden />Değiştir
          </button>
        </div>
      ) : (
        <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); save.mutate(name); }}>
          {!view.series && (
            <Note tone="warn">Bu kitabın dizisi künyeden ya da kitap kaydından belirlenemedi. Karakter kartları dizi düzeyinde saklanır; dizinin adını yazın.</Note>
          )}
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-bold">Dizi adı</span>
            <input className={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="Ör. Meraklı Vombat Kitapları" maxLength={120} />
          </label>
          {save.error && <Note tone="err">{errText(save.error, 'Kaydedilemedi.')}</Note>}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={gradientBtn} disabled={save.isPending || !name.trim()}>Kaydet</button>
            {view.series && <button type="button" className={ghostBtn} onClick={() => setEditing(false)}>Vazgeç</button>}
            {view.series?.source === 'editör' && (
              <button type="button" className={ghostBtn} disabled={save.isPending} onClick={() => save.mutate('')} title="Künye ve kitap kaydına göre bul">
                Otomatik bul
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

function Swatches({ card }: { card: Card }) {
  const cols = [card.palette_color, ...Object.values(card.colors ?? {})].filter(Boolean) as string[];
  if (!cols.length) return null;
  return (
    <span className="flex -space-x-1" aria-hidden>
      {cols.map((c, i) => <span key={`${c}-${i}`} className="h-4 w-4 rounded-full border border-white shadow-sm" style={{ background: c }} />)}
    </span>
  );
}

function CardRow({ jobId, card, inBook, onOpen }: { jobId: string; card: Card; inBook: boolean; onOpen: () => void }) {
  const primary = card.refs.find((r) => r.primary);
  return (
    <li>
      <button type="button" onClick={onOpen}
        className={`flex w-full items-center gap-3 rounded-2xl border border-white/70 bg-white/75 p-2 text-left hover:bg-white ${press}`}>
        {primary
          ? <Img src={cardsApi.refUrl(jobId, card.id, primary.id, 120)} alt="" fallback="" className="h-12 w-12 shrink-0 rounded-xl bg-white object-contain" />
          : <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-400"><UserRound className="h-5 w-5" aria-hidden /></span>}
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-[13.5px] font-extrabold">{card.name}</span>
            {card.status === 'approved' ? <Pill tone="ok">Onaylı</Pill> : <Pill tone="warn">Taslak</Pill>}
            {card.en_stale && <Pill tone="warn">Tarif yenilenmeli</Pill>}
            {!inBook && <Pill tone="muted">Bu kitapta yok</Pill>}
          </span>
          <span className="mt-0.5 flex items-center gap-2 text-[11.5px] text-canvas-muted">
            <span className="truncate">{[card.kind, card.age].filter(Boolean).join(' · ')}{card.origin?.title ? ` · «${card.origin.title}»` : ''}</span>
            <Swatches card={card} />
          </span>
        </span>
        <ChevronRight className="h-4 w-4 shrink-0 text-canvas-muted" aria-hidden />
      </button>
    </li>
  );
}

function Mismatch({ jobId, it }: { jobId: string; it: CheckItem }) {
  const bad = it.status === 'mismatch';
  return (
    <li className="flex gap-3 rounded-2xl border border-white/70 bg-white/75 p-2">
      <Img src={studioApi.artUrl(jobId, it.key, it.v, 200)} alt={`Resim ${it.page ?? it.key}`} fallback="resim"
        className="h-16 w-20 shrink-0 rounded-lg bg-slate-100 object-cover" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[13px] font-extrabold">{it.page ? `Sayfa ${it.page}` : it.key} · v{it.v}</span>
          {bad ? <Pill tone="err">Karakter kartına uymuyor</Pill> : <Pill tone="muted">Denetlenemedi</Pill>}
          {it.approved && <Pill tone="ok">Onaylı</Pill>}
        </div>
        <ul className="mt-0.5 text-[11.5px] text-canvas-muted">
          {it.characters.map((c) => (
            <li key={c.name}>
              {c.name}: {c.state === 'mismatch' || c.state === 'ok'
                ? `kartla fark ${num(c.distance ?? 0)}${it.threshold != null ? ` (sınır ${num(it.threshold)})` : ''}`
                : c.state === 'notfound' ? 'resimde bulunamadı' : c.state === 'noref' ? 'kartta referans görsel yok' : c.state}
            </li>
          ))}
        </ul>
        {bad && <p className="text-[11.5px] text-canvas-muted">{it.attempt ? `${it.attempt} kez yeniden çizildi; en yakın sürüm seçili.` : 'Yeniden çizilmedi.'} Sayfa stüdyosunda düzeltin ya da yeni görsel üretin.</p>}
        {it.note && <p className="text-[11.5px] text-canvas-muted">{it.note}</p>}
      </div>
    </li>
  );
}

export default function CharactersPanel({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  const q = useCardsView(jobId);
  const [open, setOpen] = useState<{ card: Card | null; preset?: { name: string; species: string } } | null>(null);
  const run = useMutation({
    mutationFn: (f: () => Promise<unknown>) => f(),
    onSuccess: () => qc.invalidateQueries({ queryKey: cardsKey(jobId) }),
  });
  const v = q.data;
  if (!v) return q.error ? <Note tone="err">{errText(q.error, 'Karakterler okunamadı.')}</Note> : <Loading />;

  if (open) {
    const title = open.card ? open.card.name : 'Yeni kart';
    return (
      <div className="flex flex-col gap-3">
        <button type="button" onClick={() => setOpen(null)} className={`inline-flex min-h-10 items-center gap-1 self-start rounded-xl px-2 text-[13px] font-bold text-canvas-violet hover:bg-white/70 ${press}`}>
          <ChevronLeft className="h-4 w-4" aria-hidden />Kartlar
        </button>
        <h3 className="text-[16px] font-extrabold">{title}</h3>
        <CardEditor key={open.card?.id ?? 'yeni'} jobId={jobId} view={v} card={open.card} preset={open.preset} onDone={() => setOpen(null)} />
      </div>
    );
  }

  const suggest = v.task?.suggest;
  const suggesting = !!suggest && (suggest.status === 'queued' || suggest.status === 'running');
  const checking = v.busy?.key === 'karakter' || v.check.pending > 0 || (!!v.task?.check && ['queued', 'running'].includes(v.task.check.status));
  const bookNames = new Set(v.book.map((b) => b.name.toLocaleLowerCase('tr')));
  const inBook = (c: Card) => [c.name, ...(c.aliases ?? [])].some((n) => bookNames.has(n.toLocaleLowerCase('tr')));
  const missing = v.book.filter((b) => !b.card);
  const bad = v.check.items.filter((i) => i.status === 'mismatch');
  const approved = v.cards.filter((c) => c.status === 'approved').length;

  return (
    <div className="flex flex-col gap-4">
      <SeriesBox key={v.series?.id ?? 'yok'} jobId={jobId} view={v} />
      {run.error && <Note tone="err">{errText(run.error, 'İşlem başlatılamadı.')}</Note>}

      {v.series && (
        <Section title={`Dizinin kartları · ${v.cards.length}${v.cards.length ? ` (${approved} onaylı)` : ''}`} aside={
          <button type="button" className={`${ghostBtn} !min-h-10 shrink-0 whitespace-nowrap`} onClick={() => setOpen({ card: null })}>
            <Plus className="h-4 w-4" aria-hidden />Yeni kart
          </button>
        }>
          {v.cards.length === 0 && <p className="text-[12px] text-canvas-muted">Bu dizide henüz kart yok. Aşağıdan bu kitabın karakterleri için öneri hazırlatabilirsiniz.</p>}
          <ul className="flex flex-col gap-2">
            {v.cards.map((c) => <CardRow key={c.id} jobId={jobId} card={c} inBook={inBook(c)} onOpen={() => setOpen({ card: c })} />)}
          </ul>
          {v.cards.length > 0 && approved < v.cards.length && (
            <p className="text-[11.5px] text-canvas-muted">Resimlerde yalnız onaylı kartlar kullanılır.</p>
          )}
        </Section>
      )}

      {v.series && v.book.length > 0 && (
        <Section title="Bu kitabın karakterleri">
          <ul className="flex flex-wrap gap-1.5">
            {v.book.map((b) => (
              <li key={b.name}>
                {b.card ? (
                  <button type="button" onClick={() => { const c = v.cards.find((x) => x.id === b.card); if (c) setOpen({ card: c }); }}
                    className={`inline-flex min-h-10 items-center gap-1.5 rounded-full border border-white/70 bg-white/80 px-3 text-[12px] font-bold ${press}`}>
                    <span className={`h-2 w-2 rounded-full ${b.card_status === 'approved' ? 'bg-emerald-500' : 'bg-amber-400'}`} aria-hidden />{b.name}
                  </button>
                ) : (
                  <button type="button" onClick={() => setOpen({ card: null, preset: { name: b.name, species: b.species ?? '' } })}
                    className={`inline-flex min-h-10 items-center gap-1.5 rounded-full border border-dashed border-slate-300 bg-white/50 px-3 text-[12px] font-bold text-canvas-muted ${press}`}>
                    <Plus className="h-3.5 w-3.5" aria-hidden />{b.name}
                  </button>
                )}
              </li>
            ))}
          </ul>
          {missing.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <button type="button" className={gradientBtn} disabled={suggesting || run.isPending}
                onClick={() => run.mutate(() => cardsApi.suggest(jobId, []))}>
                {suggesting ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
                {suggesting ? `Öneriler hazırlanıyor (${TASK_TEXT[suggest!.status]})…` : `Kartı olmayan ${missing.length} karakter için öneri hazırla`}
              </button>
              <p className="text-[11.5px] text-canvas-muted">Zeki AI bu kitabın karakter tariflerinden ve karakter çizimlerinden taslak kart hazırlar; siz düzeltip onaylarsınız.</p>
            </div>
          )}
          {suggest?.status === 'fail' && <Note tone="err">Öneri hazırlanamadı; biraz sonra yeniden deneyin.</Note>}
          {suggest?.status === 'done' && Array.isArray(suggest.result?.made) && (suggest.result!.made as string[]).length > 0 && (
            <Note tone="ok">Taslak kart hazırlandı: {(suggest.result!.made as string[]).join(', ')}. Kontrol edip onaylayın.</Note>
          )}
        </Section>
      )}

      {v.series && (
        <Section title="Bu kitapta karta uymayan görseller" aside={
          <button type="button" className={`${ghostBtn} !min-h-10 shrink-0 whitespace-nowrap`} disabled={checking || run.isPending || approved === 0 || (!!v.busy && !v.busy.error)}
            title={approved === 0 ? 'Önce bir kartı onaylayın' : undefined}
            onClick={() => run.mutate(() => cardsApi.check(jobId))}>
            {checking ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <ScanSearch className="h-4 w-4" aria-hidden />}
            {checking ? 'Denetleniyor…' : 'Denetle'}
          </button>
        }>
          <p className="-mt-1 text-[11.5px] text-canvas-muted">
            Her yeni resim onaylı kartlarla karşılaştırılır; uymayan resim en çok {v.max_retries} kez yeniden çizilir
            (Yönetim → Kitap Tasarım Stüdyosu), sonra burada uyarıyla görünür.
            {v.check.ok ? ` ${v.check.ok} resim karta uyuyor.` : ''}{v.check.pending ? ` ${v.check.pending} resim denetim sırasında.` : ''}
          </p>
          {bad.length === 0 && v.check.unchecked === 0 && <p className="text-[12px] text-canvas-muted">Karta uymayan görsel yok.</p>}
          {bad.length > 0 && (
            <div className="flex items-center gap-1.5 text-[12.5px] font-bold text-rose-700"><AlertTriangle className="h-4 w-4" aria-hidden />{bad.length} resim karakter kartına uymuyor</div>
          )}
          <ul className="flex flex-col gap-2">
            {v.check.items.map((it) => <Mismatch key={`${it.key}-${it.v}`} jobId={jobId} it={it} />)}
          </ul>
          {v.task?.check?.status === 'fail' && <Note tone="err">Denetim yarıda kaldı; «Denetle» ile yeniden başlatın.</Note>}
        </Section>
      )}
    </div>
  );
}
