import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, bookCatalogApi, editorialSearchApi, findCatalogCard, type BookDetail } from '../engine';
import { Loading, Note, Pill, errText, nf } from '../admin/ui';
import { dateTime, num, pct } from '../format';
import { ModuleFrame, Panel } from './kit';
import AskBox from './AskBox';
import Cover from './Cover';

/** Bir kitabın bütün süreçleri tek ekranda: künye, roller, sözleşmeler, proje ve kurul kararı, üretim,
 *  masadaki metin ve prova. Her bölüm kendi modülüne bağlanır. CRM'de kaydı olmayan bölüm hiç çizilmez. */

const money = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });

const tone = (s: string | null): 'ok' | 'warn' | 'err' | 'muted' => {
  const t = (s || '').toLocaleLowerCase('tr');
  if (t.includes('fesih') || t.includes('iptal') || t.startsWith('red')) return 'err';
  if (t.includes('bekle') || t.includes('yenileme') || t.includes('geliştirme')) return 'warn';
  if (t.startsWith('aktif') || t.startsWith('kabul') || t.includes('onaylı') || t === 'aktif') return 'ok';
  return 'muted';
};

function Facts({ b }: { b: BookDetail }) {
  const rows: Array<[string, string | null]> = [
    ['ISBN', b.isbn],
    ['E-kitap ISBN', b.ebookIsbn],
    ['Sayfa', b.pages ? nf.format(b.pages) : null],
    ['Ebat', b.size],
    ['Fiyat', b.price ? `${money.format(b.price)} ₺` : null],
    ['Baskı', b.printNo ? `${nf.format(b.printNo)}. baskı` : null],
    ['Toplam baskı adedi', b.printTotal ? nf.format(b.printTotal) : null],
    ['İlk baskı adedi', b.firstPrint ? nf.format(b.firstPrint) : null],
    ['İlk yayın', b.firstPublished ? dateTime(b.firstPublished) : null],
    ['Son baskı', b.lastPrint ? dateTime(b.lastPrint) : null],
    ['Tür', b.genres || b.shelf],
    ['Orijinal dil', b.originalLanguage],
    ['Telif durumu', b.royaltyState],
    ['Baskı durumu', b.printState],
  ].filter(([, v]) => v) as Array<[string, string]>;
  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Künye</h2>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
        {rows.map(([k, v]) => (
          <div key={k} className="min-w-0">
            <dt className="text-[11px] leading-snug text-canvas-muted">{k}</dt>
            <dd className="break-words text-[12.5px] font-semibold leading-snug">{v}</dd>
          </div>
        ))}
      </dl>
      {b.editorNote && (
        <details className="mt-3 rounded-xl bg-slate-50/80 px-3 py-2">
          <summary className="cursor-pointer select-none text-[12px] font-bold">Editörün kitaba ve yazara dair görüşleri</summary>
          <p className="mt-1.5 whitespace-pre-line text-[12.5px] leading-snug">{b.editorNote}</p>
        </details>
      )}
    </Panel>
  );
}

const SUMMARY_FROM: Record<string, string> = {
  new_kitaptanitimwebmetni: 'CRM · web tanıtım metni',
  new_ozet: 'CRM · kitap özeti',
  new_kitabineskiozeti: 'CRM · eski özet',
  proje: 'CRM · projenin fikri',
};

function About({ b }: { b: BookDetail }) {
  if (!b.summary) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Kitabın konusu</h2>
        <span className="text-[11px] text-canvas-muted">{SUMMARY_FROM[b.summaryFrom ?? ''] ?? 'CRM'}</span>
      </div>
      <div className="mt-2 space-y-1.5 px-1 text-[12.5px] leading-relaxed">
        {b.summary.split('\n').map((line, i) => <p key={i} className="break-words">{line}</p>)}
      </div>
    </Panel>
  );
}

function Roles({ b }: { b: BookDetail }) {
  if (!b.roles.length && !b.illustratorsText && !b.translatorsText) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Emeği geçenler</h2>
        <span className="text-[11px] text-canvas-muted">M7 · M4 · M8</span>
      </div>
      <ul className="mt-2 space-y-1.5">
        {b.roles.map((r) => (
          <li key={r.role} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
            <span className="shrink-0 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{r.role}</span>
            <span className="min-w-0 break-words font-semibold">{r.people.map((p) => p.name).filter(Boolean).join(', ')}</span>
          </li>
        ))}
      </ul>
      {(b.illustratorsText || b.translatorsText) && (
        <p className="mt-2 px-1 text-[11px] leading-snug text-canvas-muted">
          CRM'deki serbest metin alanları: {[b.illustratorsText && `çizer "${b.illustratorsText}"`, b.translatorsText && `tercüme "${b.translatorsText}"`].filter(Boolean).join(' · ')}
        </p>
      )}
    </Panel>
  );
}

