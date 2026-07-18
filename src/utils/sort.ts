/** Sort items by ISO date string, newest first. Missing dates sink to the bottom. */
export function sortByIsoDateDesc<T>(
  items: T[],
  getDate: (item: T) => string | undefined | null,
): T[] {
  return [...items].sort((a, b) => {
    const left = getDate(a) ?? '';
    const right = getDate(b) ?? '';
    if (left === right) return 0;
    if (!left) return 1;
    if (!right) return -1;
    return left > right ? -1 : 1;
  });
}

export function mentionRecency(item: { published_at?: string; collected_at?: string }): string | undefined {
  return item.published_at ?? item.collected_at;
}
