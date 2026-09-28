import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { NotebookPen } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, errText, field } from '../admin/ui';
import { Block, Empty, FieldFrame } from '../field/parts';
import { fmtDay } from '../field/api';
import { musteriApi, type Account } from './api';
import { AccountRow, ActionItem, ActionSheet, SubNav } from './parts';
import { RunNotes, useMusteriMeta } from './CustomersHome';

/** Portföyüm (telefon): temsilcinin yalnız kendi carileri — yetkisi olsa da başkasınınki burada yok. Üstte «bu hafta
 *  aranacaklar» (yüksek risk ve kayıp, risk × değer sırası), altında bütün portföy; her kartta tek dokunuşla aksiyon. */

export default function PortfolioPhone() {
  const meta = useMusteriMeta();
  const m = meta.data;
  const [q, setQ] = useState('');
  const list = useQuery({ queryKey: ['musteri', 'mine'], queryFn: () => musteriApi.myPortfolio(), enabled: ENGINE_ENABLED && !!m?.run.asof });
  const [sheet, setSheet] = useState<Account | null>(null);
  const d = list.data;
  const needle = q.trim().toLocaleLowerCase('tr');
  const items = (d?.items ?? []).filter((a) => !needle || `${a.ad ?? ''} ${a.code} ${a.bolge ?? ''}`.toLocaleLowerCase('tr').includes(needle));
  const hot = items.filter((a) => a.duzey === 'yuksek' || a.duzey === 'kayip');
  const rest = items.filter((a) => !(a.duzey === 'yuksek' || a.duzey === 'kayip'));
  const err = errText(meta.error ?? list.error, 'Portföy açılamadı.');

  const quick = (a: Account) =>
    m?.me.canAction ? (
      <button
        type="button"
        aria-label={`${a.ad || a.code} için aksiyon yaz`}
        className="inline-flex w-12 shrink-0 items-center justify-center rounded-2xl border border-slate-100 bg-white/85 text-canvas-violet transition-transform duration-150 ease-out active:scale-[0.96]"
        onClick={() => setSheet(a)}
      >
        <NotebookPen aria-hidden className="h-5 w-5" />
      </button>
    ) : undefined;

  return (
    <FieldFrame
      crumb="Müşteri ilişkileri"
      title="Portföyüm"
      lead="Size atanmış cariler. Risk Logo kesim tarihine göre hesaplanır; CRM'deki yeni sipariş riski yumuşatır."
      source={d?.kesim ? `Logo ${fmtDay(d.kesim)} tarihine kadar` : 'Logo + CRM'}
      presence={d ? `${d.count} cari` : 'Portföy'}
      back={{ to: '/musteri-iliskileri', label: 'Özet' }}
    >
      <SubNav meta={m} />
      {err && <Note tone="err">{err}</Note>}
      {(meta.isLoading || list.isLoading) && <Loading />}
      {m && <RunNotes meta={m} />}
      {d && m && (
        <>
          <label className="flex flex-col gap-1 px-1">
            <span className="sr-only">Portföyde ara</span>
            <input className={field} value={q} placeholder="Portföyde ara: unvan, cari kodu, il" enterKeyHint="search" onChange={(e) => setQ(e.target.value)} />
          </label>
          <Block title={`Bu hafta aranacaklar (${hot.length})`} help="Yüksek risk ve kayıp düzeyindeki carileriniz, risk × değer sırasıyla.">
            {hot.length === 0 ? (
              <Empty>Riskli cariniz yok.</Empty>
            ) : (
              <ul className="flex flex-col gap-2">
                {hot.map((a) => (
                  <AccountRow key={a.code} a={a} trailing={quick(a)} />
                ))}
              </ul>
            )}
          </Block>
          {d.acikAksiyon.length > 0 && (
            <Block title={`Açık aksiyonlar (${d.acikAksiyon.length})`}>
              <ul className="flex flex-col gap-2">
                {d.acikAksiyon.map((x) => (
                  <ActionItem key={x.id} a={x} showCari />
                ))}
              </ul>
            </Block>
          )}
          <Block title={`Diğer carilerim (${rest.length})`}>
            {rest.length === 0 ? (
              <Empty>Başka cari yok.</Empty>
            ) : (
              <ul className="flex flex-col gap-2">
                {rest.map((a) => (
                  <AccountRow key={a.code} a={a} trailing={quick(a)} />
                ))}
              </ul>
            )}
          </Block>
          <ActionSheet open={!!sheet} onClose={() => setSheet(null)} code={sheet?.code ?? ''} ad={sheet?.ad ?? null} meta={m} />
        </>
      )}
    </FieldFrame>
  );
}
