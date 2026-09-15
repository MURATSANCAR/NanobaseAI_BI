import { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED, greetingsApi } from '../engine';

/**
 * Oturum açık her ekranda çalışır: biri beni kutladıysa bildirim çıkar. 30 sn'de bir ve sekmeye dönüldüğünde
 * bakılır. Gösterilen kutlama sunucuda "görüldü" işaretlenir, başka sekmede ya da yenilemede tekrar çıkmaz.
 */
export default function GreetingsInbox() {
  const shown = useRef(new Set<string>());
  const q = useQuery({
    queryKey: ['greetings'],
    queryFn: greetingsApi.state,
    enabled: ENGINE_ENABLED,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    retry: false,
  });

  useEffect(() => {
    const fresh = (q.data?.inbox ?? []).filter((g) => !shown.current.has(g.id));
    if (!fresh.length) return;
    for (const g of fresh) {
      shown.current.add(g.id);
      const what = g.occasion?.toLocaleLowerCase('tr').includes('yıl') ? 'iş yıl dönümünüzü' : 'doğum gününüzü';
      toast(`${g.from} ${what} kutladı 🎉`, {
        id: `greeting-${g.id}`,
        description: g.occasion ? `${g.occasion} · Kampüs` : 'Kampüs',
        duration: 10_000,
      });
    }
    greetingsApi.seen(fresh.map((g) => g.id)).catch(() => {
      // İşaretlenemediyse bir sonraki bakışta yeniden gelir; bu sekmede `shown` tekrarını engeller.
    });
  }, [q.data]);

  return null;
}
