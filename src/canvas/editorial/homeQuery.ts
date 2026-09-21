import { queryOptions } from '@tanstack/react-query';
import { editorialHomeApi } from '../engine';

export const EDITORIAL_REFRESH_MS = 5 * 60_000;

export const editorialHomeOptions = (username: string) => queryOptions({
  // Existing work mutations invalidate ['editorial', 'works']; include the home desk too.
  queryKey: ['editorial', 'works', 'home', username],
  queryFn: editorialHomeApi.get,
  enabled: Boolean(username),
  staleTime: EDITORIAL_REFRESH_MS,
  gcTime: 30 * 60_000,
  refetchInterval: (query) => query.state.data?.loading ? 10_000 : EDITORIAL_REFRESH_MS,
  refetchIntervalInBackground: true,
  refetchOnWindowFocus: false,
});
