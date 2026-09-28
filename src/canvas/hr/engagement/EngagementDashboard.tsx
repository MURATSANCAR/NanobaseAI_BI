import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, field, td, th } from '../../admin/ui';
import { fmtDay } from '../hrApi';
import { Block, Fact, HrFrame } from '../parts';
import ResultView from './ResultView';
import { engApi, fmtNum } from './engApi';

/** M58 Bağlılık panosu (İK/GM): eNPS ve endeks eğilimi, yanıt oranı, madde sonuçları, eşiğe tabi birim kırılımı, Zeki AI
 *  tema özeti (alıntısız), öneri kutusu döngüsü. Yorum metni yalnız «Anket yorum metinleri» yetkisinde, maskeli ve karışık. */
export default function EngagementDashboard() {
  const meta = useQuery({ queryKey: ['hr', 'eng', 'meta'], queryFn: engApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const surveys = useQuery({ queryKey: ['hr', 'eng', 'surveys'], queryFn: engApi.surveys, enabled: ENGINE_ENABLED });
  const trend = useQuery({ queryKey: ['hr', 'eng', 'trend'], queryFn: engApi.trend, enabled: ENGINE_ENABLED });
  const [sel, setSel] = useState('');
  const [scope, setScope] = useState('sirket');
  useEffect(() => {
    const items = surveys.data?.items ?? [];
    if (!sel && items.length) setSel((items.find((s) => s.state === 'kapandi') ?? items[0]).id);
  }, [surveys.data, sel]);
  const s = surveys.data?.items.find((x) => x.id === sel);
  const prog = useQuery({ queryKey: ['hr', 'eng', 'progress', sel], queryFn: () => engApi.progress(sel), enabled: !!sel });
  const res = useQuery({ queryKey: ['hr', 'eng', 'results', sel, scope], queryFn: () => engApi.results(sel, scope), enabled: !!sel });
  const themes = useQuery({ queryKey: ['hr', 'eng', 'themes', sel], queryFn: () => engApi.themes(sel), enabled: !!sel && s?.state === 'kapandi' });
  const can = meta.data?.me.can;
  const t = trend.data;
  return (
    <HrFrame crumb="Bağlılık panosu" title="Bağlılık panosu"
      lead="Anonim anketlerin toplu sonucu. Sonuç anket kapanınca ve gösterim eşiği girilince görünür; eşiğin altındaki birim üst birimle birlikte gösterilir. Kimin katıldığı ya da ne cevap verdiği hiçbir ekranda yoktur."
      aside={surveys.data && surveys.data.items.length > 0 ? (
        <select className={field} value={sel} onChange={(e) => { setSel(e.target.value); setScope('sirket'); }} aria-label="Anket">
          {surveys.data.items.map((x) => <option key={x.id} value={x.id}>{x.title} · {x.stateLabel}</option>)}
        </select>
      ) : undefined}>
      {surveys.error && <Note tone="err">{errText(surveys.error, 'Anketler okunamadı.')}</Note>}
      {surveys.data && !surveys.data.items.length && <Note tone="info">Henüz anket yok. <Link className="font-bold text-canvas-violet underline" to="/ik/anket-yonetimi">Anket yönetimi</Link>nden başlatın.</Note>}
      {t && t.items.length > 0 && (
        <Block title="Eğilim" help="Kapanmış anketler; gösterim eşiği altındakiler boş.">
          <TableWrap>
            <thead><tr><th className={th}>Anket</th><th className={th}>Kapanış</th><th className={th}>Yanıt oranı</th><th className={th}>eNPS</th><th className={th}>Endeks</th></tr></thead>
            <tbody>
              {t.items.map((r) => (
                <tr key={r.surveyId} className="border-t border-slate-100">
                  <td className={td}>{r.title}</td><td className={td}>{fmtDay(r.closesAt)}</td>
                  <td className={`${td} tabular-nums`}>{r.rate !== null ? `%${fmtNum(r.rate * 100, 0)}` : '—'}</td>
                  <td className={`${td} tabular-nums`}>{fmtNum(r.enps)}</td><td className={`${td} tabular-nums`}>{fmtNum(r.index)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Block>
      )}
      {s && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[2fr_1fr] lg:gap-4">
          <Block title={scope === 'sirket' ? 'Şirket geneli' : `Birim: ${res.data?.unitName ?? ''}`}
            action={
              <div className="flex flex-wrap gap-2">
                {scope !== 'sirket' && <button type="button" className={btnGhost} onClick={() => setScope('sirket')}>Şirket geneline dön</button>}
                {can?.export && s.state === 'kapandi' && (
                  <button type="button" className={btnGhost} onClick={() => void engApi.exportCsv(s.id).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}><Download aria-hidden className="h-4 w-4" />CSV</button>
                )}
              </div>
            }>
            {res.error && <Note tone="err">{errText(res.error, 'Sonuç okunamadı.')}</Note>}
            {res.isLoading && <Loading />}
            {res.data && <ResultView r={res.data} onUnit={(u) => setScope(u)} />}
          </Block>
          <div className="flex flex-col gap-3">
            {prog.data && (
              <Block title="Katılım" help={prog.data.note}>
                <div className="grid grid-cols-2 gap-2">
                  <Fact label="Davet" value={prog.data.invited} />
                  <Fact label="Cevaplayan" value={prog.data.responded} />
                  <Fact label="Basılı kod" value={`${prog.data.paperUsed} / ${prog.data.paperIssued}`} />
                  <Fact label="Yanıt oranı" value={prog.data.rate !== null ? `%${fmtNum(prog.data.rate * 100, 0)}` : '—'} />
                </div>
                {prog.data.noAccount > 0 && <div className="mt-2 text-[11.5px] text-canvas-muted">Hedef kitlede hesabı olmayan {prog.data.noAccount} kişi var; onlara basılı kod dağıtın.</div>}
              </Block>
            )}
            {t && (
              <Block title="Öneri kutusu">
                <div className="grid grid-cols-2 gap-2">
                  <Fact label="Öneri" value={t.suggestions.total} />
                  <Fact label="Cevaplanan" value={t.suggestions.answered} help={t.suggestions.avgDays !== null ? `ortalama ${fmtNum(t.suggestions.avgDays)} gün` : undefined} />
                </div>
              </Block>
            )}
          </div>
        </div>
      )}
      {s?.state === 'kapandi' && <ThemesBlock sid={s.id} data={themes.data} error={themes.error} canRaw={!!can?.comments} canRefresh={!!can?.surveys && !!meta.data?.modelVar} onRefreshed={() => void themes.refetch()} />}
    </HrFrame>
  );
}

function ThemesBlock({ sid, data, error, canRaw, canRefresh, onRefreshed }: {
  sid: string; data?: Awaited<ReturnType<typeof engApi.themes>>; error: unknown; canRaw: boolean; canRefresh: boolean; onRefreshed: () => void;
}) {
  const raw = useQuery({ queryKey: ['hr', 'eng', 'themes-raw', sid], queryFn: () => engApi.themes(sid, true), enabled: false });
  const refresh = useMutation({ mutationFn: () => engApi.refreshThemes(sid), onSuccess: (r) => { toast.success(`${r.classified} yorum sınıflandı, ${r.themes} tema özeti yazıldı.`); onRefreshed(); },
    onError: (e) => toast.error(errText(e, 'Tema özeti yazılamadı.')) });
  return (
    <Block title="Açık uçlu yorumlar: temalar" help="Zeki AI yorumları kapalı tema listesine ayırır ve alıntısız özet yazar; eşiğin altındaki temaya özet yazılmaz."
      action={
        <div className="flex flex-wrap gap-2">
          {canRefresh && <button type="button" className={btnGhost} disabled={refresh.isPending} onClick={() => refresh.mutate()}>{refresh.isPending ? 'Zeki AI çalışıyor…' : 'Temaları yenile'}</button>}
          {canRaw && <button type="button" className={btnGhost} onClick={() => void raw.refetch()}>Maskeli yorumları göster</button>}
        </div>
      }>
      {error ? <Note tone="err">{errText(error, 'Temalar okunamadı.')}</Note> : null}
      {data?.suppressed && <Note tone="info">{data.message}</Note>}
      {data && !data.suppressed && (
        <ul className="flex flex-col gap-1.5">
          {data.themes.map((t) => (
            <li key={t.theme} className="rounded-xl bg-white/80 p-2.5 text-[12.5px]">
              <div className="flex items-center gap-2"><span className="min-w-0 flex-1 font-bold">{t.theme}</span><Pill tone="violet">{t.count}</Pill></div>
              {t.summary ? <div className="mt-0.5 break-words">{t.summary}</div> : t.note && <div className="text-canvas-muted">{t.note}</div>}
            </li>
          ))}
          {!data.themes.length && <li className="text-[12px] text-canvas-muted">Yorum yok.</li>}
        </ul>
      )}
      {raw.data?.comments && (
        <ul className="mt-3 flex max-h-[420px] flex-col gap-1.5 overflow-y-auto">
          {raw.data.comments.map((c, i) => (
            <li key={i} className="rounded-xl bg-slate-50 px-3 py-2 text-[12.5px]">
              <div className="whitespace-pre-wrap break-words">{c.text}</div>
              <div className="text-[11px] text-canvas-muted">{c.theme ?? 'sınıflanmadı'}{c.probability !== null ? ` · %${Math.round(c.probability * 100)}` : ''}</div>
            </li>
          ))}
        </ul>
      )}
    </Block>
  );
}