function Contracts({ b }: { b: BookDetail }) {
  if (!b.contracts.length) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Sözleşmeler</h2>
        <Link to="/telif-sozlesme" className="text-[11.5px] font-bold text-canvas-violet underline">
          M6 Telif & Sözleşme
        </Link>
      </div>
      <ul className="mt-2 space-y-1.5">
        {b.contracts.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
            <span className="min-w-0">
              <span className="block font-mono text-[12px] font-semibold">{c.no || '—'}</span>
              <span className="block text-[11px] text-canvas-muted">
                {[c.kind, c.royalty != null ? `telif ${pct(c.royalty, 0)}` : null, c.start || c.end ? `${dateTime(c.start)} – ${dateTime(c.end)}` : null].filter(Boolean).join(' · ')}
              </span>
            </span>
            <span className="flex shrink-0 gap-1.5">
              {c.daysLeft != null && c.daysLeft >= 0 && c.daysLeft <= 60 && <Pill tone="err">{nf.format(c.daysLeft)} gün</Pill>}
              {c.status && <Pill tone={tone(c.status)}>{c.status}</Pill>}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Journey({ b }: { b: BookDetail }) {
  if (!b.projects.length && !b.board.length && !b.production.length) return null;
  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Yayın süreci</h2>

      {b.projects.length > 0 && (
        <section className="mt-2">
          <h3 className="flex items-baseline gap-2 px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
            Proje
            <Link to="/editor-atama" className="font-bold normal-case tracking-normal text-canvas-violet underline">
              M2
            </Link>
          </h3>
          <ul className="mt-1 space-y-1.5">
            {b.projects.map((p) => (
              <li key={p.id} className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0 break-words font-semibold">{p.name}</span>
                  {p.status && <Pill tone={tone(p.status)}>{p.status}</Pill>}
                </div>
                <div className="mt-0.5 text-[11px] text-canvas-muted">
                  {[p.editor ? `Editör: ${p.editor}` : 'Editör atanmamış', p.text && `Metin: ${p.text}`, p.stage, p.on && dateTime(p.on)].filter(Boolean).join(' · ')}
                </div>
                {p.idea && p.idea !== b.summary && <p className="mt-1 whitespace-pre-line text-[12px] leading-snug">{p.idea}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {b.board.length > 0 && (
        <section className="mt-3">
          <h3 className="flex items-baseline gap-2 px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
            Yayın kurulu
            <Link to="/yayin-kurulu" className="font-bold normal-case tracking-normal text-canvas-violet underline">
              M1
            </Link>
          </h3>
          <ul className="mt-1 space-y-1.5">
            {b.board.map((d) => (
              <li key={d.id} className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-[11.5px] tabular-nums">{dateTime(d.date)}</span>
                  {d.decision && <Pill tone={tone(d.decision)}>{d.decision}</Pill>}
                </div>
                {d.note && <p className="mt-1 whitespace-pre-line leading-snug">{d.note}</p>}
                {(d.royalty || d.printRun) && (
                  <p className="mt-0.5 text-[11px] text-canvas-muted">
                    {[d.royalty ? `önerilen telif ${pct(d.royalty, 0)}` : null, d.printRun ? `baskı adedi ${d.printRun}` : null].filter(Boolean).join(' · ')}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {b.production.length > 0 && (
        <section className="mt-3">
          <h3 className="px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Üretim</h3>
          <ul className="mt-1 space-y-1.5">
            {b.production.map((p) => (
              <li key={p.id} className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-mono text-[11.5px] tabular-nums">{dateTime(p.on)}</span>
                  {p.status && <Pill tone={tone(p.status)}>{p.status}</Pill>}
                </div>
                <div className="mt-0.5 text-[11px] text-canvas-muted">
                  {[p.editor && `Sorumlu editör: ${p.editor}`, p.designer && `Grafiker: ${p.designer}`, p.firstText && `ilk metin ${dateTime(p.firstText)}`, p.delivery && `teslim ${dateTime(p.delivery)}`]
                    .filter(Boolean)
                    .join(' · ') || 'Ayrıntı girilmemiş'}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Panel>
  );
}

function Desk({ b }: { b: BookDetail }) {
  if (!b.desk.length) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Masadaki metin ve prova</h2>
        <span className="text-[11px] text-canvas-muted">M3 · M5</span>
      </div>
      <ul className="mt-2 space-y-1.5">
        {b.desk.map((w) => (
          <li key={w.id} className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="min-w-0 break-words font-semibold">{w.title}</span>
              <span className="flex shrink-0 gap-1.5">
                <Link to="/redaksiyon" className="text-[11.5px] font-bold text-canvas-violet underline">
                  Redaksiyon
                </Link>
                <Link to="/son-okuma" className="text-[11.5px] font-bold text-canvas-violet underline">
                  Son okuma
                </Link>
              </span>
            </div>
            <div className="mt-0.5 text-[11px] text-canvas-muted">
              {w.manuscript ? `Metin v${w.manuscript.version} · ${nf.format(w.chapters.approved)}/${nf.format(w.chapters.total)} bölüm onaylı` : 'Metin yüklenmedi'}
              {w.proof ? ` · Prova v${w.proof.version} · ${nf.format(w.signatures.signed)}/${nf.format(w.signatures.total)} imza` : ' · Prova yüklenmedi'}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default function BookScreen() {
  const { id = '' } = useParams();
  const q = useQuery({ queryKey: ['editorial', 'book', id], queryFn: () => editorialSearchApi.book(id), enabled: ENGINE_ENABLED && !!id });
  const b = q.data;
  // Kapak motorun kataloğundan: CRM'deki ad kataloğa tam eşleşirse (motor adı ya da yayınevinin adı) kart kimliğiyle çekilir;
  // eşleşmezse hiçbir yer tutucu çizilmez.
  const catalog = useQuery({ queryKey: ['editorial', 'bookCatalog'], queryFn: bookCatalogApi.list, enabled: ENGINE_ENABLED && !!b, staleTime: 5 * 60_000 });
  const cover = findCatalogCard(catalog.data?.items, b?.title);
  const err = errText(q.error, 'Kitap okunamadı.');
  const empty = b && !b.roles.length && !b.contracts.length && !b.projects.length && !b.board.length && !b.production.length && !b.desk.length;

  return (
    <ModuleFrame
      route="/kitap"
      code="Kitap"
      crumb={b?.title || 'Kitap'}
      title={b?.title || 'Kitap'}
      lead="Bu kitabın CRM'deki ve editoryal masadaki bütün kayıtları: künye, emeği geçenler, sözleşmeler, proje ve kurul kararı, üretim, metin ve prova."
      source={b?.isbn ? `ISBN ${b.isbn}` : 'Kitap kartı'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {q.isLoading && <Panel><Loading /></Panel>}

      {b && (
        <>
          <div className="flex items-start gap-3 px-1">
            {cover?.cover && <Cover id={cover.id} alt={`${b.title || 'Kitap'} kapağı`} className="h-[104px] w-[72px] sm:h-[140px] sm:w-24" />}
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              {b.status && <Pill tone={tone(b.status)}>{b.status}</Pill>}
              {b.printState && <Pill tone="muted">{b.printState}</Pill>}
              {b.pages ? <span className="text-[12px] text-canvas-muted">{num(b.pages, 0)} sayfa</span> : null}
              {b.firstPublished && <span className="text-[12px] text-canvas-muted">İlk yayın {dateTime(b.firstPublished)}</span>}
            </div>
          </div>
          <Facts b={b} />
          <About b={b} />
          <AskBox bookKey={b.id} bookTitle={b.title || undefined} />
          <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
            <div className="space-y-3 lg:space-y-4">
              <Roles b={b} />
              <Contracts b={b} />
            </div>
            <div className="space-y-3 lg:space-y-4">
              <Journey b={b} />
              <Desk b={b} />
            </div>
          </div>
          {empty && <Note tone="info">Bu kitabın künyesi dışında CRM'de kaydı yok: rol, sözleşme, proje, kurul kararı ve üretim kaydı bulunamadı.</Note>}
        </>
      )}
    </ModuleFrame>
  );
}
