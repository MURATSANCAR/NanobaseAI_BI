import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Search, UserPlus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnPrimary, errText, field } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { HeatPill, daysAgo } from '../editorial/authors/shared';
import { fmtInt, fmtMonth, paApi } from './api';
import { PersonForm } from './forms';
import { BASE, Empty, PaFrame, usePaMeta } from './parts';

/** Kişiler: alan, öncelik ve temas zamanına göre süzülen liste. Süzgeçler adres çubuğunda durur. Sessiz tavan yok. */

const SCOPES = [
  { key: '', label: 'Hepsi' },
  { key: 'zamani', label: 'Temas zamanı gelen' },
  { key: 'benim', label: 'Benim ilişkilerim' },
] as const;

export default function PaPeople() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const meta = usePaMeta();
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const [newPerson, setNewPerson] = useState(false);
  const scope = params.get('kapsam') ?? '';
  const fieldKey = params.get('alan') ?? '';
  const priority = params.get('oncelik') ?? '';
  const order = params.get('sira') ?? 'zaman';
  const archived = params.get('arsiv') === '1';
  const setParam = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
  };
  const list = useQuery({
    queryKey: ['pa', 'people', dq, scope, fieldKey, priority, order, archived],
    queryFn: () => paApi.people({ q: dq, scope, field: fieldKey, priority, order, archived }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const d = list.data;

  return (
    <PaFrame
      title="Kişiler"
      lead="Akademisyen, eğitimci, gazeteci, STK ve kamu yöneticisi: ilişki kartı, son temas, ilişki ısısı ve son hediye. Alan listesi yönetimce onaylıdır; inanç, siyasi görüş ya da köken gibi özellikler tutulmaz."
      source={d ? `${fmtInt(d.counts.toplam)} kişi` : 'Portal + CRM'}
      aside={
        meta.data?.me.canEdit ? (
          <button type="button" className={`${btnPrimary} w-full lg:w-auto`} onClick={() => setNewPerson(true)}>
            <UserPlus aria-hidden className="h-4 w-4" />
            Yeni kişi
          </button>
        ) : undefined
      }
    >
      <div className="glass-panel flex flex-col gap-2 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl lg:flex-row lg:items-end">
        <label className="block min-w-0 flex-1">
          <span className="sr-only">Ara</span>
          <div className="relative">
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setParam('q', e.target.value);
              }}
              placeholder="Ad, unvan ya da kurum"
              className={`${field} pl-9`}
            />
          </div>
        </label>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:flex">
          <select aria-label="Kapsam" value={scope} onChange={(e) => setParam('kapsam', e.target.value)} className={field}>
            {SCOPES.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
          <select aria-label="Alan" value={fieldKey} onChange={(e) => setParam('alan', e.target.value)} className={field}>
            <option value="">Bütün alanlar</option>
            {(meta.data?.fields ?? []).map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
          <select aria-label="Öncelik" value={priority} onChange={(e) => setParam('oncelik', e.target.value)} className={field}>
            <option value="">Her öncelik</option>
            {(meta.data?.priorities ?? []).map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
          <select aria-label="Sıralama" value={order} onChange={(e) => setParam('sira', e.target.value === 'zaman' ? '' : e.target.value)} className={field}>
            <option value="zaman">Temas sırası</option>
            <option value="sicak">En sıcak</option>
            <option value="ad">Ada göre</option>
          </select>
        </div>
        <label className="flex min-h-11 items-center gap-2 text-[12px] font-semibold">
          <input type="checkbox" checked={archived} onChange={(e) => setParam('arsiv', e.target.checked ? '1' : '')} />
          Arşiv
        </label>
      </div>

      {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {d && (
        <>
          <p className="px-1 text-[12px] text-canvas-muted">
            {fmtInt(d.total)} kişi gösteriliyor · temas zamanı gelen {fmtInt(d.counts.zamani)} · kritik {fmtInt(d.counts.kritik)}
          </p>
          {d.items.length === 0 ? (
            <Empty title="Kişi yok">{scope || fieldKey || priority || dq ? 'Süzgeçleri değiştirin.' : '«Yeni kişi» ile CRM\'deki kişiyi alın ya da elle açın.'}</Empty>
          ) : (
            <ul className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
              {d.items.map((p) => (
                <li key={p.id}>
                  <Link to={`${BASE}/kisi/${p.id}`} className="glass-panel flex h-full flex-col gap-1 rounded-2xl p-3 shadow-glass-float transition-transform duration-150 ease-out active:scale-[0.98]">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="min-w-0 break-words text-[14px] font-extrabold">{p.name}</span>
                      {p.priority === 'kritik' && <Pill tone="warn">Kritik</Pill>}
                      {p.isPublicOfficial && <Pill tone="muted">Kamu görevlisi</Pill>}
                      {p.crmContactId && <Pill tone="violet">CRM</Pill>}
                    </div>
                    <div className="text-[12px] text-canvas-muted">{[p.title, p.orgName, p.city].filter(Boolean).join(' · ') || '—'}</div>
                    <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1 text-[11.5px]">
                      <HeatPill heat={p.heat} />
                      {p.fieldLabel && <Pill tone="muted">{p.fieldLabel}</Pill>}
                      <span className={p.due ? 'font-bold text-amber-800' : 'text-canvas-muted'}>
                        {p.due ? 'Temas zamanı · ' : ''}
                        {daysAgo(p.heat.daysSince)}
                      </span>
                      {p.lastGift && <span className="text-canvas-muted">· son hediye {fmtMonth(p.lastGift.month)}</span>}
                      {p.openSteps > 0 && <span className="text-canvas-muted">· {p.openSteps} açık adım</span>}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <PersonForm open={newPerson} onClose={() => setNewPerson(false)} onSaved={(id) => navigate(`${BASE}/kisi/${id}`)} />
    </PaFrame>
  );
}
