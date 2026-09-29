import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BriefcaseBusiness, Search, X } from 'lucide-react';
import { ENGINE_ENABLED, contributorsApi, freelanceApi, type Contributor, type PersonDetail } from '../engine';
import { canSeePage, usePageAccess } from '../useAdmin';
import { contributorsListOptions, roleFacetsOptions } from './queries';
import { Loading, Note, Pill, btnGhost, errText, field, nf } from '../admin/ui';
import { dateTime, pct, crmLabel } from '../format';
import { Kpi, KpiRow, ModuleFrame, Pager, Panel, useDebounced } from './kit';
import { WebSection } from './web/parts';
import { RelationBody } from './authors/CardPanel';
import SqlInfo from '../components/SqlInfo';
import { RightChips, RightsDetails } from './crmRights';
import { EmptyHint } from '../components/Explain';

/** Esere katkı verenler: yazarlar (M7), çevirmenler (M4), çizer ve serbest çalışanlar (M8). Hepsi CRM'deki
 *  eser katılım kayıtlarından, rol süzgeciyle okunur. Kapasite, puan, hız ve müsaitlik CRM'de tutulmadığı
 *  için gösterilmez. */

export type ContributorModule = {
  route: string;
  crumb: string;
  title: string;
  lead: string;
  /** Bu modülün kapsadığı CRM katılımcı tipleri. */
  roles: string[];
  people: string;
  /** Kişi ayrıntısında M7 ilişki bölümü (randevu, görüşme notu, ısı). */
  relations?: boolean;
};

const statusTone = (s: string | null): 'ok' | 'warn' | 'err' | 'muted' => {
  const t = (s || '').toLocaleLowerCase('tr');
  if (t.includes('yenileme') || t.includes('bekleme')) return 'warn';
  if (t.startsWith('aktif') || t.includes('onaylı') || t.includes('çalışıyor')) return 'ok';
  if (t.includes('fesih') || t.includes('iptal') || t.includes('red')) return 'err';
  return 'muted';
};

function Block({ title, count, info, children }: { title: string; count: number; info?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] font-extrabold">
        {title}
        <span className="font-mono font-semibold tabular-nums text-canvas-muted">{nf.format(count)}</span>
        {info}
      </h3>
      {children}
    </section>
  );
}

/** CRM katılımcı tipi → serbest çalışan iş rolü (kayıt formunu önceden doldurmak için). */
const FREELANCE_ROLE: Record<string, string> = {
  Çizer: 'cizer',
  'Kapak Tasarım': 'kapak',
  'Mizanpaj Yapan': 'mizanpaj',
  Redaktör: 'redaksiyon',
  Tashih: 'tashih',
  'Yayına Hazırlayan': 'yayina-hazirlik',
  Danışman: 'danismanlik',
  Tercüme: 'ceviri',
};

/** Çizer / çevirmen kartında serbest çalışan kaydına geçiş: kayıtlıysa kartı açar, değilse formu CRM'den doldurur. */
function FreelanceLink({ p }: { p: PersonDetail }) {
  const access = usePageAccess();
  const allowed = canSeePage(access, 'serbest-calisanlar');
  const role = p.works.map((w) => FREELANCE_ROLE[w.role ?? '']).find(Boolean);
  const hit = useQuery({ queryKey: ['fl', 'lookup', p.id], queryFn: () => freelanceApi.lookup([p.id]), enabled: ENGINE_ENABLED && allowed && !!role });
  if (!allowed || !role || !hit.data) return null;
  const id = hit.data.items[p.id.toLowerCase()];
  const to = id
    ? `/serbest-calisanlar?bolum=kisiler&kisi=${encodeURIComponent(id)}`
    : `/serbest-calisanlar?bolum=kisiler&yeni=kisi&crm=${encodeURIComponent(p.id)}&ad=${encodeURIComponent(p.name ?? '')}&rol=${role}`;
  return (
    <Link to={to} className={`${btnGhost} mt-2`}>
      <BriefcaseBusiness aria-hidden className="h-4 w-4" />
      {id ? 'Serbest çalışan kartı' : 'Serbest çalışan havuzuna ekle'}
    </Link>
  );
}

