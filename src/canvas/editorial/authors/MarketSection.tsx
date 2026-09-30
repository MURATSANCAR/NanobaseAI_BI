import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, authorsApi, type AuthorPazarBook, type AuthorPazarGroup } from '../../engine';
import { Loading, Note, Pill, btnGhost, errText, nf } from '../../admin/ui';
import SqlInfo from '../../components/SqlInfo';
import { fmtDay } from './shared';

/** Pazarda bu yazar: Başarı Dağıtım kataloğunda yazarın kitapları. Barkodla doğrulanan kitaplar (CRM'de yazara bağlı)
 *  ile yalnız adla eşleşenler ayrı gösterilir; ad eşleşmesi hiçbir kayda bağlanmaz, belirsizse nedeni yazılır.
 *  Katalog dağıtımcının kitapçılara açık listesidir: okura satış göstermez. */

const money = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 });
const SHOW = 5;

function GroupTile({ title, g }: { title: string; g?: AuthorPazarGroup }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-white px-3 py-2">
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{title}</div>
      <div className="mt-0.5 font-mono text-[20px] font-bold leading-tight tabular-nums">{nf.format(g?.kitap ?? 0)}</div>
      <div className="text-[11px] leading-snug text-canvas-muted">
        {g && g.kitap > 0 ? (
          <>
            {nf.format(g.satista)} satışta · {nf.format(g.baskisiYok)} baskısı yok
            {g.diger > 0 ? ` · ${nf.format(g.diger)} başka durumda` : ''}
          </>
        ) : (
          'kitap yok'
        )}
      </div>
    </div>
  );
}

function BookRow({ b }: { b: AuthorPazarBook }) {
  const bits = [b.yayinevi, b.durum, b.baskiNo ? `${nf.format(b.baskiNo)}. baskı` : null, b.fiyat ? money.format(b.fiyat) : null, b.basimYili ? String(b.basimYili) : null].filter(Boolean);
  return (
    <li className="rounded-xl border border-slate-100 bg-white px-3 py-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-1">
        <span className="min-w-0 break-words text-[12.5px] font-extrabold">{b.ad || b.barkod}</span>
        <Pill tone={b.dogrulandi ? 'ok' : 'muted'}>{b.dogrulandi ? 'Barkodla doğrulandı' : 'Ad eşleşmesi'}</Pill>
      </div>
      <div className="mt-0.5 break-words text-[11px] leading-snug text-canvas-muted">
        {bits.join(' · ')}
        {b.drde ? " · D&R'de de var" : ''}
        {b.cikis != null ? ` · çıkış ${nf.format(b.cikis)}` : ''}
      </div>
    </li>
  );
}

