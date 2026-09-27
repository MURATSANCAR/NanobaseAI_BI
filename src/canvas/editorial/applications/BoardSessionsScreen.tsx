import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CalendarPlus, ChevronRight } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnPrimary, errText, nf } from '../../admin/ui';
import { Kpi, KpiRow, ModuleFrame, Panel } from '../kit';
import { fmtDay } from '../authors/shared';
import MeetingScreen from '../intake/MeetingScreen';
import { applicationsApi, boardApi, type SessionHead } from './api';
import SessionForm from './SessionForm';
import { BoardTabs, useAppMeta } from './shared';

/** Yayın kurulu: portalda yürütülen kurul oturumları (gündem, üye oyu, karar). CRM'deki geçmiş kurul kararları
 *  `?gorunum=crm` ile aynı sayfada açılır. */

function SessionRow({ s }: { s: SessionHead }) {
  const pending = s.agenda ? s.agenda.items - s.agenda.decided : 0;
  const myTodo = s.isMember && s.state === 'planli' && s.agenda ? Math.max(0, s.agenda.items - (s.myVotes ?? 0)) : 0;
  return (
    <li className="border-t border-slate-100 first:border-t-0">
      <Link to={`/yayin-kurulu/oturum/${s.id}`} className="flex items-center gap-3 rounded-xl px-1 py-3 transition-colors duration-150 hover:bg-white/70 sm:px-2">
        <span className="w-14 shrink-0 text-center">
          <span className="block font-mono text-[20px] font-extrabold leading-none tabular-nums">{s.date.slice(8, 10)}</span>
          <span className="block text-[11px] text-canvas-muted">{fmtDay(s.date).split(' ').slice(1).join(' ')}</span>
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="break-words text-[13.5px] font-extrabold">{s.title}</span>
            <Pill tone={s.state === 'kapandi' ? 'muted' : 'violet'}>{s.stateLabel}</Pill>
            {myTodo > 0 && <Pill tone="warn">Oyunuz bekleniyor: {nf.format(myTodo)}</Pill>}
          </span>
          <span className="mt-0.5 block break-words text-[11.5px] text-canvas-muted">
            {[s.time, s.place, `Başkan: ${s.chairName}`, `${nf.format(s.members.length)} üye`].filter(Boolean).join(' · ')}
          </span>
          <span className="mt-0.5 block text-[11.5px]">
            Gündem {nf.format(s.agenda?.items ?? 0)} başvuru
            {s.agenda && s.agenda.items > 0 && (s.state === 'kapandi' ? ' · kapandı' : pending ? ` · ${nf.format(pending)} karar bekliyor` : ' · hepsi karara bağlandı')}
          </span>
        </span>
        <ChevronRight aria-hidden className="h-4 w-4 shrink-0 text-canvas-muted" />
      </Link>
    </li>
  );
}

function Sessions() {
  const meta = useAppMeta();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const list = useQuery({ queryKey: ['board', 'sessions', 'all'], queryFn: () => boardApi.list(), enabled: ENGINE_ENABLED });
  const waiting = useQuery({
    queryKey: ['applications', 'list', 'kuyruk', '', 'kurul_bekliyor', false],
    queryFn: () => applicationsApi.list({ view: 'kuyruk', status: 'kurul_bekliyor' }),
    enabled: ENGINE_ENABLED,
  });
  const items = list.data?.items ?? [];
  const open = items.filter((s) => s.state === 'planli').sort((a, b) => a.date.localeCompare(b.date));
  const closed = items.filter((s) => s.state === 'kapandi');
  const myTodo = open.reduce((n, s) => n + (s.isMember && s.agenda ? Math.max(0, s.agenda.items - (s.myVotes ?? 0)) : 0), 0);
  const canRun = !!meta.data?.me.canRunBoard;

  return (
    <ModuleFrame
      route="/yayin-kurulu"
      crumb="Yayın kurulu"
      title="Yayın kurulu"
      lead="Kurul oturumları: gündeme kurula çıkan başvurular girer, her üye kendi puanını ve oyunu verir, başkan kararı kaydeder. Kabul, red ve revizyon başvurunun durumunu değiştirir ve yazara gidecek yazının taslağını hazırlar."
      source={`${nf.format(open.length)} hazırlanan oturum`}
      presence="Kaynak: portal"
      aside={
        <div className="flex flex-col gap-2">
          <BoardTabs active="oturum" />
          {canRun && (
            <button type="button" className={`${btnPrimary} w-full`} onClick={() => setCreating(true)}>
              <CalendarPlus aria-hidden className="h-4 w-4" />
              Yeni oturum
            </button>
          )}
        </div>
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      <KpiRow>
        <Kpi label="Hazırlanan oturum" value={list.data ? nf.format(open.length) : '—'} help="Kapanmamış kurul oturumu" />
        <Kpi label="Oyunuzu bekleyen" value={list.data ? nf.format(myTodo) : '—'} help="Üyesi olduğunuz oturumlarda" />
        <Kpi label="Kurula çıkacak" value={waiting.data ? nf.format(waiting.data.items.length) : '—'} help="Gündem bekleyen başvuru" />
        <Kpi label="Kapanan oturum" value={list.data ? nf.format(closed.length) : '—'} help="Kararları kayıtlı" />
      </KpiRow>
      {list.error && <Note tone="err">{errText(list.error, 'Oturumlar okunamadı.')}</Note>}
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)] lg:items-start lg:gap-4">
        <Panel>
          <h2 className="text-[15px] font-extrabold">Hazırlanan oturumlar</h2>
          {list.isLoading && <Loading />}
          {list.data && open.length === 0 && (
            <p className="py-6 text-center text-[12.5px] text-canvas-muted">{canRun ? 'Açık oturum yok. «Yeni oturum» ile açın.' : 'Açık kurul oturumu yok.'}</p>
          )}
          <ul className="mt-1">
            {open.map((s) => (
              <SessionRow key={s.id} s={s} />
            ))}
          </ul>
          {closed.length > 0 && (
            <>
              <h2 className="mt-4 text-[15px] font-extrabold">Kapanan oturumlar</h2>
              <ul className="mt-1">
                {closed.map((s) => (
                  <SessionRow key={s.id} s={s} />
                ))}
              </ul>
            </>
          )}
        </Panel>
        <Panel>
          <h2 className="text-[15px] font-extrabold">Kurula çıkacak başvurular</h2>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">Editör raporu tamam, gündeme eklenmeyi bekliyor.</p>
          {waiting.data && waiting.data.items.length === 0 && <p className="mt-3 text-[12.5px] text-canvas-muted">Bekleyen başvuru yok.</p>}
          <ul className="mt-2">
            {(waiting.data?.items ?? []).map((a) => (
              <li key={a.id} className="border-t border-slate-100 py-2.5 first:border-t-0">
                <Link to={`/basvurular/${a.id}`} className="block hover:underline">
                  <span className="font-mono text-[11px] text-canvas-muted">{a.no}</span>
                  <span className="block break-words text-[13px] font-extrabold leading-snug">{a.title}</span>
                </Link>
                <span className="block text-[11.5px] text-canvas-muted">
                  {[a.authorName, a.categoryName, a.evaluatorName && `Editör: ${a.evaluatorName}`].filter(Boolean).join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <SessionForm
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(s) => {
          setCreating(false);
          navigate(`/yayin-kurulu/oturum/${s.id}`);
        }}
      />
    </ModuleFrame>
  );
}

export default function BoardSessionsScreen() {
  const [params] = useSearchParams();
  return params.get('gorunum') === 'crm' ? <MeetingScreen /> : <Sessions />;
}
