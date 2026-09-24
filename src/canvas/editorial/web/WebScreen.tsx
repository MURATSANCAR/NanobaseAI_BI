import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, webApi, type WebChannel } from '../../engine';
import { Note, errText, nf } from '../../admin/ui';
import { dateTime } from '../../format';
import { Kpi, KpiRow, ModuleFrame, Pager, Panel } from '../kit';
import { MentionRow, TONE, ToneBar } from './parts';

/** Basın ve web: CRM yazarları ve kitapları hakkında Türk haber sitelerinin RSS akışlarında çıkan haberler.
 *  Her gece taranır; yerel modelin ilgili bulmadığı eşleşme gösterilmez. */

const STATUS: Record<WebChannel['status'], string> = {
  açık: 'bg-emerald-50 text-emerald-700',
  kapalı: 'bg-amber-50 text-amber-800',
  hata: 'bg-amber-50 text-amber-800',
  engelli: 'bg-slate-100 text-canvas-muted',
};

/** Kanal haritası: hangi kanaldan ne okundu, kaçı yazarla eşleşti, kaçı ilgili bulundu; kapalı kanal nedeniyle. */
function Channels({ rows }: { rows: WebChannel[] }) {
  const open = rows.filter((r) => r.status !== 'engelli');
  const closed = rows.filter((r) => r.status === 'engelli');
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Kanallar</h2>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">
        {nf.format(open.length)} kanal taranıyor, {nf.format(closed.length)} kanal kapalı. Sayılar: okunan kayıt · yazarla eşleşen · ilgili bulunan.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[520px] text-[12.5px]">
          <thead>
            <tr className="text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              <th className="px-2 py-1.5">Kanal</th>
              <th className="px-2 py-1.5">Tür</th>
              <th className="px-2 py-1.5 text-right">Okunan</th>
              <th className="px-2 py-1.5 text-right">Eşleşen</th>
              <th className="px-2 py-1.5 text-right">İlgili</th>
              <th className="px-2 py-1.5">Son okuma</th>
            </tr>
          </thead>
          <tbody>
            {open.map((r) => (
              <tr key={r.key} className="border-t border-slate-100 align-top">
                <td className="px-2 py-1.5">
                  <span className="font-semibold">{r.label}</span>
                  {r.status !== 'açık' && <span className={`ml-1.5 rounded px-1 text-[10.5px] font-bold ${STATUS[r.status]}`}>{r.status}</span>}
                  {r.note && <span className="block text-[11px] text-canvas-muted">{r.note}</span>}
                </td>
                <td className="px-2 py-1.5 text-canvas-muted">{r.kind}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{nf.format(r.read)}</td>
                <td className="px-2 py-1.5 text-right font-mono tabular-nums">{nf.format(r.matched)}</td>
                <td className={`px-2 py-1.5 text-right font-mono tabular-nums ${r.relevant ? 'font-bold text-emerald-700' : ''}`}>{nf.format(r.relevant)}</td>
                <td className="px-2 py-1.5 font-mono text-[11px] tabular-nums text-canvas-muted">{r.lastAt ? dateTime(r.lastAt) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="mt-3">
        <summary className="cursor-pointer text-[12px] font-bold text-canvas-violet">Kapalı kanallar ve nedenleri ({nf.format(closed.length)})</summary>
        <ul className="mt-1.5 space-y-1 text-[12px]">
          {closed.map((r) => (
            <li key={r.key}>
              <b className="font-semibold">{r.label}</b> <span className="text-canvas-muted">— {r.note}</span>
            </li>
          ))}
        </ul>
      </details>
    </Panel>
  );
}

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
      lead="Yazarlarımız ve kitapları hakkında haber sitelerinde ve sözlüklerde çıkanlar. Her gece taranır; yalnız gerçekten ilgili bulunanlar gösterilir, her kaydın yanında kanalı yazar."
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
      {d && <Channels rows={d.channels} />}
    </ModuleFrame>
  );
}
