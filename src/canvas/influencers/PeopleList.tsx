import { useCallback, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import SqlInfo from '../components/SqlInfo';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import { fmtDay, fmtInt, inflApi, type Meta, type PersonRow } from './api';
import PersonForm from './PersonForm';
import { FilePick } from '../components/FileDrop';
import { InflFrame, RelationBadge, TopicPills, useMeta } from './parts';

/** Kayıt defteri: süzgeçler adreste (?q=, ?platform=, ?konu=, ?yas=, ?bos=gün). Liste tavansız. */
export default function PeopleList() {
  const meta = useMeta();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const platform = params.get('platform') ?? '';
  const topic = params.get('konu') ?? '';
  const age = params.get('yas') ?? '';
  const idle = params.get('bos') ? Number(params.get('bos')) : null;
  const update = useCallback((next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    setParams(p, { replace: true });
  }, [params, setParams]);
  const list = useQuery({
    queryKey: ['influencers', 'people', dq, platform, topic, age, idle],
    queryFn: () => inflApi.people({ q: dq, platform, topic, age, idle }),
    enabled: ENGINE_ENABLED,
  });
  const m = meta.data;
  const me = m?.me;
  return (
    <InflFrame
      title="İçerik üreticileri"
      lead="Kim, hangi platformda, hangi konuda; hangi kitapları aldı, ne paylaştı. Sayılar elle ya da CSV ile girilir; resmî API bağlantısı ikinci sürümde."
      aside={m ? (
        <div className="flex flex-wrap items-start gap-2 lg:justify-end">
          {/* CSV içe aktarma yetkisizde de görünür (kilitli, gereken yetki yazılı). */}
          <CsvImport allowed={!!me?.canEdit} />
          {me?.canEdit && <button type="button" className={btnPrimary} onClick={() => setCreating(true)}><Plus aria-hidden className="h-4 w-4" /> Yeni içerik üreticisi</button>}
        </div>
      ) : undefined}
    >
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {m && (
        <Panel>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Ara</span>
              <span className="relative flex items-center">
                <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
                <input className={`${field} pl-9`} value={q} placeholder="Ad, kullanıcı adı, şehir" onChange={(e) => { setQ(e.target.value); update({ q: e.target.value || null }); }} />
              </span>
            </label>
            <Select label="Platform" value={platform} options={m.platformlar} onChange={(v) => update({ platform: v })} />
            <Select label="Konu" value={topic} options={m.konular} onChange={(v) => update({ konu: v })} />
            <Select label="Yaş grubu" value={age} options={m.yasGruplari} onChange={(v) => update({ yas: v })} />
            <Select label="Son işbirliği" value={idle ? String(idle) : ''} options={{ '90': '90 günden eski', '180': '180 günden eski', '365': '1 yıldan eski' }}
              onChange={(v) => update({ bos: v })} />
          </div>
          <div className="mt-3 flex flex-col gap-2">
            {list.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
            {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
            {list.data && !list.data.items.length && <div className="py-8 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte kayıt yok.</div>}
            {list.data?.items.map((p) => <PersonRowCard key={p.id} p={p} meta={m} />)}
          </div>
          {list.data && <div className="mt-2 flex items-center justify-end gap-1 font-mono text-[11.5px] text-canvas-muted">{list.data.total} kişi<SqlInfo k={list.data.kaynaklar} alan="items" label="Kişiler, takipçi ve işbirliği sayıları" /></div>}
        </Panel>
      )}
      {meta.data && <PersonForm open={creating} meta={meta.data} onClose={() => setCreating(false)} onSaved={(id) => nav(`/isbirlikleri/kisi/${id}`)} />}
    </InflFrame>
  );
}

function Select({ label, value, options, onChange }: { label: string; value: string; options: Record<string, string>; onChange: (v: string | null) => void }) {
  return (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{label}</span>
      <select className={field} value={value} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">Hepsi</option>
        {Object.entries(options).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </label>
  );
}

function PersonRowCard({ p, meta }: { p: PersonRow; meta: Meta }) {
  return (
    <Link
      to={`/isbirlikleri/kisi/${p.id}`}
      className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 transition-colors duration-150 hover:border-canvas-violet/40 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_130px_150px] md:items-center"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="break-words text-[13.5px] font-extrabold">{p.name}</span>
          {p.doNotContact && <Pill tone="err">İletişim kurulmasın</Pill>}
          {p.minor && <Pill tone="warn">Reşit değil</Pill>}
          {p.jumps.length > 0 && <Pill tone="warn">Takipçi sıçraması</Pill>}
          {p.openCollabs > 0 && <Pill tone="violet">{p.openCollabs} açık iş</Pill>}
        </div>
        <div className="mt-0.5 break-words text-[12px] text-canvas-muted">
          {p.accounts.map((a) => `${a.platformAdi} @${a.handle}`).join(' · ') || 'hesap yok'}{p.city ? ` · ${p.city}` : ''}
        </div>
      </div>
      <TopicPills keys={p.topics} meta={meta} />
      <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-start md:gap-0.5">
        <span className="font-mono text-[12px] tabular-nums">{p.followers ? `${fmtInt(p.followers)} takipçi` : 'sayı yok'}</span>
        <span className="text-[11.5px] text-canvas-muted">son iş {fmtDay(p.lastCollab)}</span>
      </div>
      <RelationBadge rel={p.relation} />
    </Link>
  );
}

function CsvImport({ allowed }: { allowed: boolean }) {
  const qc = useQueryClient();
  const imp = useMutation({
    mutationFn: async (f: File) => inflApi.importCsv(await f.text(), f.name),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['influencers'] });
      toast.success(`${r.eklenen} yeni kişi, ${r.mevcut} mevcut hesap, ${r.olcum} ölçüm.${r.okunamayan.length ? ` ${r.okunamayan.length} satır okunamadı.` : ''}`);
      if (r.okunamayan.length) toast.message(r.okunamayan.map((x) => `Satır ${x.satir}: ${x.neden}`).join('\n'));
    },
    onError: (e) => toast.error(errText(e, 'Dosya okunamadı.') ?? ''),
  });
  return (
    <FilePick
      label="CSV içe aktar"
      accept=".csv,text/csv,text/plain"
      hint="Başlıklar: Ad; Platform; Kullanıcı adı; Bağlantı; Konu; Yaş grubu; Takipçi; E-posta; Telefon; Şehir; Not"
      feature="isbirligi.duzenle"
      allowed={allowed}
      busy={imp.isPending}
      onPick={(f) => imp.mutate(f)}
    />
  );
}