function Relations({ p }: { p: PersonDetail }) {
  const navigate = useNavigate();
  return (
    <section className="mt-4">
      <h3 className="text-[12px] font-extrabold">İlişki</h3>
      <div className="mt-1.5">
        <RelationBody
          compact
          target={{ crm: { id: p.id, name: p.name || 'Yazar' } }}
          onOpenCard={(id) => navigate(`/yazar-iliskileri?kart=${encodeURIComponent(id)}`)}
        />
      </div>
    </section>
  );
}

function Detail({ p, onClose, relations }: { p: PersonDetail; onClose: () => void; relations?: boolean }) {
  return (
    <div className="text-[12.5px]">
      <div className="flex items-start justify-between gap-2">
        <h2 className="min-w-0 break-words text-[17px] font-extrabold leading-tight tracking-tight">{p.name || 'Adı kayıtlı değil'}</h2>
        <button type="button" onClick={onClose} aria-label="Ayrıntıyı kapat" className={`${btnGhost} shrink-0 px-2.5`}>
          <X aria-hidden className="h-4 w-4" />
        </button>
      </div>
      <FreelanceLink p={p} />
      {p.bio && <p className="mt-2 max-h-40 overflow-y-auto whitespace-pre-line leading-snug text-canvas-muted">{p.bio}</p>}

      {relations && <Relations p={p} />}

      <Block title="Eserler" count={p.works.length} info={<SqlInfo k={p.kaynaklar} alan="sayac.eser" label="Eserler" />}>
        {p.truncated && <p className="mt-1 text-[11px] text-canvas-muted">Liste çok uzun olduğu için kısaltıldı; eserlerin tamamı gösterilmiyor.</p>}
        <ul className="mt-1.5 max-h-72 space-y-1 overflow-y-auto pr-1">
          {p.works.map((w, i) => (
            <li key={`${w.bookId}-${w.role}-${i}`} className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 break-words">{w.title || 'Kitap bağlanmamış'}</span>
              <span className="shrink-0 text-[11px] text-canvas-muted">{w.role}</span>
            </li>
          ))}
        </ul>
      </Block>

      <WebSection kind="person" id={p.id} />

      {p.contracts.length > 0 && (
        <Block
          title="Sözleşmeler"
          count={p.contracts.length}
          info={
            <>
              <SqlInfo k={p.kaynaklar} alan="sayac.sozlesme" label="Sözleşme sayısı" />
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-canvas-muted">
                telif oranı <SqlInfo k={p.kaynaklar} alan="contracts[]" label="Sözleşmeler ve telif oranı" />
              </span>
            </>
          }
        >
          <ul className="zk-scroll mt-1.5 max-h-[28rem] space-y-2 overflow-y-auto overscroll-contain pr-1">
            {p.contracts.map((c) => (
              <li key={c.id} className="border-t border-slate-100 pt-1.5 first:border-t-0 first:pt-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span className="font-mono text-[11.5px] tabular-nums">{c.no || '—'}</span>
                  {c.status && <Pill tone={statusTone(c.status)}>{crmLabel(c.status)}</Pill>}
                  {c.kind && <span className="text-[11px] text-canvas-muted">{crmLabel(c.kind)}</span>}
                  <span className="font-mono text-[11px] tabular-nums text-canvas-muted">
                    {dateTime(c.start)} – {dateTime(c.end)}
                  </span>
                  {c.royalty != null && <span className="text-[11px] text-canvas-muted">telif {pct(c.royalty, 0)}</span>}
                </div>
                <div className="mt-1">
                  <RightChips rights={c.rights} compact />
                </div>
                <RightsDetails rights={c.rights} license={c.license} />
              </li>
            ))}
          </ul>
        </Block>
      )}

      {p.projects.length > 0 && (
        <Block title="Projeler" count={p.projects.length} info={<SqlInfo k={p.kaynaklar} alan="sayac.proje" label="Projeler" />}>
          <ul className="mt-1.5 max-h-60 space-y-1.5 overflow-y-auto pr-1">
            {p.projects.map((j) => (
              <li key={j.id}>
                <div className="break-words font-semibold">{j.name || 'Adsız proje'}</div>
                <div className="text-[11px] text-canvas-muted">{[j.status, j.text, j.editor && `Editör: ${j.editor}`].filter(Boolean).join(' · ')}</div>
              </li>
            ))}
          </ul>
        </Block>
      )}
    </div>
  );
}

