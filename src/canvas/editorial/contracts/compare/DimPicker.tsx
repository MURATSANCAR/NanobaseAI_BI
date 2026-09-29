import type { Meta } from './api';

/**
 * Ek kıyas ölçütleri (ajans, satış dilimi, hedef kitle, tür, yerli/çeviri): dokunulan ölçüt açılır/kapanır. Değer
 * virgüllü dizedir; boş dize = hiçbiri. Satış hazırlığı yoksa satış dilimi pasif ve nedeni yazılı.
 */
export default function DimPicker({ meta, value, onChange }: { meta: Meta; value: string[]; onChange: (v: string) => void }) {
  const ids = Object.keys(meta.olcutler);
  const toggle = (id: string) => {
    const next = value.includes(id) ? value.filter((x) => x !== id) : [...value, id];
    onChange(ids.filter((x) => next.includes(x)).join(','));
  };
  return (
    <div>
      <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Ek kıyas ölçütleri</span>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {ids.map((id) => {
          const off = id === 'satis' && !meta.satisVar;
          const on = value.includes(id) && !off;
          return (
            <button
              key={id}
              type="button"
              aria-pressed={on}
              disabled={off}
              title={off ? 'Logo satış hazırlığı bu kurulumda yok (Yazar ilişkileri); satış dilimi kullanılamıyor.' : undefined}
              onClick={() => toggle(id)}
              className={`inline-flex min-h-11 items-center rounded-xl border px-2.5 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-50 sm:min-h-8 ${
                on ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/80'
              }`}
            >
              {meta.olcutler[id]}
            </button>
          );
        })}
      </div>
    </div>
  );
}
