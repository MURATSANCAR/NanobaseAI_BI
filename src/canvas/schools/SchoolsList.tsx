import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, errText, field, label as labelCls } from '../admin/ui';
import { Pager, useDebounced } from '../editorial/kit';
import { schoolsApi } from './api';
import { CalendarNote, ScoreBadge, daysAgo, fmtDay, useSchoolsMeta } from './parts';
import SqlInfo from '../components/SqlInfo';
import { EmptyHint } from '../components/Explain';

/** Okul listesi: kapsamdaki okullar öncelik sırasıyla (süzgeç: il, ilçe, kademe, tür, puan). Liste kesilmez, sayfalanır.
 *  Okul adıyla arama (en az 3 harf) bütün listede yapılır ki kapsam dışındaki yeni okul da açılabilsin. */

export default function SchoolsList({ params, update }: { params: URLSearchParams; update: (n: Record<string, string | null>) => void }) {
  const meta = useSchoolsMeta();
  const me = meta.data?.me;
  const today = meta.data?.today ?? new Date().toISOString().slice(0, 10);
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 350);
  useEffect(() => {
    if ((params.get('q') ?? '') !== dq) update({ q: dq || null, sayfa: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dq]);
  const f = {
    il: params.get('il') ?? '',
    ilce: params.get('ilce') ?? '',
    kademe: params.get('kademe') ?? '',
    tur: params.get('tur') ?? '',
    oncelik: params.get('oncelik') ?? '',
    q: params.get('q') ?? '',
    kapsam: params.get('kapsam') ?? '',
    sirala: params.get('sirala') ?? 'puan',
    page: Number(params.get('sayfa') ?? 0) || 0,
  };
  const list = useQuery({
    queryKey: ['schools', 'list', f],
    queryFn: () => schoolsApi.list(f),
    enabled: ENGINE_ENABLED && !!meta.data,
    placeholderData: keepPreviousData,
  });
  const d = list.data;
  const set = (k: string) => (v: string) => update({ [k]: v || null, sayfa: null });

  return (
    <div className="flex flex-col gap-3">
      <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
        <label className="relative block">
          <span className="sr-only">Okul ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Okul adıyla ara (bütün liste)" />
        </label>
        <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-6">
          <Select label="İl" value={f.il} onChange={set('il')} options={(meta.data?.ils ?? []).map((x) => ({ key: x, label: x }))} />
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İlçe</span>
            <input className={field} key={f.ilce} defaultValue={f.ilce} onBlur={(e) => set('ilce')(e.target.value.trim())} placeholder="Örn. Kadıköy (boş: hepsi)" />
          </label>
          <Select label="Kademe" value={f.kademe} onChange={set('kademe')} options={meta.data?.kademeler ?? []} />
          <Select label="Kurum türü" value={f.tur} onChange={set('tur')} options={meta.data?.kurumTurleri ?? []} />
          <Select
            label="Sırala"
            value={f.sirala}
            onChange={set('sirala')}
            empty={null}
            options={[
              { key: 'puan', label: 'Öncelik' },
              { key: 'son', label: 'En eski ziyaret' },
              { key: 'ogrenci', label: 'Öğrenci sayısı' },
              { key: 'ad', label: 'Ad' },
            ]}
          />
          {me?.all ? (
            <Select
              label="Kapsam"
              value={f.kapsam}
              onChange={set('kapsam')}
              empty={null}
              options={[
                { key: '', label: 'Bütün okullar' },
                { key: 'benim', label: 'Benim okullarım' },
              ]}
            />
          ) : (
            <Select
              label="En az puan"
              value={f.oncelik}
              onChange={set('oncelik')}
              options={[
                { key: '30', label: '30+' },
                { key: '50', label: '50+' },
                { key: '70', label: '70+' },
              ]}
            />
          )}
        </div>
        {d && (
          <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
            {d.scope === 'benim'
              ? `Kapsamınızdaki okullar (${d.mineCount.toLocaleString('tr-TR')}): CRM'de sahibi, ilin temsilcisi ya da ziyaret sorumlusu olduğunuz ve portalda ziyaret/plan yazdığınız okullar.`
              : 'Bütün okullar.'}{' '}
            Liste CRM ziyaret yerlerinden, {fmtDay(d.asOf)} okundu; listede son değişiklik {fmtDay(d.listChanged)}.{' '}
            <span className="inline-flex items-center gap-0.5 align-middle">
              {d.total.toLocaleString('tr-TR')} okul listede
              <SqlInfo k={d.kaynaklar} alan="total" label="Listedeki okul" />
            </span>
            <span className="ml-1 inline-flex items-center gap-0.5 align-middle">
              öncelik puanı
              <SqlInfo k={d.kaynaklar} alan="items[].score" label="Öncelik puanı" />
            </span>
          </p>
        )}
      </section>

      {list.error && <Note tone="err">{errText(list.error, 'Okul listesi okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {d && d.items.length === 0 && <EmptyHint title="Süzgece uyan okul yok" why="İl, ilçe, kademe ya da puan süzgecini «Hepsi»ne alın. Okul adıyla aramada en az 3 harf yazın; arama bütün listede yapılır." />}

      <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {d?.items.map((s) => (
          <li key={s.id} className="relative">
            <Link
              to={`/okul-tanitim/${s.id}`}
              className="flex h-full items-start gap-2.5 rounded-2xl border border-slate-100 bg-white/90 p-3 pr-10 shadow-sm transition-transform duration-150 ease-out active:scale-[0.99]"
            >
              <ScoreBadge score={s.score} />
              <div className="min-w-0 flex-1">
                <div className="text-[14px] font-extrabold leading-snug">{s.name}</div>
                <div className="mt-0.5 text-[11.5px] font-semibold text-canvas-muted">
                  {[s.ilce ? `${s.ilce}, ${s.il ?? ''}` : s.il, s.kademe, s.kurumTuru, s.students ? `${s.students.toLocaleString('tr-TR')} öğrenci` : 'öğrenci sayısı bilinmiyor']
                    .filter(Boolean)
                    .join(' · ')}
                </div>
                <div className="mt-1 text-[12px] leading-snug">{s.reason}</div>
                <div className="mt-1 text-[11.5px] font-semibold text-canvas-muted">
                  Son ziyaret {daysAgo(s.lastVisit, today)}
                  {s.dealers.length ? ` · Bayi: ${s.dealers.map((x) => x.name).join(', ')}` : ''}
                </div>
                {s.calendar.length > 0 && (
                  <div className="mt-1.5">
                    <CalendarNote hits={s.calendar} />
                  </div>
                )}
              </div>
            </Link>
            {/* «i» bağlantının dışında: tıklama okul kartını açmasın */}
            <span className="absolute right-2 top-2">
              <SqlInfo k={d.kaynaklar} alan="items[]" row={s.id} label={`${s.name}: puan ve öğrenci sayısı`} />
            </span>
          </li>
        ))}
      </ul>
      {d && d.total > 0 && (
        <Pager
          page={d.page}
          pageSize={d.pageSize}
          total={d.total}
          shown={d.items.length}
          loading={list.isLoading}
          fetching={list.isFetching}
          onPage={(p) => update({ sayfa: p ? String(p) : null })}
        />
      )}
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  empty = 'Hepsi',
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ key: string; label: string }>;
  empty?: string | null;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className={labelCls}>{label}</span>
      <select className={field} value={value} onChange={(e) => onChange(e.target.value)}>
        {empty !== null && <option value="">{empty}</option>}
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