function Row({ c, active, onOpen }: { c: Contributor; active: boolean; onOpen: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-pressed={active}
        className={`flex w-full items-center justify-between gap-3 rounded-2xl border px-3 py-2.5 text-left text-[12.5px] transition-colors duration-150 ${
          active ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'
        }`}
      >
        <span className="min-w-0">
          <span className="block break-words font-extrabold leading-snug">{c.name || 'Adı kayıtlı değil'}</span>
          <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">
            {c.roles.map((r) => `${r.role} ${nf.format(r.works)}`).join(' · ')}
          </span>
        </span>
        <span className="shrink-0 text-right">
          <span className="block font-mono text-[15px] font-bold tabular-nums leading-none">{nf.format(c.works)}</span>
          <span className="mt-1 block text-[11px] text-canvas-muted">{c.recentWorks ? `son 12 ayda ${nf.format(c.recentWorks)}` : dateTime(c.last)}</span>
        </span>
      </button>
    </li>
  );
}

export default function ContributorsScreen({ module: m, aside, initialOpen }: { module: ContributorModule; aside?: React.ReactNode; initialOpen?: string | null }) {
  const [text, setText] = useState('');
  const [role, setRole] = useState('');
  const [order, setOrder] = useState('son');
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(initialOpen ?? null);
  const q = useDebounced(text.trim(), 350);
  const roles = useMemo(() => (role ? [role] : m.roles), [role, m.roles]);

  useEffect(() => setPage(0), [q, role, order]);

  const facets = useQuery({ ...roleFacetsOptions(), enabled: ENGINE_ENABLED && m.roles.length > 1 });
  const list = useQuery(contributorsListOptions(roles, q, order, page));
  const person = useQuery({ queryKey: ['editorial', 'person', open], queryFn: () => contributorsApi.person(open as string), enabled: ENGINE_ENABLED && !!open });

  const data = list.data;
  const items = data?.items ?? [];
  const roleOptions = (facets.data?.items ?? []).filter((f) => m.roles.includes(f.role));
  const err = errText(list.error || person.error, 'Kayıtlar okunamadı.');

  return (
    <ModuleFrame route={m.route} crumb={m.crumb} title={m.title} lead={m.lead} source={data ? `${nf.format(data.total)} ${m.people}` : 'CRM eser katılımları'} aside={aside}>
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda tanımlı değil; ekrandaki bilgiler okunamaz. Sistem yöneticinize haber verin.</Note>}
      {err && <Note tone="err">{err}</Note>}

      {data && (
        <KpiRow>
          <Kpi
            label={m.people}
            value={nf.format(data.total)}
            help={q || role ? 'Süzgece uyan kişi' : 'Eser katılım kaydı olan kişi'}
            explain="CRM'de bu sekmenin rollerinden biriyle en az bir kitaba katılım kaydı olan kişi sayısı. Arama ya da rol seçiliyse yalnız uyanlar sayılır."
            info={<SqlInfo k={data.kaynaklar} alan="total" label={m.people} />}
          />
          <Kpi
            label="Son 12 ayda çalışan"
            value={nf.format(data.activePeople)}
            help="Bu dönemde yeni eser kaydı olan"
            explain="Son 12 ayda en az bir kitaba yeni katılım kaydı açılmış kişiler."
            info={<SqlInfo k={data.kaynaklar} alan="activePeople" label="Son 12 ayda çalışan" />}
          />
          <Kpi
            label="Kişi başına eser"
            value={data.total ? nf.format(Math.round((data.contributions / data.total) * 10) / 10) : '—'}
            help={`${nf.format(data.contributions)} eser katkısı`}
            explain="Her kişinin katkı verdiği farklı kitap sayısının ortalaması; aynı kitapta iki rolü olan kişi o kitabı bir kez sayar."
            info={<SqlInfo k={data.kaynaklar} alan="kisiBasinaEser" label="Kişi başına eser" />}
          />
          <Kpi label="Kapsanan rol" value={nf.format(roles.length)} help={roles.join(', ')} explain="Bu sekmede listelenen CRM katılımcı tipleri. Rol süzgecinden birini seçerseniz yalnız o rol kalır." />
        </KpiRow>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)] lg:items-start lg:gap-4">
        <Panel>
          <div className={`grid gap-2 sm:grid-cols-2 ${m.roles.length > 1 ? 'lg:grid-cols-[minmax(0,1fr)_190px_170px]' : 'lg:grid-cols-[minmax(0,1fr)_170px]'}`}>
            <label className="relative block">
              <span className="sr-only">Kişi ara</span>
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
              <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ad soyad ile arayın" className={`${field} pl-9`} />
            </label>
            {m.roles.length > 1 && (
              <div className="flex min-w-0 items-center gap-1">
                <select aria-label="Rol" value={role} onChange={(e) => setRole(e.target.value)} className={`${field} min-w-0 flex-1`}>
                  <option value="">Tüm roller</option>
                  {roleOptions.map((f) => (
                    <option key={f.role} value={f.role}>
                      {f.role} ({nf.format(f.people)})
                    </option>
                  ))}
                </select>
                <SqlInfo k={facets.data?.kaynaklar} alan="items[]" label="Rol başına kişi sayısı" />
              </div>
            )}
            <select aria-label="Sıralama" value={order} onChange={(e) => setOrder(e.target.value)} className={field}>
              <option value="son">Son çalışan</option>
              <option value="eser">En çok eser</option>
              <option value="ad">Ada göre</option>
            </select>
          </div>
          <Pager page={page} pageSize={data?.pageSize ?? 50} total={data?.total ?? 0} shown={items.length} loading={list.isLoading} fetching={list.isFetching} db={data?.db} onPage={setPage} />
          {!list.isLoading && !items.length && !err && (
            <div className="mt-3">
              <EmptyHint
                title={q || role ? 'Süzgece uyan kişi yok' : 'Bu sekmede kişi yok'}
                why={q || role ? 'Adı farklı yazmayı deneyin ya da «Tüm roller»i seçin.' : 'CRM\'de bu rollerle eser katılım kaydı olan kişi bulunamadı.'}
                action={
                  q || role ? (
                    <button
                      type="button"
                      className="min-h-9 rounded-xl bg-slate-100 px-3 text-[12px] font-extrabold hover:bg-slate-200"
                      onClick={() => {
                        setText('');
                        setRole('');
                      }}
                    >
                      Süzgeçleri temizle
                    </button>
                  ) : undefined
                }
              />
            </div>
          )}
          {items.length > 0 && (
            <p className="mt-3 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[11.5px] text-canvas-muted">
              Satırdaki eser, rol ve son 12 ay sayıları
              <SqlInfo k={data?.kaynaklar} alan="items[]" label="Kişi listesi" />
              <span aria-hidden>·</span> toplam
              <SqlInfo k={data?.kaynaklar} alan="total" label="Süzgece uyan kişi" />
            </p>
          )}
          {items.length > 0 && (
            <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">
              Sağdaki sayı kişinin eser sayısıdır; altında son 12 aydaki eseri ya da son çalıştığı tarih yazar. Kişiye dokunun, ayrıntısı açılsın.
            </p>
          )}
          <ul className="mt-2 grid gap-2 xl:grid-cols-2">
            {items.map((c) => (
              <Row key={c.id} c={c} active={open === c.id} onOpen={() => setOpen(c.id)} />
            ))}
          </ul>
        </Panel>

        {/* Telefonda ayrıntı listenin üstüne gelir; masaüstünde sağda durur. */}
        {open && (
          <div className="order-first lg:sticky lg:top-0 lg:order-none">
            <Panel>{person.data && person.data.id === open ? <Detail p={person.data} onClose={() => setOpen(null)} relations={m.relations} /> : <Loading />}</Panel>
          </div>
        )}
      </div>
    </ModuleFrame>
  );
}
