import { useEffect, useId, useState, type ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { studioApi, type StudioBookEdit, type StudioJob, type StudioKunyeResult, type StudioKunyeRow } from '../../engine';
import { Note, errText } from '../../admin/ui';
import { Panel } from '../kit';
import { Img, ghostBtn, gradientBtn } from './shared';

/** Künye: sistem kitabın kendi künyesinden (alıntıyla) doldurur; kaynağı olmayan alan «—» kalır ve ön baskı
 *  denetimi durur. Editör eksik ya da değişecek alanı burada yazar; kaydedince iç sayfa yeniden dizilir.
 *  Kitap adı ve yazar da buradan düzeltilir: kayıt el yazmasının kendisini değiştirir, kapak, iç kapak, künye ve
 *  dizgi yeni değerle yeniden kurulur (resim yeniden çizilmez). Kaynağı her alanın altında: yayınevi kaydı, Word
 *  dosyası, okunmuş kitap ya da editörün adı ve tarihi. Hareket yok: durum metinle anlatılır. */

const CRM_FIELD_TR: Record<string, string> = {
  author: 'yazar', illustrator: 'çizer', ISBN: 'ISBN', STOCK_CODE: 'stok kodu', CRM_SUMMARY: 'arka kapak yazısı',
};

function when(at: number | null | undefined) {
  if (!at) return '';
  return new Date(at * 1000).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' });
}

function SourceLine({ row }: { row: StudioKunyeRow }) {
  if (row.edited) {
    return (
      <span className="block text-[11px] leading-snug text-canvas-muted">
        {row.source}{row.edited.at ? `, ${when(row.edited.at)}` : ''}
        {row.edited.was ? <> · önceki: <span className="break-words">«{row.edited.was}»</span></> : null}
      </span>
    );
  }
  if (!row.source) return null;
  return <span className="block text-[11px] leading-snug text-canvas-muted">{row.source}</span>;
}

/** Kitap adı / yazar: tam genişlik, telefonda 16 px (odakta sayfa büyümesin). */
function BookField({ row, value, onChange, error, extra }: {
  row: StudioKunyeRow; value: string; onChange: (v: string) => void; error?: string; extra?: ReactNode;
}) {
  const id = useId();
  const label = row.field === 'title' ? 'Kitap adı' : 'Yazar';
  return (
    <div className={`rounded-xl px-2.5 py-2 ${row.missing || error ? 'bg-amber-50/80' : 'bg-white/70'}`}>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-[11.5px] font-bold text-canvas-muted">{label}</label>
        {extra}
      </div>
      <input
        id={id}
        value={value}
        placeholder={row.field === 'title' ? 'Kitabın adı' : row.none ? 'Yazarsız basılacak' : 'Eksik — yazın'}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-err` : undefined}
        className="mt-1 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-[16px] font-bold outline-none focus:border-canvas-violet sm:text-[13.5px]"
      />
      {error && <span id={`${id}-err`} className="mt-1 block text-[11.5px] font-semibold text-red-700">{error}</span>}
      <div className="mt-1 px-0.5"><SourceLine row={row} /></div>
    </div>
  );
}

export default function KunyePanel({ jobId, front, rev = '', hasCover = false }: {
  jobId: string; front: NonNullable<StudioJob['front']>; rev?: string; hasCover?: boolean;
}) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [book, setBook] = useState<StudioBookEdit>({});
  const [done, setDone] = useState<StudioKunyeResult | null>(null);
  useEffect(() => { setEdit({}); setBook({}); }, [front]);
  const save = useMutation({
    mutationFn: (v: { fields: Record<string, string>; book: StudioBookEdit }) => studioApi.kunye(jobId, v.fields, v.book),
    onMutate: () => setDone(null),
    onSuccess: async (r, v) => {
      await qc.invalidateQueries({ queryKey: ['studio', 'job', jobId] });
      setDone(Object.keys(v.book).length ? r : null);
    },
  });
  const bookRows = front.rows.filter((r) => r.field);
  const rows = front.rows.filter((r) => !r.field);
  const titleRow = bookRows.find((r) => r.field === 'title');
  const authorRow = bookRows.find((r) => r.field === 'author');
  const missing = front.rows.filter((r) => r.missing).length;
  const titleValue = book.title ?? (titleRow && !titleRow.missing ? titleRow.value : '');
  const authorValue = book.author ?? (authorRow && !authorRow.missing ? authorRow.value : '');
  const titleError = book.title !== undefined && !book.title.trim() ? 'Kitap adı boş olamaz.' : undefined;
  const bookDirty = Object.keys(book).length > 0;
  const dirty = Object.keys(edit).length > 0 || bookDirty;
  const rebuilding = save.isPending && bookDirty;

  const setField = (f: 'title' | 'author', v: string) => {
    const row = f === 'title' ? titleRow : authorRow;
    const orig = row && !row.missing ? row.value : '';
    setBook((b) => {
      const next = { ...b };
      if (v === orig) delete next[f];
      else next[f] = v;
      return next;
    });
  };

  const crmNote = (() => {
    const c = done?.crm;
    if (!c) return null;
    if (c.filled.length) return `Yayınevi kaydında bu adla kitap bulundu; boş alanlar dolduruldu: ${c.filled.map((k) => CRM_FIELD_TR[k] ?? k).join(', ')}.`;
    if (c.match === 'kitap adı' && !c.linked) return 'Bu ad yayınevi kaydında başka bir kitaba denk geliyor; bilgiler karıştırılmadı.';
    if (c.match === 'kitap adı') return null;
    if (c.match === 'denenemedi') return 'Yayınevi kaydına şu an ulaşılamadı; alanlar elle tamamlanabilir.';
    return 'Yayınevi kaydında bu adla birebir eşleşen kitap yok; eksik alanları elle tamamlayın.';
  })();

  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Künye</h2>
        <span className={`text-[12px] font-bold ${missing ? 'text-amber-700' : 'text-emerald-700'}`}>
          {missing ? `${missing} alan eksik` : 'Tam'}
        </span>
      </div>
      <p className="text-[11.5px] text-canvas-muted">Kitabın kendi künyesinden alındı; kaynağı olmayan alanı siz yazın. Resim ve tasarım satırları sistemindir.</p>

      {titleRow && authorRow && (
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          <BookField row={titleRow} value={titleValue} onChange={(v) => setField('title', v)} error={titleError} />
          <BookField
            row={authorRow}
            value={authorValue}
            onChange={(v) => setField('author', v)}
            extra={(authorRow.missing && book.author === undefined) ? (
              <button type="button" className="text-[11.5px] font-bold text-canvas-violet underline-offset-2 hover:underline"
                onClick={() => setBook((b) => ({ ...b, author: '' }))}>
                Yazarsız bas
              </button>
            ) : null}
          />
          <p className="text-[11px] leading-snug text-canvas-muted md:col-span-2">
            Kitap adı ve yazar kapağa, sırta, iç kapağa, künyeye ve e-kitap bilgisine yazılır; değişince bunlar yeniden dizilir, resimler yeniden çizilmez.
            {' '}Kitap adı değişince yayınevi kaydında aynı adla kitap aranır, bulunursa yalnız boş alanlar oradan dolar.
          </p>
        </div>
      )}

      {save.error && <div className="mt-2"><Note tone="err">{errText(save.error, 'Künye kaydedilemedi.')}</Note></div>}
      <dl className="mt-2 grid gap-1.5">
        {rows.map((r) => (
          <div key={r.label} className={`grid grid-cols-[minmax(92px,130px)_minmax(0,1fr)] items-center gap-2 rounded-xl px-2.5 py-1.5 ${r.missing ? 'bg-amber-50/80' : 'bg-white/70'}`}>
            <dt className="text-[11.5px] font-bold text-canvas-muted">{r.label}</dt>
            <dd className="min-w-0">
              {r.editable ? (
                <input
                  value={edit[r.label] ?? (r.missing ? '' : r.value)}
                  placeholder={r.missing ? 'Eksik — yazın' : ''}
                  onChange={(e) => setEdit((x) => ({ ...x, [r.label]: e.target.value }))}
                  aria-label={r.label}
                  className="w-full rounded-lg border border-transparent bg-transparent px-1.5 py-0.5 text-[16px] outline-none focus:border-canvas-violet focus:bg-white sm:text-[12.5px]"
                />
              ) : (
                <span className="block truncate px-1.5 text-[12.5px]">{r.value}</span>
              )}
              {r.source && !r.missing && <span className="block px-1.5 text-[10.5px] text-canvas-muted">{r.source}</span>}
            </dd>
          </div>
        ))}
      </dl>

      <div aria-live="polite" className="mt-3 flex flex-col gap-2">
        {rebuilding && <Note tone="info">Kapak ve sayfalar yeniden diziliyor… Bu birkaç saniye sürebilir.</Note>}
        {done && !save.isPending && (
          <div className="rounded-2xl bg-emerald-50/70 p-2.5">
            <p className="text-[12px] font-semibold text-emerald-800">
              Kapak ve sayfalar yeni bilgiyle dizildi: «{done.book?.title}»{done.book?.author ? ` · ${done.book.author}` : ' · yazarsız'}.
            </p>
            {crmNote && <p className="mt-1 text-[11.5px] text-emerald-900/80">{crmNote}</p>}
            <div className="mt-2 flex flex-wrap items-end gap-2">
              {hasCover && (
                <figure className="min-w-0 max-w-full flex-1 basis-[220px] sm:max-w-[360px]">
                  <Img src={studioApi.coverUrl(jobId, 720, rev)} alt="Yenilenen kapak açılımı" fallback="Kapak"
                    className="w-full rounded-lg border border-slate-200 bg-white object-contain" />
                  <figcaption className="mt-0.5 text-[10.5px] text-canvas-muted">Kapak</figcaption>
                </figure>
              )}
              {[1, 2].map((n) => (
                <figure key={n} className="w-[84px] shrink-0">
                  <Img src={studioApi.pageUrl(jobId, n, 168, rev)} alt={n === 1 ? 'Yenilenen iç kapak' : 'Yenilenen künye sayfası'} fallback={`s. ${n}`}
                    className="aspect-[171/231] w-full rounded-lg border border-slate-200 bg-white object-cover" />
                  <figcaption className="mt-0.5 text-[10.5px] text-canvas-muted">{n === 1 ? 'İç kapak' : 'Künye'}</figcaption>
                </figure>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap justify-end gap-2">
        {dirty && !save.isPending && (
          <button type="button" className={ghostBtn} onClick={() => { setEdit({}); setBook({}); }}>Vazgeç</button>
        )}
        <button type="button" className={gradientBtn} disabled={!dirty || save.isPending || !!titleError}
          onClick={() => save.mutate({ fields: edit, book })}>
          {save.isPending ? (bookDirty ? 'Yeniden diziliyor…' : 'Kaydediliyor…') : 'Künyeyi kaydet'}
        </button>
      </div>
    </Panel>
  );
}
