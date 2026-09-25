import { useEffect, useId, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, ImagePlus, Languages, Loader2, Palette, Plus, Star, Trash2, Upload, X } from 'lucide-react';
import { studioApi } from '../../../engine';
import { Note, errText, field } from '../../../admin/ui';
import { ConfirmDialog } from '../dialogs';
import { Img, ghostBtn, gradientBtn, press } from '../shared';
import { ColorChips, Section } from '../elements/controls';
import { CardsError, blankCard, cardsApi, cardsKey, toInput, type Candidate, type Card, type CardInput, type CardsView, type Part } from './api';

/** Kart düzenleyici: ad, tür, yaş, görünüş (Türkçe + modele giden), sabit renkler, kitap paletindeki rengi,
 *  kıyafetler, referans görseller, onay. Kaydedilen kart taslağa döner; resimlerde yalnız onaylı kart kullanılır.
 *  Çakışmada (başka bir kart aynı anda değişti) yazım güncel sürümle bir kez yeniden denenir; aynı kart
 *  değiştiyse editöre söylenir, yazdığı kaybolmaz. */

const PART_ORDER: Part[] = ['hair', 'fur', 'eyes', 'skin', 'outfit', 'accent'];
const label = 'text-[12px] font-bold text-canvas-ink';

function hexOk(v: string) {
  return /^#[0-9a-fA-F]{6}$/.test(v);
}

