import { keepPreviousData, queryOptions, type QueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED, boardDecisionsApi, contractsApi, contributorsApi, editorsApi } from '../engine';

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

export const boardSummaryOptions = () =>
  queryOptions({ queryKey: ['editorial', 'board', 'summary'], queryFn: boardDecisionsApi.summary, enabled: ENGINE_ENABLED });

export const boardListOptions = (q: string, year: number | null, decision: string, page: number) =>
  queryOptions({
    queryKey: ['editorial', 'board', q, year, decision, page],
    queryFn: () => boardDecisionsApi.list({ q, year: year || undefined, decision: decision ? Number(decision) : undefined, page }),
    enabled: ENGINE_ENABLED && year !== null,
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
    qc.prefetchQuery(contractsSummaryOptions()),
    qc.prefetchQuery(contractsListOptions('', '', '', false, 'bitis', 0)),
    qc.prefetchQuery(roleFacetsOptions()),
    ...Object.values(CONTRIBUTOR_ROLES).map((roles) => qc.prefetchQuery(contributorsListOptions(roles, '', 'son', 0))),
    // Kurul ve editör listeleri özetten gelen varsayılana (en yeni yıl, başlangıç yılı) bağlı.
    qc.fetchQuery(boardSummaryOptions()).then((s) => {
      const year = s.years[0]?.year;
      return year === undefined ? undefined : qc.prefetchQuery(boardListOptions('', year, '', 0));
    }),
    qc.fetchQuery(editorsOverviewOptions()).then((o) => qc.prefetchQuery(projectsListOptions('', '', '', o.sinceYear, 0))),
  ];
  await Promise.allSettled(jobs);
}
