import { useCallback, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { FilePlus2, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, btnPrimary, errText, field, nf } from '../../admin/ui';
import { Kpi, KpiRow, ModuleFrame, Panel, useDebounced } from '../kit';
import { fmtDay } from '../authors/shared';
import { applicationsApi, type AppListItem, type AppStatus, type AppView } from './api';
import ApplicationForm from './ApplicationForm';
import FormsPanel from './FormsPanel';
import { StatusPill, useAppMeta } from './shared';
import { FileDrop } from '../../components/FileDrop';
import { MB } from '../../components/fileDropRules';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';
import { EmptyHint, Explain } from '../../components/Explain';

/** M1 Başvurular: yeni kitap başvurularının kuyruğu, kabul edilenler ve arşiv (reddedilen, geri çekilen).
 *  Görünüm, süzgeç ve arama adres çubuğunda durur (?gorunum=, ?durum=, ?ara=, ?benim=1). */

const TABS: Array<{ key: AppView; label: string }> = [
  { key: 'kuyruk', label: 'Kuyruk' },
  { key: 'kabul', label: 'Kabul edilenler' },
  { key: 'arsiv', label: 'Arşiv' },
];

const QUEUE_STATUSES: AppStatus[] = ['yeni', 'degerlendirmede', 'revizyon', 'kurul_bekliyor', 'kurulda'];
const ARCHIVE_STATUSES: AppStatus[] = ['red', 'geri_cekildi'];

function Row({ a }: { a: AppListItem }) {
  const closed = a.status === 'kabul' || a.status === 'red' || a.status === 'geri_cekildi';
  return (
    <li className="border-t border-slate-100 first:border-t-0">
      <Link
        to={`/basvurular/${a.id}`}
        className="grid gap-1.5 rounded-xl px-1 py-3 transition-colors duration-150 hover:bg-white/70 sm:grid-cols-[minmax(0,1fr)_170px_150px] sm:items-center sm:gap-4 sm:px-2"
      >
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{a.no}</span>
            <StatusPill status={a.status} label={a.statusLabel} />
            {a.mine && <span className="rounded-md bg-canvas-violet/10 px-1.5 py-0.5 text-[10.5px] font-bold text-canvas-violet">Sizde</span>}
          </span>
          <span className="mt-1 block break-words text-[13.5px] font-extrabold leading-snug">{a.title}</span>
          <span className="mt-0.5 block break-words text-[11.5px] leading-snug text-canvas-muted">
            {[a.authorName, a.agencyName && `Ajans: ${a.agencyName}`, a.categoryName, a.pageEstimate != null ? `${nf.format(a.pageEstimate)} sayfa` : null].filter(Boolean).join(' · ')}
          </span>
          {closed && a.decisionNote && <span className="mt-1 block break-words text-[11.5px] leading-snug text-canvas-ink/80">«{a.decisionNote.length > 160 ? `${a.decisionNote.slice(0, 160)}…` : a.decisionNote}»</span>}
        </span>
        <span className="text-[11.5px] leading-snug text-canvas-muted">
          {a.evaluatorName ? <span className="block">Editör: <b className="text-canvas-ink">{a.evaluatorName}</b></span> : <span className="block font-semibold text-amber-800">Editör atanmadı</span>}
          {a.evaluation && (
            <span className="block">
              Rapor: {a.evaluation.submitted ? 'tamam' : 'taslak'}
              {a.evaluation.contentScore != null && <> · içerik <b className="font-mono text-canvas-ink">{a.evaluation.contentScore}</b></>}
            </span>
          )}
          {a.session && <span className="block">Kurul: {fmtDay(a.session.date)}</span>}
        </span>
        <span className="text-[11.5px] leading-snug text-canvas-muted sm:text-right">
          <span className="block">Geldi {fmtDay(a.receivedOn)} · {a.channelLabel}</span>
          {a.waitingDays != null && (
            <span className={`block font-mono tabular-nums ${a.waitingDays > 14 ? 'font-bold text-red-700' : ''}`}>
              {a.waitingDays === 0 ? 'bugün bu adıma geldi' : `${nf.format(a.waitingDays)} gündür bu adımda`}
            </span>
          )}
          {closed && a.decidedAt && <span className="block">Karar {fmtDay(a.decidedAt)}</span>}
          <span className="block">{a.files ? `${nf.format(a.files)} dosya` : 'Dosya yok'}</span>
        </span>
      </Link>
    </li>
  );
}

export default function ApplicationsScreen() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const meta = useAppMeta();
  const view = (TABS.find((t) => t.key === params.get('gorunum'))?.key ?? 'kuyruk') as AppView;
  const status = params.get('durum') ?? '';
  const mine = params.get('benim') === '1';
  const [text, setText] = useState(params.get('ara') ?? '');
  const q = useDebounced(text.trim(), 300);
  const [creating, setCreating] = useState(false);
  const [dropped, setDropped] = useState<File | null>(null);

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  const list = useQuery({
    queryKey: ['applications', 'list', view, q, status, mine],
    queryFn: () => applicationsApi.list({ view, q, status, mine }),
    enabled: ENGINE_ENABLED,
    placeholderData: (prev) => prev,
  });
  const counts = list.data?.counts;
  const totals = list.data?.totals;
  const statuses = view === 'kuyruk' ? QUEUE_STATUSES : view === 'arsiv' ? ARCHIVE_STATUSES : [];
  const statusLabel = (s: string) => meta.data?.statuses.find((x) => x.value === s)?.label ?? s;
  const canWrite = !!meta.data?.me.canWrite;

  const aside = (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-3 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Görünüm">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={view === t.key}
            onClick={() => update({ gorunum: t.key === 'kuyruk' ? null : t.key, durum: null })}
            className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
              view === t.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
            }`}
          >
            {t.label}
            {totals && <span className="ml-1 font-mono text-[11px] font-bold opacity-80">{nf.format(totals[t.key])}</span>}
          </button>
        ))}
      </div>
      {canWrite && (
        <button type="button" className={`${btnPrimary} w-full`} onClick={() => setCreating(true)}>
          <FilePlus2 aria-hidden className="h-4 w-4" />
          Yeni başvuru
        </button>
      )}
      <FormsPanel />
    </div>
  );

  const kpi = (s: AppStatus, help: string, explain: string) => (
    <Kpi
      explain={`${explain} Karta dokununca kuyruk bu duruma süzülür; yeniden dokununca süzgeç kalkar.`}
      info={<SqlInfo k={kaynakOf(list.data)} alan="_hepsi" label={statusLabel(s)} />}
      label={statusLabel(s)}
      value={counts ? nf.format(counts[s]) : '—'}
      help={help}
      active={view === 'kuyruk' && status === s}
      onClick={() => update({ gorunum: null, durum: status === s ? null : s })}
    />
  );

  return (
    <ModuleFrame
      route="/basvurular"
      crumb="Başvurular"
      title="Başvurular"
      lead="Yeni kitap başvurularını kaydedin, editöre değerlendirtin, yayın kuruluna çıkarın ve kararı yazara bildirin. Kayıtlar portalda tutulur; kategori, benzer kitaplar ve satışlar CRM ile Logo'dan okunur."
      source={counts ? `${nf.format(totals?.kuyruk ?? 0)} başvuru kuyrukta` : 'Portal + CRM + Logo'}
      presence="Kaynak: portal"
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda tanımlı değil; ekrandaki bilgiler okunamaz. Sistem yöneticinize haber verin.</Note>}
      {/* Birincil eylem: eser dosyasını bırak → yeni başvuru formu dosya ekli ve eser adı dosya adından dolu açılır. */}
      <Panel>
        <FileDrop
          title="Eser dosyasını yükle (yeni başvuru)"
          hint="Başvuru formu dosya ekli açılır; eser adı dosya adından gelir, yazar bilgisini tamamlayıp kaydedersiniz."
          accept=".pdf,.docx,.doc"
          maxBytes={(meta.data?.fileMaxMb ?? 10) * MB}
          feature="basvuru.yaz"
          allowed={meta.data ? canWrite : undefined}
          onPick={(f) => {
            setDropped(f);
            setCreating(true);
          }}
        />
      </Panel>
      <KpiRow>
        {kpi('yeni', 'Editör atanmayı bekliyor', 'Kaydedilmiş ama henüz değerlendirecek editörü atanmamış başvurular.')}
        {kpi('degerlendirmede', 'Editör raporu yazılıyor', 'Editörü atanmış, ön değerlendirme raporu yazılan başvurular.')}
        {kpi('kurul_bekliyor', 'Rapor tamam, kurul gündemi bekleniyor', 'Editör raporu tamamlanıp kurula gönderilmiş, henüz bir oturumun gündemine eklenmemiş başvurular.')}
        {kpi('kurulda', 'Açık kurul oturumunun gündeminde', 'Açık bir yayın kurulu oturumunun gündeminde, kararı beklenen başvurular.')}
      </KpiRow>

      <Panel>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="flex items-center gap-1.5 text-[15px] font-extrabold">
            {TABS.find((t) => t.key === view)?.label}
            <Explain label="Başvuru durumları">
              Başvuru yeni → değerlendirmede → kurul bekliyor → kurulda adımlarından geçer. Revizyon, yazardan düzeltme istendiğini gösterir. Kabul edilenler ayrı sekmede, reddedilen ve geri çekilenler arşivdedir.
            </Explain>
          </h2>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="relative block">
              <span className="sr-only">Ara</span>
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
              <input
                type="search"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  update({ ara: e.target.value.trim() || null });
                }}
                placeholder="Eser, yazar, ajans ya da numara"
                className={`${field} !pl-9 sm:w-72`}
              />
            </label>
            {statuses.length > 0 && (
              <select aria-label="Durum" value={status} onChange={(e) => update({ durum: e.target.value || null })} className={field}>
                <option value="">Bütün durumlar</option>
                {statuses.map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
            )}
            <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-semibold sm:min-h-0">
              <input type="checkbox" checked={mine} onChange={(e) => update({ benim: e.target.checked ? '1' : null })} className="h-4 w-4 accent-[theme(colors.canvas.violet)]" />
              Bana atananlar
            </label>
          </div>
        </div>
        {list.error && <div className="mt-3"><Note tone="err">{errText(list.error, 'Başvurular okunamadı.')}</Note></div>}
        {list.isLoading && <Loading />}
        {list.data && list.data.items.length === 0 && (
          <div className="mt-3">
            {q || status || mine ? (
              <EmptyHint
                title="Süzgece uyan başvuru yok"
                why="Aramayı, durum seçimini ya da «Bana atananlar» işaretini kaldırıp yeniden bakın."
                action={
                  <button
                    type="button"
                    className="min-h-9 rounded-xl bg-slate-100 px-3 text-[12px] font-extrabold hover:bg-slate-200"
                    onClick={() => {
                      setText('');
                      update({ ara: null, durum: null, benim: null });
                    }}
                  >
                    Süzgeçleri temizle
                  </button>
                }
              />
            ) : view === 'kuyruk' ? (
              <EmptyHint title="Kuyrukta başvuru yok" why={canWrite ? 'Yeni gelen eser dosyasını yukarıdaki alana bırakarak ya da «Yeni başvuru» ile kaydedin.' : 'Yeni başvuru kaydedildiğinde burada görünür.'} />
            ) : view === 'kabul' ? (
              <EmptyHint title="Henüz kabul edilen başvuru yok" why="Yayın kurulunun kabul ettiği başvurular burada toplanır." />
            ) : (
              <EmptyHint title="Arşiv boş" why="Reddedilen ya da yazarın geri çektiği başvurular burada saklanır." />
            )}
          </div>
        )}
        <ul className={`mt-2 ${list.isFetching && !list.isLoading ? 'opacity-60' : ''}`}>
          {(list.data?.items ?? []).map((a) => (
            <Row key={a.id} a={a} />
          ))}
        </ul>
        {view === 'kuyruk' && (list.data?.items.length ?? 0) > 0 && (
          <p className="mt-2 px-1 text-[11.5px] leading-snug text-canvas-muted">
            Gün sayısı başvurunun bugünkü adıma (yeni, değerlendirmede, revizyonda, kurul sırasında, kurulda) geldiği günden bu yana geçen süredir; düzenleme, dosya ya da yazı bu sayıyı sıfırlamaz. Kırmızıysa 14 günden uzun süredir aynı adımda. «Sizde» rozeti, değerlendirmesi size atanmış başvuruyu gösterir.
          </p>
        )}
      </Panel>

      <ApplicationForm
        open={creating}
        initialFile={dropped}
        onClose={() => {
          setCreating(false);
          setDropped(null);
        }}
        onSaved={(a) => {
          setCreating(false);
          setDropped(null);
          navigate(`/basvurular/${a.id}`);
        }}
      />
    </ModuleFrame>
  );
}