function ColorField({ name, value, onChange }: { name: string; value: string | undefined; onChange: (v: string | undefined) => void }) {
  const id = useId();
  const [text, setText] = useState(value ?? '');
  useEffect(() => setText(value ?? ''), [value]);
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-[12px] font-bold">{name}</label>
      <div className="flex min-w-0 items-center gap-2">
        <input type="color" aria-label={`${name} rengi seç`} value={value && hexOk(value) ? value : '#FFFFFF'}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-10 w-11 shrink-0 cursor-pointer rounded-lg border border-slate-200 bg-white p-0.5" />
        <input id={id} value={text} placeholder="#RRGGBB" maxLength={7} spellCheck={false}
          onChange={(e) => { setText(e.target.value); if (hexOk(e.target.value)) onChange(e.target.value.toUpperCase()); }}
          onBlur={() => { if (!text) onChange(undefined); else if (!hexOk(text)) setText(value ?? ''); }}
          className={`${field} min-w-0 flex-1 font-mono`} />
        {value && (
          <button type="button" onClick={() => onChange(undefined)} aria-label={`${name} rengini kaldır`}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-canvas-muted hover:bg-slate-100 ${press}`}>
            <X className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
    </div>
  );
}

export default function CardEditor({ jobId, view, card, preset, onDone }: {
  jobId: string;
  view: CardsView;
  card: Card | null;              // null: yeni kart
  preset?: { name: string; species: string };
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<CardInput>(() => (card ? toInput(card) : blankCard(preset?.name, preset?.species)));
  const [baseline, setBaseline] = useState<CardInput | null>(() => (card ? toInput(card) : null));
  const [aliases, setAliases] = useState((card?.aliases ?? []).join(', '));
  const [confirmDel, setConfirmDel] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'ok' | 'warn' | 'err'; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const live = card ? view.cards.find((c) => c.id === card.id) ?? card : null;
  const input = (): CardInput => ({ ...draft, aliases: aliases.split(',').map((a) => a.trim()).filter(Boolean) });
  const dirty = !baseline || JSON.stringify(input()) !== JSON.stringify(baseline);
  const adopt = (c: Card) => {
    const b = toInput(c);
    setBaseline(b);
    setDraft(b);
    setAliases((c.aliases ?? []).join(', '));
  };

  // Sunucudaki kart değişirse (ör. çeviri bitti) ve editör henüz dokunmadıysa taslak tazelenir; dokunduysa korunur.
  useEffect(() => {
    if (live && !dirty) adopt(live);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live?.version]);

  const refresh = () => qc.invalidateQueries({ queryKey: cardsKey(jobId) });
  const set = <K extends keyof CardInput>(k: K, v: CardInput[K]) => setDraft((d) => ({ ...d, [k]: v }));

  const save = useMutation({
    mutationFn: async () => {
      const body = input();
      const once = (rev: number) => (card ? cardsApi.update(jobId, card.id, rev, body) : cardsApi.create(jobId, rev, body));
      try {
        return await once(view.rev);
      } catch (e) {
        if (!(e instanceof CardsError && e.code === 'STALE')) throw e;
        const fresh = await cardsApi.view(jobId);
        const now = card && fresh.cards.find((c) => c.id === card.id);
        if (card && (!now || now.version !== live?.version)) {
          qc.setQueryData(cardsKey(jobId), fresh);
          throw new Error('Bu kart başka bir yerde değişti. Yazdıklarınız duruyor; güncel kartı kontrol edip yeniden kaydedin.');
        }
        return once(fresh.rev);            // başka bir kart değişmişti: aynı yazım güncel sürümle
      }
    },
    onSuccess: (r) => {
      adopt(r.card);
      setMsg({ tone: 'ok', text: r.card.en_stale ? 'Kaydedildi. Türkçe tarif değişti; modele giden tarifi yenileyin.' : 'Kaydedildi. Resimlerde kullanılması için onaylayın.' });
      refresh();
      if (!card) onDone();
    },
    onError: (e) => setMsg({ tone: 'err', text: errText(e, 'Kaydedilemedi.') ?? '' }),
  });
  const act = useMutation({
    mutationFn: (f: () => Promise<unknown>) => f(),
    onSuccess: () => { setMsg(null); refresh(); },
    onError: (e) => setMsg({ tone: 'err', text: errText(e, 'İşlem yapılamadı.') ?? '' }),
  });
  const del = useMutation({
    mutationFn: () => cardsApi.remove(jobId, card!.id, view.rev),
    onSuccess: () => { refresh(); onDone(); },
    onError: (e) => setMsg({ tone: 'err', text: errText(e, 'Silinemedi.') ?? '' }),
  });

  const translating = view.task?.translate && ['queued', 'running'].includes(view.task.translate.status) && view.task.translate.card === card?.id;
  const book = view.book.find((b) => b.card === card?.id || b.name.toLocaleLowerCase('tr') === draft.name.toLocaleLowerCase('tr'));
  const palette = (view.palette.colors ?? []).map((c) => ({ hex: c.hex, name: c.name }));
  const inBookColor = book ? view.palette.characters?.[book.name] : undefined;
  const parts = PART_ORDER.filter((p) => view.parts[p]);
  const busyAct = act.isPending || save.isPending;

  const candidates = (book?.candidates ?? []).filter((c) => !(live?.refs ?? []).some((r) =>
    c.from === 'sheet' ? r.source.kind === 'sheet' && r.source.job === jobId : r.source.kind === 'art' && r.source.key === c.key && r.source.v === c.v));
  const candUrl = (c: Candidate) => (c.from === 'sheet' ? studioApi.characterUrl(jobId, c.i, 200) : studioApi.artUrl(jobId, c.key, c.v, 240));

  return (
    <div className="flex flex-col gap-4">
      {msg && <Note tone={msg.tone}>{msg.text}</Note>}
      {view.task?.translate?.status === 'fail' && view.task.translate.card === card?.id && (
        <Note tone="err">Modele giden tarif yenilenemedi; biraz sonra yeniden deneyin ya da elle düzeltin.</Note>
      )}
      {live?.status === 'approved' && !dirty && (
        <Note tone="ok">Onaylı{live.approved_by ? ` · ${live.approved_by}` : ''} — dizinin her kitabında bu kart kullanılıyor.</Note>
      )}

      <Section title="Kimlik">
        <label className="flex flex-col gap-1.5">
          <span className={label}>Ad</span>
          <input className={field} value={draft.name} onChange={(e) => set('name', e.target.value)} maxLength={80} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={label}>Diğer adları <span className="font-normal text-canvas-muted">(virgülle)</span></span>
          <input className={field} value={aliases} onChange={(e) => setAliases(e.target.value)} placeholder="Ör. Elifçik" />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className={label}>Tür</span>
            <select className={field} value={draft.kind} onChange={(e) => set('kind', e.target.value)}>
              {view.kinds.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className={label}>Yaş</span>
            <input className={field} value={draft.age} onChange={(e) => set('age', e.target.value)} maxLength={30} placeholder="Ör. 7, yetişkin" />
          </label>
        </div>
      </Section>

      <Section title="Görünüş">
        <label className="flex flex-col gap-1.5">
          <span className={label}>Tarif</span>
          <textarea className={field} rows={4} value={draft.look_tr} onChange={(e) => set('look_tr', e.target.value)}
            placeholder="Beden, yüz, saç, göz, ayırt edici işaretler. Kıyafet aşağıda ayrı yazılır." />
        </label>
        <details className="rounded-xl border border-slate-200/80 bg-white/60 px-3 py-2" open={!!live?.en_stale || !draft.look_en}>
          <summary className="flex min-h-10 cursor-pointer items-center text-[12px] font-bold">Resim üretiminde kullanılan tarif</summary>
          <p className="mb-2 text-[11.5px] text-canvas-muted">Görsel model İngilizce tarifle çalışır. Türkçe tarifi değiştirdiyseniz «Türkçeden yenile» deyin ya da buradan düzeltin.</p>
          <label className="flex flex-col gap-1.5">
            <span className={label}>Tür (model için)</span>
            <input className={field} value={draft.species_en} onChange={(e) => set('species_en', e.target.value)} placeholder="little girl, baby wombat…" />
          </label>
          <textarea className={`${field} mt-2`} rows={3} value={draft.look_en} onChange={(e) => set('look_en', e.target.value)} aria-label="Modele giden tarif" />
          {live?.en_stale && <p className="mt-1.5 text-[11.5px] font-semibold text-amber-700">Türkçe tarif değişti; bu tarif eski kalmış olabilir.</p>}
          {card && (
            <button type="button" className={`${ghostBtn} mt-2`} disabled={busyAct || dirty || !!translating}
              title={dirty ? 'Önce kaydedin' : undefined}
              onClick={() => act.mutate(() => cardsApi.translate(jobId, card.id))}>
              {translating ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Languages className="h-4 w-4" aria-hidden />}
              {translating ? 'Yenileniyor…' : 'Türkçeden yenile'}
            </button>
          )}
        </details>
      </Section>

      <Section title="Sabit renkler">
        <p className="-mt-1 text-[11.5px] text-canvas-muted">Her resimde adıyla ve renk koduyla istenir. Tarifte olmayan alanı boş bırakın.</p>
        <div className="grid gap-2.5 sm:grid-cols-2">
          {parts.map((p) => (
            <ColorField key={p} name={view.parts[p]} value={draft.colors[p]}
              onChange={(v) => set('colors', Object.fromEntries(Object.entries({ ...draft.colors, [p]: v }).filter(([, x]) => x)) as CardInput['colors'])} />
          ))}
        </div>
      </Section>

      <Section title="Kitap paletindeki rengi" aside={
        card && draft.palette_color && inBookColor?.toUpperCase() !== draft.palette_color.toUpperCase() ? (
          <button type="button" className={`${ghostBtn} !min-h-10 shrink-0 whitespace-nowrap`} disabled={busyAct || dirty} title={dirty ? 'Önce kaydedin' : undefined}
            onClick={() => act.mutate(() => cardsApi.applyPalette(jobId, card.id))}>
            <Palette className="h-4 w-4" aria-hidden />Bu kitaba uygula
          </button>
        ) : undefined
      }>
        <p className="-mt-1 text-[11.5px] text-canvas-muted">
          Karakterin konuşmaları ve adı sayfada bu renkle yazılır.
          {inBookColor ? ` Bu kitapta şu an ${inBookColor}.` : ''}
        </p>
        {palette.length > 0
          ? <ColorChips label="Kitap paletindeki rengi" value={draft.palette_color} onChange={(v) => set('palette_color', v)} swatches={palette} />
          : <ColorField name="Renk" value={draft.palette_color ?? undefined} onChange={(v) => set('palette_color', v ?? null)} />}
      </Section>

      <Section title="Kıyafetler" aside={
        <button type="button" className={`${ghostBtn} !min-h-10 shrink-0 whitespace-nowrap`} onClick={() => set('outfits', [...draft.outfits,
          { name: '', look_tr: '', look_en: '', color: null, default: draft.outfits.length === 0 }])}>
          <Plus className="h-4 w-4" aria-hidden />Ekle
        </button>
      }>
        {draft.outfits.length === 0 && <p className="text-[12px] text-canvas-muted">Kıyafet yok; sahne işin kendi kıyafet tarifini kullanır.</p>}
        <ul className="flex flex-col gap-2">
          {draft.outfits.map((o, i) => {
            const upd = (patch: Partial<typeof o>) => set('outfits', draft.outfits.map((x, j) => (j === i ? { ...x, ...patch } : patch.default ? { ...x, default: false } : x)));
            return (
              <li key={o.id ?? `yeni-${i}`} className="flex flex-col gap-2 rounded-xl border border-slate-200/80 bg-white/60 p-2.5">
                <div className="flex items-center gap-2">
                  <input className={`${field} min-w-0 flex-1`} value={o.name} onChange={(e) => upd({ name: e.target.value })} placeholder="Ad (ör. gündelik)" aria-label="Kıyafet adı" />
                  <label className="inline-flex min-h-10 shrink-0 items-center gap-1.5 text-[12px] font-bold">
                    <input type="radio" name={`dflt-${card?.id ?? 'yeni'}`} checked={o.default} onChange={() => upd({ default: true })} className="h-4 w-4 accent-canvas-violet" />
                    Varsayılan
                  </label>
                  <button type="button" aria-label={`${o.name || 'kıyafeti'} kaldır`}
                    onClick={() => set('outfits', draft.outfits.filter((_, j) => j !== i))}
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-canvas-muted hover:bg-slate-100 ${press}`}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                </div>
                <textarea className={field} rows={2} value={o.look_tr} onChange={(e) => upd({ look_tr: e.target.value })} placeholder="Tarif" aria-label="Kıyafet tarifi" />
                <details>
                  <summary className="flex min-h-9 cursor-pointer items-center text-[11.5px] font-bold text-canvas-muted">Resim üretiminde kullanılan tarif</summary>
                  <textarea className={field} rows={2} value={o.look_en} onChange={(e) => upd({ look_en: e.target.value })} aria-label="Kıyafetin modele giden tarifi" />
                </details>
                <ColorField name="Ana renk" value={o.color ?? undefined} onChange={(v) => upd({ color: v ?? null })} />
              </li>
            );
          })}
        </ul>
      </Section>

      {card && live && (
        <Section title="Referans görseller" aside={
          <button type="button" className={`${ghostBtn} !min-h-10 shrink-0 whitespace-nowrap`} disabled={busyAct} onClick={() => fileRef.current?.click()}>
            <Upload className="h-4 w-4" aria-hidden />Yükle
          </button>
        }>
          <input ref={fileRef} type="file" accept="image/*" className="sr-only" tabIndex={-1} aria-hidden
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) act.mutate(() => cardsApi.upload(jobId, card.id, f)); }} />
          <p className="-mt-1 text-[11.5px] text-canvas-muted">Yıldızlı görsel her resimde karakterin referansı olarak kullanılır; tercihen düz zeminde, bütün beden.</p>
          {live.refs.length === 0 && <Note tone="warn">Referans görsel yok: karakter yalnız tarif ve renklerle çizilir, resimler karta karşı denetlenemez.</Note>}
          <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {live.refs.map((r) => (
              <li key={r.id} className="flex min-w-0 flex-col gap-1">
                <div className={`relative overflow-hidden rounded-xl border bg-white ${r.primary ? 'border-canvas-violet ring-2 ring-canvas-violet/30' : 'border-slate-200'}`}>
                  <Img src={cardsApi.refUrl(jobId, card.id, r.id, 240)} alt={`${live.name} referansı`} fallback="görsel" className="aspect-square w-full object-contain" />
                  {r.primary && <span className="absolute left-1 top-1 inline-flex items-center gap-0.5 rounded bg-canvas-violet px-1 text-[10px] font-bold text-white"><Star className="h-3 w-3" aria-hidden />Birincil</span>}
                </div>
                <div className="flex justify-between gap-1">
                  <button type="button" disabled={r.primary || busyAct} aria-label="Birincil yap" title="Birincil yap"
                    onClick={() => act.mutate(() => cardsApi.primary(jobId, card.id, r.id))}
                    className={`flex h-10 flex-1 items-center justify-center rounded-lg bg-white/80 disabled:opacity-40 ${press}`}>
                    <Star className="h-4 w-4" aria-hidden />
                  </button>
                  <button type="button" disabled={busyAct} aria-label="Kaldır" title="Kaldır"
                    onClick={() => act.mutate(() => cardsApi.removeRef(jobId, card.id, r.id))}
                    className={`flex h-10 flex-1 items-center justify-center rounded-lg bg-white/80 text-rose-600 disabled:opacity-40 ${press}`}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                </div>
              </li>
            ))}
          </ul>
          {candidates.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <span className={label}>Bu kitaptan ekle</span>
              <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                {candidates.map((c) => (
                  <li key={c.from === 'sheet' ? 'sheet' : `${c.key}-${c.v}`}>
                    <button type="button" disabled={busyAct} onClick={() => act.mutate(() => cardsApi.refFromJob(jobId, card.id, c))}
                      className={`group relative block w-full overflow-hidden rounded-xl border border-slate-200 bg-white ${press}`}
                      aria-label={c.from === 'sheet' ? 'Karakter çizimini referans yap' : `Sayfa resmini (v${c.v}) referans yap`}>
                      <Img src={candUrl(c)} alt="" fallback="görsel" className="aspect-square w-full object-cover" />
                      <span className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-1 bg-black/55 py-0.5 text-[10.5px] font-bold text-white">
                        <ImagePlus className="h-3 w-3" aria-hidden />{c.from === 'sheet' ? 'Karakter çizimi' : 'Onaylı resim'}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Section>
      )}

      <div className="sticky bottom-0 -mx-4 flex gap-2 border-t border-slate-200/70 bg-white/85 px-4 py-3 backdrop-blur">
        <button type="button" className={`${gradientBtn} min-w-0 flex-1 whitespace-nowrap`} disabled={!dirty || busyAct || !draft.name.trim()} onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Check className="h-4 w-4" aria-hidden />}
          {card ? 'Kaydet' : 'Kartı oluştur'}
        </button>
        {card && live && (
          <button type="button" className={`${ghostBtn} shrink-0 whitespace-nowrap !px-3`} disabled={busyAct || dirty || (live.status !== 'approved' && (!!live.en_stale || !live.look_en))}
            title={dirty ? 'Önce kaydedin' : live.en_stale ? 'Önce modele giden tarifi yenileyin' : undefined}
            onClick={() => act.mutate(() => cardsApi.approve(jobId, card.id, live.status !== 'approved'))}>
            {live.status === 'approved' ? 'Onayı kaldır' : 'Onayla'}
          </button>
        )}
        {card && (
          <button type="button" className={`${ghostBtn} shrink-0 !px-3 !text-rose-600`} disabled={busyAct} onClick={() => setConfirmDel(true)} aria-label="Kartı sil">
            <Trash2 className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
      <ConfirmDialog open={confirmDel} danger title={`«${card?.name}» kartı silinsin mi?`}
        body="Kart dizinin bütün kitaplarından kalkar; eski hâli sürüm geçmişinde durur. Üretilmiş resimler silinmez."
        confirm="Sil" onClose={() => setConfirmDel(false)} onConfirm={() => { setConfirmDel(false); del.mutate(); }} />
    </div>
  );
}