export default function MarketSection({ contactId, name }: { contactId?: string | null; name: string }) {
  const [all, setAll] = useState(false);
  const q = useQuery({
    queryKey: ['authors', 'pazar', contactId ?? null, name],
    queryFn: () => authorsApi.pazar({ contactId, name }),
    enabled: ENGINE_ENABLED && !!(contactId || name),
    staleTime: 10 * 60_000,
  });
  const d = q.data;
  const k = d?.kaynaklar;
  const books = d?.kitaplar ?? [];
  const shown = all ? books : books.slice(0, SHOW);
  return (
    <section>
      <h3 className="flex items-center gap-2 text-[12px] font-extrabold">
        Pazarda bu yazar (dağıtımcı kataloğu)
        {d && <span className="font-mono font-semibold tabular-nums text-canvas-muted">{nf.format(books.length)}</span>}
        {d && books.length > 0 && <SqlInfo k={k} alan="kitaplar[]" label="Pazarda bu yazar" />}
      </h3>
      {d && (
        <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
          {d.kaynak}
          {d.tarih ? `, ${fmtDay(d.tarih)} görüntüsü` : ''}. Kitapçılara açık liste; okura satışı göstermez.
        </p>
      )}
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Dağıtımcı kataloğu okunamadı.')}</Note>}
      {d && !d.okundu && <p className="mt-1 text-[12px] text-canvas-muted">Dağıtımcı kataloğu henüz okunmadı; ilk sabah turundan sonra görünür.</p>}
      {d && d.okundu && !books.length && (
        <p className="mt-1 text-[12px] text-canvas-muted">Başarı Dağıtım kataloğunda «{d.ad}» adıyla ya da yazarın kitaplarının barkoduyla eşleşen kitap yok.</p>
      )}
      {d && books.length > 0 && (
        <div className="mt-1.5 space-y-2">
          {d.belirsiz ? (
            <Note tone="warn">
              <span className="font-bold">Ad eşleşmesi belirsiz; kitaplar yazar kaydına bağlanmadı.</span>
              <ul className="mt-1 list-disc space-y-0.5 pl-4">
                {d.nedenler.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </Note>
          ) : (
            <p className="text-[11.5px] leading-snug text-canvas-muted">
              {nf.format(d.dogrulanan ?? 0)} kitap barkodla doğrulandı (CRM'de bu yazara bağlı).
              {(d.dogrulanan ?? 0) < books.length ? ' Diğerleri yalnız ad eşleşmesidir, yazar kaydına bağlanmaz.' : ''}
            </p>
          )}
          <div className="grid grid-cols-2 gap-2">
            <GroupTile title="TİMAŞ'ta" g={d.timas} />
            <GroupTile title="Başka yayınevlerinde" g={d.diger} />
          </div>
          <dl className="grid grid-cols-[112px_minmax(0,1fr)] gap-x-2 gap-y-1 text-[12px]">
            {d.yayinevleri && d.yayinevleri.length > 0 && (
              <div className="contents">
                <dt className="text-canvas-muted">Yayınevleri</dt>
                <dd className="min-w-0 break-words font-semibold">
                  {d.yayinevleri.map((p) => `${p.yayinevi} (${nf.format(p.kitap)})`).join(', ')}
                </dd>
              </div>
            )}
            {d.enYuksekBaski && (
              <div className="contents">
                <dt className="text-canvas-muted">En yüksek baskı</dt>
                <dd className="min-w-0 break-words font-semibold">
                  {nf.format(d.enYuksekBaski.baski)}. baskı · {d.enYuksekBaski.ad}
                  {d.enYuksekBaski.yayinevi ? ` (${d.enYuksekBaski.yayinevi})` : ''}
                </dd>
              </div>
            )}
            {d.fiyat && (
              <div className="contents">
                <dt className="text-canvas-muted">Liste fiyatı</dt>
                <dd className="min-w-0 break-words font-mono font-semibold tabular-nums">
                  {money.format(d.fiyat.enDusuk)} – {money.format(d.fiyat.enYuksek)}
                  <span className="font-sans font-normal text-canvas-muted"> · orta {money.format(d.fiyat.orta)}</span>
                </dd>
              </div>
            )}
            <div className="contents">
              <dt className="text-canvas-muted">D&amp;R'de de var</dt>
              <dd className="font-mono font-semibold tabular-nums">
                {nf.format(d.drdeOlan ?? 0)} / {nf.format(books.length)}
              </dd>
            </div>
            <div className="contents">
              <dt className="text-canvas-muted">Çıkış endeksi</dt>
              <dd className="min-w-0 break-words">
                {d.cikis ? (
                  <span className="inline-flex flex-wrap items-center gap-1 font-semibold">
                    <span className="font-mono tabular-nums">TİMAŞ {nf.format(d.cikis.timas)} · diğer {nf.format(d.cikis.diger)}</span>
                    <span className="font-normal text-canvas-muted">
                      ({fmtDay(d.cikis.bas)} – {fmtDay(d.cikis.son)})
                    </span>
                    <SqlInfo k={k} alan="cikis" label="Çıkış endeksi" />
                  </span>
                ) : (
                  <span className="text-canvas-muted">{d.cikisNot}</span>
                )}
              </dd>
            </div>
          </dl>
          {d.adlar.length > 0 && (
            <p className="break-words text-[11px] leading-snug text-canvas-muted">Katalogdaki yazım: {d.adlar.join(' · ')}</p>
          )}
          <ul className="space-y-1.5">
            {shown.map((b) => (
              <BookRow key={b.barkod} b={b} />
            ))}
          </ul>
          {books.length > SHOW && (
            <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => setAll((v) => !v)}>
              {all ? 'Daha az göster' : `Bütün kitaplar (${nf.format(books.length)})`}
            </button>
          )}
          <p className="text-[10.5px] leading-snug text-canvas-muted">{d.not}</p>
        </div>
      )}
    </section>
  );
}
