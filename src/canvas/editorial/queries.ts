import { keepPreviousData, queryOptions, type QueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED, assignApi, contractsApi, contributorsApi, editorsApi, intakeApi } from '../engine';
import { editorialHomeOptions } from './homeQuery';

/**
 * Editoryal liste ekranlarının sorguları. Ekran da girişteki ön yükleme de aynı tanımı kullanır;
 * anahtar tek yerde olduğu için ön yüklenen veri ekran açılınca doğrudan kullanılır.
 */

/** CRM katılımcı tipleri: M7 Yazarlar, M4 Çevirmenler, M8 Çizer & serbest çalışanlar. */
export const CONTRIBUTOR_ROLES = {
  authors: ['Yazar'],
  translators: ['Tercüme'],
  freelancers: ['Çizer', 'Kapak Tasarım', 'Mizanpaj Yapan', 'Redaktör', 'Tashih', 'Yayına Hazırlayan', 'Derleyen', 'Danışman'],
};

/** Yazar giriş süreci: köprü CRM'i beş dakikada bir okur; ekran aynı aralıkla tazelenir. İlk okuma sürerken sık sorar. */
export const INTAKE_REFRESH_MS = 5 * 60_000;

export const intakeBoardOptions = () =>
  queryOptions({
    queryKey: ['editorial', 'intake', 'board'],
    queryFn: intakeApi.board,
    enabled: ENGINE_ENABLED,
    staleTime: 60_000,
    refetchInterval: (query) => (query.state.data?.loading ? 10_000 : INTAKE_REFRESH_MS),
    refetchOnWindowFocus: false,
  });

export const intakeProjectOptions = (id: string) =>
  queryOptions({ queryKey: ['editorial', 'intake', 'project', id], queryFn: () => intakeApi.project(id), enabled: ENGINE_ENABLED && !!id });

export const intakeMeetingsOptions = () =>
  queryOptions({ queryKey: ['editorial', 'intake', 'meetings'], queryFn: intakeApi.meetings, enabled: ENGINE_ENABLED });

export const intakeAgendaOptions = (day: string) =>
  queryOptions({
    queryKey: ['editorial', 'intake', 'agenda', day],
    queryFn: () => intakeApi.agenda(day),
    enabled: ENGINE_ENABLED && !!day,
    placeholderData: keepPreviousData,
  });

export const contractsSummaryOptions = () =>
  queryOptions({ queryKey: ['editorial', 'contracts', 'summary'], queryFn: contractsApi.summary, enabled: ENGINE_ENABLED });

