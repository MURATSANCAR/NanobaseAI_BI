import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Building2, Check } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { btnGhost, btnPrimary, field, label as labelCls } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { corporateApi, fmtShort, parseNum, type Account, type OppInput } from './api';

/** Kurum seçici: Logo KURUM carileri + CRM kurum kartları; listede yoksa ad elle yazılır (fırsat kurum kartsız da açılır). */
export function AccountPicker({ value, onChange }: { value: { ref: string | null; name: string }; onChange: (v: { ref: string | null; name: string }) => void }) {
  const [q, setQ] = useState(value.name);
  const dq = useDebounced(q, 250);
  const list = useQuery({
    queryKey: ['corporate', 'accounts', 'pick', dq],
    queryFn: () => corporateApi.accounts({ q: dq, sort: 'ciro' }),
    enabled: dq.trim().length >= 2 && dq !== value.name,
    staleTime: 60_000,
  });
  return (
    <div className="flex flex-col gap-1">
      <label className={labelCls} htmlFor="corp-acc">Kurum</label>
      <input
        id="corp-acc"
        className={field}
        value={q}
        autoComplete="off"
        placeholder="Unvan, cari kodu ya da il"
        onChange={(e) => {
          setQ(e.target.value);
          onChange({ ref: null, name: e.target.value });
        }}
      />
      {value.ref ? (
        <span className="inline-flex items-center gap-1 text-[11.5px] font-bold text-emerald-700">
          <Check aria-hidden className="h-3.5 w-3.5" /> Kurum kartına bağlı ({value.ref})
        </span>
      ) : (
        q.trim().length >= 2 && <span className="text-[11.5px] text-canvas-muted">Listeden seçilmezse fırsat bu adla, kurum kartına bağlanmadan açılır.</span>
      )}
      {!value.ref && list.data && list.data.items.length > 0 && (
        <ul className="max-h-56 overflow-y-auto rounded-xl border border-slate-100 bg-white">
          {list.data.items.map((a: Account) => (
            <li key={a.ref}>
              <button
                type="button"
                className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-[12.5px] hover:bg-slate-50"
                onClick={() => {
                  setQ(a.unvan ?? a.ref);
                  onChange({ ref: a.ref, name: a.unvan ?? a.ref });
                }}
              >
                <Building2 aria-hidden className="h-4 w-4 shrink-0 text-canvas-muted" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-bold">{a.unvan ?? a.ref}</span>
                  <span className="block truncate text-[11px] text-canvas-muted">
                    {[a.logoKod, a.il, a.segmentLabel, a.buYil ? `bu yıl ${fmtShort(a.buYil)}` : null].filter(Boolean).join(' · ')}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function NewOpportunitySheet({
  open,
  onClose,
  vocabulary,
  busy,
  onCreate,
  initial,
}: {
  open: boolean;
  onClose: () => void;
  vocabulary: string[];
  busy?: boolean;
  onCreate: (b: OppInput) => void;
  initial?: Partial<{ tema: string; deger: number }>;
}) {
  const [acc, setAcc] = useState<{ ref: string | null; name: string }>({ ref: null, name: '' });
  const [ad, setAd] = useState('');
  const [tema, setTema] = useState(initial?.tema ?? '');
  const [deger, setDeger] = useState(initial?.deger ? String(Math.round(initial.deger)) : '');
  const [karar, setKarar] = useState('');
  const [adim, setAdim] = useState('');
  useEffect(() => {
    if (open) {
      setTema(initial?.tema ?? '');
      setDeger(initial?.deger ? String(Math.round(initial.deger)) : '');
    }
  }, [open, initial?.tema, initial?.deger]);
  const ok = acc.name.trim().length > 1 && ad.trim().length > 1;
  return (
    <Sheet open={open} modal onClose={onClose} title="Yeni fırsat" subtitle="Aşama «Aday» olarak başlar; kurum kartına bağlanırsa alım geçmişi fırsatta görünür.">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ok) return;
          onCreate({
            accountRef: acc.ref,
            kurum: acc.name.trim(),
            ad: ad.trim(),
            tema: tema || null,
            deger: parseNum(deger),
            kararTarihi: karar || null,
            sonrakiAdim: adim.trim() || null,
          });
        }}
      >
        <AccountPicker value={acc} onChange={setAcc} />
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Fırsat</span>
          <input className={field} value={ad} onChange={(e) => setAd(e.target.value)} placeholder="Ör. Yeni çalışan paketi, yılsonu hediyesi" />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tema</span>
            <select className={field} value={tema} onChange={(e) => setTema(e.target.value)}>
              <option value="">Seçilmedi</option>
              {vocabulary.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tahmini değer (₺)</span>
            <input className={`${field} font-mono tabular-nums`} inputMode="decimal" value={deger} onChange={(e) => setDeger(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Karar tarihi</span>
            <input type="date" className={field} value={karar} onChange={(e) => setKarar(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sonraki adım</span>
            <input className={field} value={adim} onChange={(e) => setAdim(e.target.value)} placeholder="Ör. İK müdürüyle görüşme" />
          </label>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={!ok || busy}>Fırsatı aç</button>
        </div>
      </form>
    </Sheet>
  );
}
