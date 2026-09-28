import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, Section, btnPrimary, errText, field } from '../admin/ui';
import { fmtDay, readersApi, type ReaderSummary } from './api';
import { ConsentPill, ROOT, useMeta } from './parts';
import SqlInfo from '../components/SqlInfo';

/** Okur ara: e-posta, cep telefonu ya da okur numarasıyla kesin arama (özet üzerinden). Ada göre arama yalnız kişisel veri yetkisiyle. */
export default function ReaderSearch() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const [text, setText] = useState(q);
  const meta = useMeta();
  const res = useQuery({ queryKey: ['readers', 'search', q], queryFn: () => readersApi.search(q), enabled: ENGINE_ENABLED && q.trim().length > 0 });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setParams(text.trim() ? { q: text.trim() } : {});
  };
  return (
    <Section
      title="Okur ara"
      help={meta.data?.me.canPersonal
        ? 'E-posta, cep telefonu, okur numarası ya da ad (en az 3 harf). Ada göre arama değişiklik kaydına geçer.'
        : 'E-posta, cep telefonu ya da okur numarasıyla. Yazılan değer saklanmaz; özetiyle eşleştirilir.'}
    >
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="okur-ara">Arama</label>
        <input id="okur-ara" className={field} value={text} onChange={(e) => setText(e.target.value)} placeholder="ornek@eposta.com, 05xx xxx xx xx ya da OK…" autoComplete="off" />
        <button type="submit" className={btnPrimary}><Search aria-hidden className="h-4 w-4" />Ara</button>
      </form>
      {res.isFetching && <Loading />}
      {res.error && <Note tone="err">{errText(res.error, 'Arama yapılamadı.')}</Note>}
      {res.data?.note && <Note tone="info">{res.data.note}</Note>}
      {res.data && !res.data.note && res.data.items.length === 0 && <Note tone="info">Bu değerle eşleşen okur yok.</Note>}
      {res.data && res.data.items.length > 0 && (
        <p className="flex items-center gap-1 text-[11.5px] text-canvas-muted">{res.data.items.length} okur<SqlInfo k={res.data.kaynaklar} alan="items[]" label="Arama sonucu sayıları" /></p>
      )}
      <ul className="flex flex-col gap-2">
        {res.data?.items.map((r) => <ReaderRow key={r.id} r={r} />)}
      </ul>
    </Section>
  );
}

export function ReaderRow({ r }: { r: ReaderSummary }) {
  return (
    <li>
      <Link to={`${ROOT}/kisi/${r.id}`} className="flex flex-col gap-1.5 rounded-2xl border border-slate-100 bg-white/80 p-3 transition-colors duration-150 hover:bg-white sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="font-mono text-[12.5px] font-bold">{r.id}</div>
          <div className="text-[11.5px] text-canvas-muted">
            {r.sources.join(' + ')} · {r.city ?? 'il yok'} · {r.age != null ? `${r.age} yaş` : 'yaş yok'} · son temas {fmtDay(r.lastTouch)}
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          {r.minor && <Pill tone="warn">18 yaş altı</Pill>}
          <ConsentPill prefix="E-posta" status={r.consent.email} />
          <ConsentPill prefix="SMS" status={r.consent.sms} />
          <ConsentPill prefix="KVKK" status={r.consent.kvkk} />
        </div>
      </Link>
    </li>
  );
}
