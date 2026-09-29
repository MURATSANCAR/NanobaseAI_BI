import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, webApi, type WebChannel } from '../../engine';
import { Note, errText, nf } from '../../admin/ui';
import { dateTime } from '../../format';
import { Kpi, KpiRow, ModuleFrame, Pager, Panel } from '../kit';
import { MentionRow, TONE, ToneBar } from './parts';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';
import { EmptyHint, ExplainLabel } from '../../components/Explain';

/** Basın ve web: CRM yazarları ve kitapları hakkında Türk haber sitelerinin RSS akışlarında çıkan haberler.
 *  Her gece taranır; yerel modelin ilgili bulmadığı eşleşme gösterilmez. */

const STATUS: Record<WebChannel['status'], string> = {
  açık: 'bg-emerald-50 text-emerald-700',
  kapalı: 'bg-amber-50 text-amber-800',
  hata: 'bg-amber-50 text-amber-800',
  engelli: 'bg-slate-100 text-canvas-muted',
};
const STATUS_TEXT: Record<WebChannel['status'], string> = { açık: 'açık', kapalı: 'kapalı', hata: 'okunamadı', engelli: 'kapalı' };

/** Kanal haritası: hangi kanaldan ne okundu, kaçı yazarla eşleşti, kaçı ilgili bulundu; kapalı kanal nedeniyle. */
function Channels({ rows, k }: { rows: WebChannel[]; k?: ReturnType<typeof kaynakOf> }) {
  const open = rows.filter((r) => r.status !== 'engelli');
  const closed = rows.filter((r) => r.status === 'engelli');
  return (
    <Panel>
      <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
        Kanallar
        <SqlInfo k={k} alan="_hepsi" label="Kanal tablosu" />
      </h2>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">
        {nf.format(open.length)} kanal taranıyor, {nf.format(closed.length)} kanal kapalı. Sayılar: okunan kayıt · yazarla eşleşen · ilgili bulunan.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[520px] text-[12.5px]">
          <thead>
            <tr className="text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              <th className="px-2 py-1.5">Kanal</th>
              <th className="px-2 py-1.5">Tür</th>
              <th className="px-2 py-1.5 text-right">
                <ExplainLabel label="Okunan">Kanaldan son taramada okunan haber ya da girdi sayısı.</ExplainLabel>
              </th>
              <th className="px-2 py-1.5 text-right">
                <ExplainLabel label="Eşleşen">Başlığında ya da özetinde CRM'deki bir yazarın adı geçen kayıtlar.</ExplainLabel>
              </th>
              <th className="px-2 py-1.5 text-right">
                <ExplainLabel label="İlgili">Eşleşenlerden Zeki AI'ın gerçekten o yazar ya da kitabı hakkında bulduğu ve ekranda gösterilenler.</ExplainLabel>
              </th>
              <th className="px-2 py-1.5">Son okuma</th>
            </tr>
          </thead>
          <tbody>
            {open.map((r) => (
              <tr key={r.key} className="border-t border-slate-100 align-top">
                <td className="px-2 py-1.5">
                  <span className="font-semibold">{r.label}</span>
                  {r.status !== 'açık' && <span className={`ml-1.5 rounded px-1 text-[10.5px] font-bold ${STATUS[r.status]}`}>{STATUS_TEXT[r.status] ?? r.status}</span>}
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
      lead="Yazarlarımız ve kitapları hakkında haber sitelerinde ve açık kaynaklarda çıkanlar. Her gece taranır; Zeki AI'ın gerçekten ilgili bulduğu haberler, kaynağı ve tonuyla gösterilir."
      source={d?.lastRun?.at ? `Son tarama ${dateTime(d.lastRun.at)}` : 'Kaynak: haber akışları, açık bilgi tabanı'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda tanımlı değil; ekrandaki bilgiler okunamaz. Sistem yöneticinize haber verin.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {d && !d.enabled && (
        <Note tone="info">
          {d.lastRun?.at
            ? `Gece taraması bu ortamda kapalı; aşağıdakiler ${dateTime(d.lastRun.at)} tarihli son taramadan, yeni haber eklenmiyor.`
            : 'Basın ve web taraması bu ortamda kapalı.'}
        </Note>
      )}
      {d && d.enabled && !d.lastRun && <Note tone="info">İlk tarama henüz yapılmadı.</Note>}

      {d && (
        <KpiRow>
          <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="İlgili haber" />} explain="Zeki AI'ın bir yazarımız ya da kitabımız hakkında olduğuna karar verdiği haberler; olumlu, olumsuz ve nötr toplamı." label="İlgili haber" value={nf.format(shown)} help="Yazar ya da kitabı hakkında olan" />
          <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Olumlu" />} explain="Tonu olumlu bulunan ilgili haberler. Karta dokununca liste yalnız bunlara süzülür." label="Olumlu" value={nf.format(d.tone.olumlu ?? 0)} help="Övgü, ödül, başarı" active={label === 'olumlu'} onClick={() => { setLabel(label === 'olumlu' ? '' : 'olumlu'); setPage(0); }} />
          <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Olumsuz" />} explain="Tonu olumsuz bulunan ilgili haberler. Karta dokununca liste yalnız bunlara süzülür." label="Olumsuz" value={nf.format(d.tone.olumsuz ?? 0)} help="Eleştiri, tartışma" active={label === 'olumsuz'} onClick={() => { setLabel(label === 'olumsuz' ? '' : 'olumsuz'); setPage(0); }} />
          <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Yazar bilgisi" />} explain="Açık bilgi tabanında kaydı bulunan yazar sayısı; doğum yılı, meslek ve ödül bilgisi kişi kartında görünür." label="Yazar bilgisi" value={nf.format(d.counts.authorsFound)} help={`${nf.format(d.counts.authorsChecked)} yazar açık bilgi tabanında arandı`} />
        </KpiRow>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)] lg:items-start lg:gap-4">
        <Panel>
          <h2 className="text-[15px] font-extrabold">{label ? `${TONE[label].label} haberler` : 'Son haberler'}</h2>
          {d && !d.items.length && (
            <div className="mt-2">
              <EmptyHint
                title={label ? `${TONE[label].label} haber yok` : 'Henüz ilgili haber yok'}
                why={label ? 'Tüm haberleri görmek için seçili karta yeniden dokunun.' : 'Tarama her gece yapılır; ilgili bulunan haberler burada birikir.'}
              />
            </div>
          )}
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
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
            En çok haberi çıkan yazarlar
            <SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Yazar başına haber" />
          </h2>
          {d && !d.authors.length && <p className="mt-2 text-[12.5px] text-canvas-muted">Henüz haberi çıkan yazar yok.</p>}
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
      {d && <Channels rows={d.channels} k={kaynakOf(d)} />}
    </ModuleFrame>
  );
}