export const contractsListOptions = (q: string, status: string, kind: string, expiring: boolean, order: string, page: number) =>
  queryOptions({
    queryKey: ['editorial', 'contracts', q, status, kind, expiring, order, page],
    queryFn: () =>
      contractsApi.list({ q, status: status ? Number(status) : undefined, kind: kind ? Number(kind) : undefined, expiring, order, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });

export const editorsOverviewOptions = () =>
  queryOptions({ queryKey: ['editorial', 'editors'], queryFn: () => editorsApi.overview(), enabled: ENGINE_ENABLED });

export const projectsListOptions = (q: string, editor: string, status: string, since: number | undefined, page: number) =>
  queryOptions({
    queryKey: ['editorial', 'projects', q, editor, status, since, page],
    queryFn: () => editorsApi.projects({ q, editor: editor || undefined, status: status ? Number(status) : undefined, since, page }),
    enabled: ENGINE_ENABLED && since !== undefined,
    placeholderData: keepPreviousData,
  });

export const roleFacetsOptions = () =>
  queryOptions({ queryKey: ['editorial', 'roles'], queryFn: contributorsApi.roles, enabled: ENGINE_ENABLED });

export const contributorsListOptions = (roles: string[], q: string, order: string, page: number) =>
  queryOptions({
    queryKey: ['editorial', 'contributors', roles, q, order, page],
    queryFn: () => contributorsApi.list({ roles, q, order, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });

/** Ön yüklenen liste bu süre taze sayılır: sayfa yenilense de yeniden istenmez. */
const PREFETCH_FRESH_MS = 5 * 60_000;
/** Aynı anda en çok bu kadar ön yükleme isteği: hepsi CRM'e gider, açık ekranın isteklerini bekletmesin. */
const PREFETCH_PARALLEL = 2;

/** Açık ekranın kendi istekleri bitene kadar bekler (en çok `maxMs`). Ön yükleme onlarla yarışmasın. */
function whenIdle(qc: QueryClient, maxMs = 20_000): Promise<void> {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      unsubscribe();
      window.clearTimeout(cap);
      window.clearTimeout(first);
      resolve();
    };
    const check = () => {
      if (qc.isFetching() === 0) finish();
    };
    const unsubscribe = qc.getQueryCache().subscribe(() => window.setTimeout(check, 0));
    const cap = window.setTimeout(finish, maxMs);
    // Ekran ilk isteklerini atana kadar kısa bir pay; sonra boşsa hemen başlar.
    const first = window.setTimeout(check, 1500);
  });
}

/**
 * Girişten sonra editoryal ekranların açılış görünümleri arka planda alınır; menüden açıldıklarında liste
 * beklemeden ekranda olur. Açık ekranın verisi geldikten sonra başlar, ikişer ikişer gider ve taze olanı
 * yeniden istemez: eskiden her sayfa yüklenişinde sekiz CRM isteği ekranın kendi istekleriyle aynı anda
 * gidiyor, Veri sözlüğü gibi ilgisiz ekranları 20 sn'ye kadar bekletiyordu. Hata ekranı düşürmez.
 */
export async function prefetchEditorialLists(qc: QueryClient, username: string): Promise<void> {
  if (!ENGINE_ENABLED) return;
  await whenIdle(qc);
  const fresh = { staleTime: PREFETCH_FRESH_MS };
  const jobs: Array<() => Promise<unknown>> = [
    () => qc.prefetchQuery({ ...editorialHomeOptions(username), ...fresh }),
    () => qc.prefetchQuery({ ...intakeBoardOptions(), ...fresh }),
    () => qc.prefetchQuery({ ...contractsSummaryOptions(), ...fresh }),
    () => qc.prefetchQuery({ ...contractsListOptions('', '', '', false, 'bitis', 0), ...fresh }),
    () => qc.prefetchQuery({ ...roleFacetsOptions(), ...fresh }),
    ...Object.values(CONTRIBUTOR_ROLES).map((roles) => () => qc.prefetchQuery({ ...contributorsListOptions(roles, '', 'son', 0), ...fresh })),
    // Editör listesi özetten gelen varsayılana (başlangıç yılı) bağlı.
    () =>
      qc
        .fetchQuery({ ...editorsOverviewOptions(), ...fresh })
        .then((o) => qc.prefetchQuery({ ...projectsListOptions('', '', '', o.sinceYear, 0), ...fresh })),
  ];
  let next = 0;
  const worker = async () => {
    while (next < jobs.length) {
      const job = jobs[next++];
      await job().catch(() => undefined);
    }
  };
  await Promise.all(Array.from({ length: PREFETCH_PARALLEL }, worker));
}

/* ------------------------------------------------------------------ M2 editör atama (yazma) */

export const assignKeys = {
  all: ['editorial', 'assign'] as const,
  pending: (q: string, status: string, category: string, page: number) => ['editorial', 'assign', 'pending', q, status, category, page] as const,
  suggest: (project: string, start: string, due: string) => ['editorial', 'assign', 'suggest', project, start, due] as const,
  editors: ['editorial', 'assign', 'editors'] as const,
  calendar: (start: string) => ['editorial', 'assign', 'calendar', start] as const,
  rules: ['editorial', 'assign', 'rules'] as const,
  mine: ['editorial', 'assign', 'mine'] as const,
  history: (id: string) => ['editorial', 'assign', 'history', id] as const,
};

export const assignPendingOptions = (q: string, status: string, category: string, page: number) =>
  queryOptions({
    queryKey: assignKeys.pending(q, status, category, page),
    queryFn: () =>
      assignApi.pending({ q, status: status ? status.split('|').map(Number) : undefined, category: category || undefined, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });

export const assignSuggestOptions = (project: string, start: string, due: string) =>
  queryOptions({
    queryKey: assignKeys.suggest(project, start, due),
    queryFn: () => assignApi.suggest(project, start || undefined, due || undefined),
    enabled: ENGINE_ENABLED && !!project,
    placeholderData: keepPreviousData,
  });

export const assignEditorsOptions = () => queryOptions({ queryKey: assignKeys.editors, queryFn: assignApi.editors, enabled: ENGINE_ENABLED });

export const assignCalendarOptions = (start: string, end: string) =>
  queryOptions({
    queryKey: assignKeys.calendar(start),
    queryFn: () => assignApi.calendar(start, end),
    enabled: ENGINE_ENABLED && !!start,
    placeholderData: keepPreviousData,
  });

export const assignRulesOptions = () => queryOptions({ queryKey: assignKeys.rules, queryFn: assignApi.rules, enabled: ENGINE_ENABLED });

export const myTasksOptions = () => queryOptions({ queryKey: assignKeys.mine, queryFn: assignApi.mine, enabled: ENGINE_ENABLED });

export const taskHistoryOptions = (id: string) =>
  queryOptions({ queryKey: assignKeys.history(id), queryFn: () => assignApi.history(id), enabled: ENGINE_ENABLED && !!id });
