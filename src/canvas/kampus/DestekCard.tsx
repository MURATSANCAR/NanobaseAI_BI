import { ArrowRight, Headset, Plus } from 'lucide-react';

/**
 * Destek masası (NanobaseAI Destek, apps/destek): talep aç ve izle. Masa portalla aynı sunucu adında 8446 portunda
 * çalışır (test sunucusu https://portal.nanobase.ai:8446, müşteri VM'i http://192.168.0.55:8446); adres sayfanın
 * kendi adresinden türetilir, ayar gerekmez. Masa portal oturumuyla kendiliğinden açılır (tek oturum).
 */
export function destekUrl(path = '/helpdesk'): string {
  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8446${path}`;
}

export default function DestekCard() {
  return (
    <section id="destek-masasi" className="kp-card rounded-3xl border border-white/80 bg-white/90 p-4">
      <div className="mb-2 flex items-center gap-2">
        <Headset aria-hidden className="h-4 w-4 shrink-0 text-violet" />
        <h3 className="kp-display truncate text-xs font-bold uppercase tracking-wider text-ink">Destek Masası</h3>
      </div>
      <p className="text-xs text-muted">Bilgisayar, yazılım ya da iş talebinizi buradan açın; talebin durumunu «Taleplerim»den izleyin. Masa yeni sekmede açılır.</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <a
          href={destekUrl('/helpdesk/tickets/new')}
          target="_blank"
          rel="noreferrer"
          className="kp-press flex min-h-11 items-center gap-1.5 rounded-xl bg-violet px-3 text-xs font-semibold text-white hover:bg-violet/90 sm:min-h-0 sm:py-2"
        >
          <Plus aria-hidden className="h-3.5 w-3.5" /> Talep aç
        </a>
        <a
          href={destekUrl('/helpdesk/tickets')}
          target="_blank"
          rel="noreferrer"
          className="kp-press flex min-h-11 items-center gap-1 rounded-lg px-2 text-xs font-semibold text-violet hover:bg-violet/5 sm:min-h-0 sm:py-2"
        >
          Taleplerim <ArrowRight aria-hidden className="h-3.5 w-3.5" />
        </a>
      </div>
    </section>
  );
}
