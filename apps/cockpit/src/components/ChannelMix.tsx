import { num, pct, tl } from '../lib/format';
import { InfoTip } from './InfoTip';
import type { Channel } from '../lib/metrics';

export function ChannelMix({ channels, total }: { channels: Channel[]; total: number }) {
  return (
    <section className="card p-5">
      <div className="flex items-center gap-2">
        <h2 className="font-display text-[20px] font-semibold leading-tight">Kanal Payı</h2>
        <InfoTip k="channels" align="right" />
      </div>
      <p className="mt-1 text-[12px] text-ink-muted">Net ciro · cari kartındaki kanal kodu (SPECODE2)</p>
      <ul className="mt-4 space-y-3">
        {channels.map((c) => {
          const share = total > 0 ? Math.max(c.net, 0) / total : 0;
          return (
            <li key={c.channel}>
              <div className="flex items-baseline justify-between text-[12px]">
                <span className="font-semibold">{c.channel}</span>
                <span className="text-ink-muted">
                  {tl(c.net)} · <b className="text-ink">{pct(share, 1)}</b> · {num(c.customers)} cari
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-page">
                <div className="h-1.5 rounded-full bg-brand" style={{ width: `${Math.round(share * 100)}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
