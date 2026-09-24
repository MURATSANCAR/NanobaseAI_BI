import { keepPreviousData, queryOptions, type QueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED, contractsApi, contributorsApi, editorsApi, intakeApi } from '../engine';

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

/**
 * Girişten hemen sonra editoryal ekranların açılış görünümleri arka planda alınır; menüden
 * açıldıklarında liste beklemeden ekranda olur. Hata ekranı düşürmez: ekran açılınca kendisi yeniden dener.
 */
export async function prefetchEditorialLists(qc: QueryClient): Promise<void> {
  if (!ENGINE_ENABLED) return;
  const jobs: Array<Promise<unknown>> = [
    qc.prefetchQuery(intakeBoardOptions()),
    qc.prefetchQuery(contractsSummaryOptions()),
    qc.prefetchQuery(contractsListOptions('', '', '', false, 'bitis', 0)),
    qc.prefetchQuery(roleFacetsOptions()),
    ...Object.values(CONTRIBUTOR_ROLES).map((roles) => qc.prefetchQuery(contributorsListOptions(roles, '', 'son', 0))),
    // Editör listesi özetten gelen varsayılana (başlangıç yılı) bağlı.
    qc.fetchQuery(editorsOverviewOptions()).then((o) => qc.prefetchQuery(projectsListOptions('', '', '', o.sinceYear, 0))),
  ];
  await Promise.allSettled(jobs);
}
