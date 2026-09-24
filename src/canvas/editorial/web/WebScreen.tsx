import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, webApi } from '../../engine';
import { Note, errText, nf } from '../../admin/ui';
import { dateTime } from '../../format';
import { Kpi, KpiRow, ModuleFrame, Pager, Panel } from '../kit';
import { MentionRow, TONE, ToneBar } from './parts';

/** Basın ve web: CRM yazarları ve kitapları hakkında Türk haber sitelerinin RSS akışlarında çıkan haberler.
 *  Her gece taranır; yerel modelin ilgili bulmadığı eşleşme gösterilmez. */

export default function WebScreen() {
  const [page, setPage] = useState(0);
  const [label, setLabel] = useState('');
  const q = useQuery({
    queryKey: ['editorial', 'web', 'overview', page, label],
    queryFn: () => webApi.overview({ page, label: label || undefined }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const d = q.data;
  const err = errText(q.error, 'Basın kayıtları okunamadı.');
  const shown = (d?.tone.olumlu ?? 0) + (d?.tone.olumsuz ?? 0) + (d?.tone.notr ?? 0);

  return (
    <ModuleFrame
      route="/basin-web"
      crumb="Basın ve web"
      title="Basın ve web"
      lead={`Yazarlarımız ve kitapları hakkında haber sitelerinde çıkan haberler. Her gece taranır; yalnız gerçekten ilgili bulunan haberler gösterilir.${d?.sources.length ? ` Kaynaklar: ${d.sources.map((s) => s.label).join(', ')}.` : ''}`}
      source={d?.lastRun?.at ? `Son tarama ${dateTime(d.lastRun.at)}` : 'Kaynak: haber RSS, Wikidata'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {d && !d.lastRun && <Note tone="info">İlk tarama henüz yapılmadı.</Note>}

      {d && (
        <KpiRow>
          <Kpi label="İlgili haber" value={nf.format(shown)} help="Yazar ya da kitabı hakkında olan" />
          <Kpi label="Olumlu" value={nf.format(d.tone.olumlu ?? 0)} help="Övgü, ödül, başarı" active={label === 'olumlu'} onClick={() => { setLabel(label === 'olumlu' ? '' : 'olumlu'); setPage(0); }} />
          <Kpi label="Olumsuz" value={nf.format(d.tone.olumsuz ?? 0)} help="Eleştiri, tartışma" active={label === 'olumsuz'} onClick={() => { setLabel(label === 'olumsuz' ? '' : 'olumsuz'); setPage(0); }} />
          <Kpi label="Yazar bilgisi" value={nf.format(d.counts.authorsFound)} help={`${nf.format(d.counts.authorsChecked)} yazar Wikidata'da arandı`} />
        </KpiRow>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)] lg:items-start lg:gap-4">
        <Panel>
          <h2 className="text-[15px] font-extrabold">{label ? `${TONE[label].label} haberler` : 'Son haberler'}</h2>
          {d && !d.items.length && <p className="py-8 text-center text-[12.5px] text-canvas-muted">Henüz ilgili haber yok. Tarama her gece sürer.</p>}
          <ul className="mt-1">
            {(d?.items ?? []).map((m) => (
              <MentionRow key={`${m.url}-${m.contactId}`} m={m} showAuthor />
            ))}
          </ul>
          {d && d.total > d.pageSize && (
            <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
          )}
        </Panel>

        <Panel>
          <h2 className="text-[15px] font-extrabold">En çok haberi çıkan yazarlar</h2>
          {d && !d.authors.length && <p className="mt-2 text-[12.5px] text-canvas-muted">Henüz yok.</p>}
          <ul className="mt-2">
            {(d?.authors ?? []).map((a) => (
              <li key={a.contactId} className="border-t border-slate-100 py-2.5 first:border-t-0">
                <div className="flex items-baseline justify-between gap-2">
                  <Link to={`/kisiler?rol=yazar&kisi=${a.contactId}`} className="min-w-0 break-words text-[13px] font-extrabold hover:underline">
                    {a.author}
                  </Link>
                  <span className="shrink-0 font-mono text-[12px] tabular-nums text-canvas-muted">{nf.format(a.total)}</span>
                </div>
                <div className="mt-1">
                  <ToneBar tone={a.tone} />
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </ModuleFrame>
  );
}
