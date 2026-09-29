import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ExternalLink, FileText, Loader2, Mail, MessageSquareText, Pencil, Phone, Plus, Search, Trash2, UserPlus, X } from 'lucide-react';
import {
  contributorsApi,
  freelanceApi,
  type FlAway,
  type FlLogoCard,
  type FlPersonDetail,
  type FlRate,
} from '../../engine';
import { CONTRIBUTOR_ROLES } from '../queries';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, nf } from '../../admin/ui';
import { Panel, useDebounced } from '../kit';
import SqlInfo from '../../components/SqlInfo';
import { ConfirmButton, Empty, FieldBox, PAYOUT_STATUS, TASK_STATUS, TagInput, day, editNum, parseNum, pctText, roleLabel, stamp, tl, q2, useFlRefresh, type FlCtx } from './shared';
import { FileDrop } from '../../components/FileDrop';
import { MB } from '../../components/fileDropRules';

// ------------------------------------------------------------------ liste

export default function PeoplePane({ ctx }: { ctx: FlCtx }) {
  const [params, setParams] = useSearchParams();
  const open = params.get('kisi');
  const creating = params.get('yeni') === 'kisi';
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('aktif');
  const q = useDebounced(text.trim(), 250);
  const list = useQuery({ queryKey: ['fl', 'people', q, role, status], queryFn: () => freelanceApi.people({ q, role, status }), placeholderData: (p) => p });
  const items = list.data?.items ?? [];

  const setOpen = (id: string | null) => {
    const next = new URLSearchParams(params);
    next.delete('yeni');
    ['crm', 'ad', 'rol'].forEach((k) => next.delete(k));
    if (id) next.set('kisi', id);
    else next.delete('kisi');
    setEditing(false);
    setParams(next, { replace: true });
  };
  const startNew = () => {
    const next = new URLSearchParams(params);
    next.set('yeni', 'kisi');
    next.delete('kisi');
    setParams(next, { replace: true });
  };

  const side = creating ? (
    <PersonForm ctx={ctx} initial={null} onDone={(id) => setOpen(id)} onCancel={() => setOpen(null)} />
  ) : open ? (
    <PersonDetailPanel ctx={ctx} id={open} editing={editing} onEdit={setEditing} onClose={() => setOpen(null)} />
  ) : null;

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,500px)] lg:items-start lg:gap-4">
      <Panel>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_180px_120px] lg:grid-cols-[minmax(0,1fr)_180px_120px_auto]">
          <label className="relative block sm:col-span-3 lg:col-span-1">
            <span className="sr-only">Kişi ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
            <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ad, e-posta, şehir, üslup" className={`${field} pl-9`} />
          </label>
          <select aria-label="Rol" value={role} onChange={(e) => setRole(e.target.value)} className={field}>
            <option value="">Bütün roller</option>
            {ctx.roles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </select>
          <select aria-label="Durum" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
            <option value="aktif">Aktif</option>
            <option value="pasif">Pasif</option>
            <option value="">Hepsi</option>
          </select>
          {ctx.canManage && (
            <button type="button" className={`${btnPrimary} sm:col-span-3 lg:col-span-1`} onClick={startNew}>
              <UserPlus aria-hidden className="h-4 w-4" />
              Yeni kişi
            </button>
          )}
        </div>
        <div className="mt-3 flex items-center gap-2 text-[12px] font-semibold text-canvas-muted">
          {list.isFetching && <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" />}
          <span className="font-mono tabular-nums">{list.data ? `${nf.format(list.data.total)} kişi` : 'Okunuyor…'}</span>
          {list.data && <SqlInfo k={list.data.kaynaklar} alan="total" label="Kişi sayısı" />}
          {list.data && items.length > 0 && (
            <span className="inline-flex items-center gap-1 font-normal">
              <span aria-hidden>·</span> süren ve geciken iş
              <SqlInfo k={list.data.kaynaklar} alan="items[].stats" label="Kişi başına süren ve geciken iş" />
            </span>
          )}
        </div>
        {list.error && <Note tone="err">{errText(list.error, 'Kişiler okunamadı.')}</Note>}
        {list.data && !items.length && (
          <Empty>
            {q || role || status !== 'aktif'
              ? 'Bu süzgece uyan kişi yok.'
              : ctx.canManage
                ? 'Henüz kayıtlı serbest çalışan yok. «Yeni kişi» ile ekleyin; CRM\'de çizer ya da çevirmen olarak kayıtlı birini oradan seçebilirsiniz.'
                : 'Henüz kayıtlı serbest çalışan yok.'}
          </Empty>
        )}
        <ul className="mt-2 grid gap-2 xl:grid-cols-2">
          {items.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => setOpen(p.id)}
                aria-pressed={open === p.id}
                className={`flex w-full gap-3 rounded-2xl border px-3 py-2.5 text-left text-[12.5px] transition-[border-color,background-color,transform] duration-150 ease-out active:scale-[0.99] ${
                  open === p.id ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'
                }`}
              >
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className="break-words font-extrabold leading-snug">{p.name}</span>
                    {p.status === 'pasif' && <Pill tone="muted">Pasif</Pill>}
                    {p.stats.late > 0 && <Pill tone="err">{p.stats.late} geciken</Pill>}
                  </span>
                  <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">
                    {[p.roles.map((r) => roleLabel(ctx.roles, r)).join(', '), p.city].filter(Boolean).join(' · ')}
                  </span>
                  {p.styles.length > 0 && <span className="mt-1 block truncate text-[11px] font-semibold text-canvas-violet">{p.styles.join(' · ')}</span>}
                </span>
                {!!p.preview?.length && (
                  <span className="flex shrink-0 -space-x-3">
                    {p.preview.map((f) => (
                      <img key={f} src={freelanceApi.portfolioUrl(f)} alt="" loading="lazy" className="h-10 w-10 rounded-lg border-2 border-white object-cover shadow-sm" />
                    ))}
                  </span>
                )}
                <span className="shrink-0 text-right">
                  <span className="block font-mono text-[15px] font-bold tabular-nums leading-none">{p.stats.active}</span>
                  <span className="mt-1 block text-[11px] text-canvas-muted">süren iş</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Panel>
      {side && <div className="order-first lg:sticky lg:top-0 lg:order-none">{side}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ ayrıntı

function PersonDetailPanel({ ctx, id, editing, onEdit, onClose }: { ctx: FlCtx; id: string; editing: boolean; onEdit: (v: boolean) => void; onClose: () => void }) {
  const person = useQuery({ queryKey: ['fl', 'person', id], queryFn: () => freelanceApi.person(id) });
  if (person.error) return <Panel><Note tone="err">{errText(person.error, 'Kişi okunamadı.')}</Note></Panel>;
  if (!person.data) return <Panel><Loading /></Panel>;
  if (editing) return <PersonForm ctx={ctx} initial={person.data} onDone={() => onEdit(false)} onCancel={() => onEdit(false)} />;
  return <PersonDetail ctx={ctx} p={person.data} onEdit={() => onEdit(true)} onClose={onClose} />;
}

function Section({ title, count, info, action, children }: { title: string; count?: number; info?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-4 border-t border-slate-100 pt-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-[12px] font-extrabold">
          {title}
          {count != null && <span className="font-mono font-semibold tabular-nums text-canvas-muted">{nf.format(count)}</span>}
          {info}
        </h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function PersonDetail({ ctx, p, onEdit, onClose }: { ctx: FlCtx; p: FlPersonDetail; onEdit: () => void; onClose: () => void }) {
  const [, setParams] = useSearchParams();
  const refresh = useFlRefresh();
  const toggle = useMutation({
    mutationFn: () => freelanceApi.updatePerson(p.id, { status: p.status === 'aktif' ? 'pasif' : 'aktif' }),
    onSuccess: () => {
      toast.success(p.status === 'aktif' ? `${p.name} pasife alındı.` : `${p.name} yeniden aktif.`);
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const current = p.tasks.filter((t) => ['atandi', 'calisiyor', 'teslim', 'revizyon'].includes(t.status));
  const past = p.tasks.filter((t) => !current.includes(t));

  return (
    <Panel>
      <div className="text-[12.5px]">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="break-words text-[18px] font-extrabold leading-tight tracking-tight">{p.name}</h2>
            <div className="mt-1 flex flex-wrap gap-1">
              {p.roles.map((r) => (
                <Pill key={r} tone="violet">
                  {roleLabel(ctx.roles, r)}
                </Pill>
              ))}
              {p.status === 'pasif' && <Pill tone="muted">Pasif</Pill>}
            </div>
          </div>
          <div className="flex shrink-0 gap-1.5">
            {ctx.canManage && (
              <button type="button" onClick={onEdit} className={`${btnGhost} px-2.5`} aria-label="Düzenle">
                <Pencil aria-hidden className="h-4 w-4" />
              </button>
            )}
            <button type="button" onClick={onClose} aria-label="Ayrıntıyı kapat" className={`${btnGhost} px-2.5`}>
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[12px]">
          {p.email && (
            <a href={`mailto:${p.email}`} className="inline-flex items-center gap-1 font-semibold text-canvas-violet hover:underline">
              <Mail aria-hidden className="h-3.5 w-3.5" />
              {p.email}
            </a>
          )}
          {p.phone && (
            <a href={`tel:${p.phone.replace(/\s/g, '')}`} className="inline-flex items-center gap-1 font-semibold text-canvas-violet hover:underline">
              <Phone aria-hidden className="h-3.5 w-3.5" />
              {p.phone}
            </a>
          )}
          {p.website && (
            <a href={p.website.startsWith('http') ? p.website : `https://${p.website}`} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 font-semibold text-canvas-violet hover:underline">
              <ExternalLink aria-hidden className="h-3.5 w-3.5" />
              Web sitesi
            </a>
          )}
          {p.city && <span className="text-canvas-muted">{p.city}</span>}
        </div>
        {!p.email && <p className="mt-2 text-[11.5px] text-amber-700">E-posta yok: yazışmalar ona e-postayla gidemez.</p>}

        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Süren" value={nf.format(p.stats.active)} info={<SqlInfo k={p.kaynaklar} alan="stats.active" label="Süren iş" />} />
          <Stat label="Tamamlanan" value={nf.format(p.stats.done)} info={<SqlInfo k={p.kaynaklar} alan="stats.done" label="Tamamlanan iş" />} />
          <Stat label="Zamanında" value={pctText(p.stats.onTimeRate)} info={<SqlInfo k={p.kaynaklar} alan="stats.onTimeRate" label="Zamanında teslim" />} />
          <Stat label="Ödenecek" value={tl(p.stats.payable)} info={<SqlInfo k={p.kaynaklar} alan="stats.payable" label="Ödenecek" />} />
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <button type="button" className={btnGhost} onClick={() => setParams({ bolum: 'mesajlar', yazisma: `k:${p.id}` })}>
            <MessageSquareText aria-hidden className="h-4 w-4" />
            Yazışma
          </button>
          {p.crmContactId && (
            <Link to={`/kisiler?rol=cizer&kisi=${encodeURIComponent(p.crmContactId)}`} className={btnGhost}>
              CRM'deki eserleri
            </Link>
          )}
          {ctx.canManage && (
            <ConfirmButton confirm={p.status === 'aktif' ? 'Pasife al?' : 'Aktif et?'} onConfirm={() => toggle.mutate()} disabled={toggle.isPending}>
              {p.status === 'aktif' ? 'Pasife al' : 'Aktif et'}
            </ConfirmButton>
          )}
        </div>

        <Section title="Çalışma bilgisi" info={<SqlInfo k={p.kaynaklar} alan="weeklyHours" label="Haftalık kapasite ve birim ücretler" />}>
          <dl className="mt-1.5 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[12px]">
            <dt className="text-canvas-muted">Haftalık kapasite</dt>
            <dd className="font-semibold">{q2(p.weeklyHours)} saat</dd>
            {p.styles.length > 0 && (
              <>
                <dt className="text-canvas-muted">Üslup</dt>
                <dd className="font-semibold">{p.styles.join(', ')}</dd>
              </>
            )}
            <dt className="text-canvas-muted">Logo cari</dt>
            <dd className="font-mono font-semibold">{p.logoCard || '—'}</dd>
          </dl>
          {p.rates.length > 0 && (
            <ul className="mt-2 space-y-1">
              {p.rates.map((r, i) => (
                <li key={i} className="flex justify-between gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5">
                  <span>{roleLabel(ctx.roles, r.role)}</span>
                  <span className="font-mono font-semibold tabular-nums">
                    {tl(r.price)} / {r.unit}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {p.away.length > 0 && (
            <ul className="mt-2 space-y-1 text-[12px]">
              {p.away.map((a, i) => (
                <li key={i} className="text-amber-800">
                  Müsait değil: {day(a.from)} – {day(a.to)}
                  {a.note ? ` · ${a.note}` : ''}
                </li>
              ))}
            </ul>
          )}
          {p.note && <p className="mt-2 whitespace-pre-line leading-snug text-canvas-muted">{p.note}</p>}
        </Section>

        <Portfolio ctx={ctx} p={p} />

        <Section title="Süren işler" count={current.length} info={<SqlInfo k={p.kaynaklar} alan="sayac.suren" label="Süren işler" />}>
          {!current.length ? <p className="mt-1 text-[12px] text-canvas-muted">Elinde iş yok.</p> : <TaskList tasks={current} />}
        </Section>
        {past.length > 0 && (
          <Section title="Geçmiş işler" count={past.length} info={<SqlInfo k={p.kaynaklar} alan="tasks[]" label="Görevler: miktar ve tutar" />}>
            <TaskList tasks={past} />
          </Section>
        )}

        {p.payouts.length > 0 && (
          <Section title="Hakedişler" count={p.payouts.length} info={<SqlInfo k={p.kaynaklar} alan="sayac.hakedis" label="Hakedişler" />}>
            <ul className="mt-1.5 space-y-1">
              {p.payouts.map((h) => (
                <li key={h.id}>
                  <button type="button" onClick={() => setParams({ bolum: 'hakedis', hakedis: h.id })} className="flex w-full items-center justify-between gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5 text-left hover:bg-slate-100">
                    <span className="font-mono font-semibold">#{h.no}</span>
                    <Pill tone={PAYOUT_STATUS[h.status].tone}>{PAYOUT_STATUS[h.status].label}</Pill>
                    <span className="ml-auto font-mono font-semibold tabular-nums">{tl(h.total)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {p.logoCard && <LogoMovements personId={p.id} />}

        <p className="mt-4 text-[11px] text-canvas-muted">
          Kaydeden {p.createdBy}, {stamp(p.createdAt)}
          {p.updatedAt ? ` · son değişiklik ${p.updatedBy}, ${stamp(p.updatedAt)}` : ''}
        </p>
      </div>
    </Panel>
  );
}

function Stat({ label, value, info }: { label: string; value: string; info?: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-slate-50 px-2.5 py-2">
      <div className="flex items-center justify-between gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
        <span className="min-w-0 truncate">{label}</span>
        {info}
      </div>
      <div className="mt-0.5 truncate font-mono text-[14px] font-bold tabular-nums">{value}</div>
    </div>
  );
}

function TaskList({ tasks }: { tasks: FlPersonDetail['tasks'] }) {
  const [, setParams] = useSearchParams();
  return (
    <ul className="mt-1.5 space-y-1">
      {tasks.map((t) => (
        <li key={t.id}>
          <button type="button" onClick={() => setParams({ bolum: 'paketler', paket: t.packageId })} className="w-full rounded-lg bg-slate-50 px-2.5 py-1.5 text-left hover:bg-slate-100">
            <span className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate font-semibold">{t.title}</span>
              <Pill tone={t.late ? 'err' : TASK_STATUS[t.status].tone}>{t.late ? 'Gecikti' : TASK_STATUS[t.status].label}</Pill>
            </span>
            <span className="mt-0.5 block truncate text-[11px] text-canvas-muted">
              {[t.bookTitle || t.packageTitle, `${q2(t.units)} ${t.unit}`, t.due && `termin ${day(t.due)}`].filter(Boolean).join(' · ')}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------ portfolyo

function Portfolio({ ctx, p }: { ctx: FlCtx; p: FlPersonDetail }) {
  const refresh = useFlRefresh();
  const [tags, setTags] = useState<string[]>([]);
  const [book, setBook] = useState('');
  const remove = useMutation({
    mutationFn: (id: string) => freelanceApi.deletePortfolio(id),
    onSuccess: () => {
      toast.success('Dosya portfolyodan kaldırıldı.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Kaldırılamadı.')),
  });

  return (
    <Section title="Portfolyo" count={p.portfolio.length} info={<SqlInfo k={p.kaynaklar} alan="sayac.portfolyo" label="Portfolyo" />}>
      <div className="mt-2 grid gap-2 rounded-xl bg-slate-50 p-2.5">
        {ctx.canManage && (
          <div className="grid gap-2 sm:grid-cols-2">
            <FieldBox label="Etiketler">
              <TagInput value={tags} onChange={setTags} placeholder="Ör. kapak, suluboya" max={10} />
            </FieldBox>
            <FieldBox label="Kitap (isteğe bağlı)">
              <input value={book} onChange={(e) => setBook(e.target.value)} className={field} placeholder="Hangi işten" />
            </FieldBox>
          </div>
        )}
        {/* Yetkisizde de görünür: kilitli, gereken yetki yazılı. */}
        <FileDrop
          size="sm"
          multiple
          title="Görsel ya da PDF ekle"
          accept=".jpg,.jpeg,.png,.webp,.gif,.pdf"
          maxBytes={40 * MB}
          feature="serbest.yonet"
          allowed={ctx.canManage}
          run={(f) => freelanceApi.addPortfolio(p.id, f, { tags: tags.join(','), book })}
          onDone={(_r, f) => {
            toast.success(`${f.name} portfolyoya eklendi.`);
            refresh();
          }}
        />
      </div>
      {!p.portfolio.length ? (
        <p className="mt-2 text-[12px] text-canvas-muted">Portfolyo boş.</p>
      ) : (
        <ul className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {p.portfolio.map((f) => (
            <li key={f.id} className="group relative overflow-hidden rounded-xl border border-slate-100 bg-white">
              <a href={freelanceApi.portfolioUrl(f.id)} target="_blank" rel="noreferrer" className="block">
                {f.mime.startsWith('image/') ? (
                  <img src={freelanceApi.portfolioUrl(f.id)} alt={f.title || f.filename} loading="lazy" className="aspect-[4/5] w-full object-cover" />
                ) : (
                  <span className="flex aspect-[4/5] w-full flex-col items-center justify-center gap-1 bg-slate-50 text-canvas-muted">
                    <FileText aria-hidden className="h-7 w-7" />
                    <span className="text-[11px] font-bold">PDF</span>
                  </span>
                )}
                <span className="block px-2 py-1.5">
                  <span className="block truncate text-[11.5px] font-bold">{f.title || f.filename}</span>
                  <span className="block truncate text-[10.5px] text-canvas-muted">{[f.book, ...f.tags].filter(Boolean).join(' · ') || stamp(f.uploadedAt)}</span>
                </span>
              </a>
              {ctx.canManage && (
                <div className="absolute right-1 top-1">
                  <ConfirmButton
                    confirm="Sil?"
                    onConfirm={() => remove.mutate(f.id)}
                    className="inline-flex min-h-9 items-center gap-1 rounded-lg bg-white/90 px-2 text-[11px] font-extrabold text-canvas-ink shadow transition-transform duration-150 ease-out active:scale-[0.97]"
                  >
                    <Trash2 aria-hidden className="h-3.5 w-3.5" />
                    <span className="sr-only">Sil</span>
                  </ConfirmButton>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

// ------------------------------------------------------------------ Logo

export function LogoMovements({ personId }: { personId: string }) {
  const [open, setOpen] = useState(false);
  const logo = useQuery({ queryKey: ['fl', 'logo', personId], queryFn: () => freelanceApi.logo(personId), enabled: open, staleTime: 5 * 60_000 });
  const d = logo.data;
  return (
    <Section
      title={`Logo'daki hareketler${d ? ` (${d.year})` : ''}`}
      info={d?.found ? <SqlInfo k={d.kaynaklar} alan="lines[]" label="Logo cari hareketleri" /> : undefined}
      action={
        !open && (
          <button type="button" className={btnGhost} onClick={() => setOpen(true)}>
            Getir
          </button>
        )
      }
    >
      {open && logo.isLoading && <Loading />}
      {logo.error && <Note tone="err">{errText(logo.error, "Logo okunamadı.")}</Note>}
      {d && !d.found && <p className="mt-1 text-[12px] text-amber-700">Bu cari kod Logo'da bulunamadı: {d.code}</p>}
      {d?.found && (
        <>
          <p className="mt-1 text-[11.5px] text-canvas-muted">
            {d.name} {d.specode ? `· ${d.specode}` : ''} {d.last ? `· son hareket ${day(d.last)}` : ''} · alacak: fatura, makbuz, açılış; borç: ödeme, virman
          </p>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Stat label="Alacak" value={tl(d.credit)} info={<SqlInfo k={d.kaynaklar} alan="credit" label="Logo alacak" />} />
            <Stat label="Borç" value={tl(d.debit)} info={<SqlInfo k={d.kaynaklar} alan="debit" label="Logo borç" />} />
            <Stat
              label={(d.balance ?? 0) >= 0 ? 'Borcumuz' : 'Alacağımız'}
              value={tl(Math.abs(d.balance ?? 0))}
              info={<SqlInfo k={d.kaynaklar} alan="balance" label="Logo bakiye" />}
            />
          </div>
          {!d.lines.length ? (
            <p className="mt-2 text-[12px] text-canvas-muted">Bu yıl hareket yok.</p>
          ) : (
            <ul className="mt-2 max-h-64 space-y-1 overflow-y-auto pr-1">
              {d.lines.map((l, i) => (
                <li key={i} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-baseline gap-2 text-[11.5px]">
                  <span className="font-mono tabular-nums text-canvas-muted">{day(l.day)}</span>
                  <span className="min-w-0 truncate">{[l.type, l.text].filter(Boolean).join(' · ')}</span>
                  <span className={`font-mono font-semibold tabular-nums ${l.side === 'borc' ? 'text-emerald-700' : ''}`}>{tl(l.amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Section>
  );
}

// ------------------------------------------------------------------ kayıt formu

type Draft = {
  name: string;
  roles: string[];
  email: string;
  phone: string;
  city: string;
  website: string;
  crmContactId: string;
  crmName: string;
  logoCard: string;
  styles: string[];
  weeklyHours: string;
  rates: Array<{ role: string; unit: string; price: string }>;
  away: Array<{ from: string; to: string; note: string }>;
  note: string;
};

function draftOf(p: FlPersonDetail | null, prefill: URLSearchParams): Draft {
  return {
    name: p?.name ?? prefill.get('ad') ?? '',
    roles: p?.roles ?? (prefill.get('rol') ? [prefill.get('rol') as string] : []),
    email: p?.email ?? '',
    phone: p?.phone ?? '',
    city: p?.city ?? '',
    website: p?.website ?? '',
    crmContactId: p?.crmContactId ?? prefill.get('crm') ?? '',
    crmName: p ? '' : prefill.get('crm') ? prefill.get('ad') ?? '' : '',
    logoCard: p?.logoCard ?? '',
    styles: p?.styles ?? [],
    weeklyHours: editNum(p?.weeklyHours ?? 20),
    rates: (p?.rates ?? []).map((r: FlRate) => ({ role: r.role, unit: r.unit, price: editNum(r.price) })),
    away: (p?.away ?? []).map((a: FlAway) => ({ from: a.from, to: a.to, note: a.note ?? '' })),
    note: p?.note ?? '',
  };
}

function PersonForm({ ctx, initial, onDone, onCancel }: { ctx: FlCtx; initial: FlPersonDetail | null; onDone: (id: string) => void; onCancel: () => void }) {
  const [params] = useSearchParams();
  const [d, setD] = useState<Draft>(() => draftOf(initial, params));
  const [error, setError] = useState<string | null>(null);
  const refresh = useFlRefresh();
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const roleUnit = (role: string) => ctx.roles.find((r) => r.key === role)?.unit ?? 'iş';

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: d.name,
        roles: d.roles,
        email: d.email,
        phone: d.phone,
        city: d.city,
        website: d.website,
        crmContactId: d.crmContactId || null,
        logoCard: d.logoCard,
        styles: d.styles,
        weeklyHours: parseNum(d.weeklyHours),
        rates: d.rates.filter((r) => r.price.trim()).map((r) => ({ role: r.role, unit: r.unit, price: parseNum(r.price) })),
        away: d.away.filter((a) => a.from || a.to),
        note: d.note,
      };
      return initial ? freelanceApi.updatePerson(initial.id, body) : freelanceApi.createPerson(body);
    },
    onSuccess: (p) => {
      toast.success(initial ? 'Kayıt güncellendi.' : `${p.name} havuza eklendi.`);
      refresh();
      onDone(p.id);
    },
    onError: (e) => setError(errText(e, 'Kaydedilemedi.')),
  });

  return (
    <Panel>
      <form
        className="grid gap-3 text-[12.5px]"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          save.mutate();
        }}
      >
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-[17px] font-extrabold leading-tight tracking-tight">{initial ? `${initial.name} · düzenle` : 'Yeni serbest çalışan'}</h2>
          <button type="button" onClick={onCancel} aria-label="Formu kapat" className={`${btnGhost} px-2.5`}>
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>

        <CrmPicker value={d.crmContactId} name={d.crmName} onPick={(id, name) => setD((x) => ({ ...x, crmContactId: id, crmName: name, name: x.name || name }))} />

        <FieldBox label="Ad soyad *">
          <input required value={d.name} onChange={(e) => set('name', e.target.value)} className={field} autoComplete="off" />
        </FieldBox>

        <fieldset>
          <legend className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">İş rolleri *</legend>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {ctx.roles.map((r) => {
              const on = d.roles.includes(r.key);
              return (
                <button
                  key={r.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() => set('roles', on ? d.roles.filter((x) => x !== r.key) : [...d.roles, r.key])}
                  className={`min-h-9 rounded-xl border px-2.5 text-[12px] font-bold transition-[background-color,border-color,transform] duration-150 ease-out active:scale-[0.97] ${
                    on ? 'border-canvas-violet bg-canvas-violet text-white' : 'border-slate-200 bg-white hover:border-canvas-violet'
                  }`}
                >
                  {r.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-2">
          <FieldBox label="E-posta" hint="Yazışma ve atama bildirimi buraya gider.">
            <input type="email" value={d.email} onChange={(e) => set('email', e.target.value)} className={field} autoComplete="off" inputMode="email" />
          </FieldBox>
          <FieldBox label="Telefon">
            <input value={d.phone} onChange={(e) => set('phone', e.target.value)} className={field} inputMode="tel" autoComplete="off" />
          </FieldBox>
          <FieldBox label="Şehir">
            <input value={d.city} onChange={(e) => set('city', e.target.value)} className={field} />
          </FieldBox>
          <FieldBox label="Web sitesi / portfolyo bağlantısı">
            <input value={d.website} onChange={(e) => set('website', e.target.value)} className={field} inputMode="url" placeholder="behance.net/…" />
          </FieldBox>
        </div>

        <FieldBox label="Üslup ve uzmanlık etiketleri" hint="Virgül ya da Enter ile ekleyin (ör. suluboya, çocuk kitabı, dijital).">
          <TagInput value={d.styles} onChange={(v) => set('styles', v)} placeholder="Ör. suluboya, çizgi roman" />
        </FieldBox>

        <div className="grid gap-3 sm:grid-cols-2">
          <FieldBox label="Haftalık kapasite (saat)" hint="Kapasite görünümü ve dağıtım önerisi buna göre hesaplanır.">
            <input value={d.weeklyHours} onChange={(e) => set('weeklyHours', e.target.value)} className={field} inputMode="decimal" />
          </FieldBox>
          <LogoPicker value={d.logoCard} onPick={(code) => set('logoCard', code)} />
        </div>

        <fieldset className="rounded-xl bg-slate-50 p-2.5">
          <div className="flex items-center justify-between gap-2">
            <legend className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Birim ücretler (KDV hariç)</legend>
            <button
              type="button"
              className={`${btnGhost} min-h-9 bg-white px-2.5`}
              onClick={() => {
                const role = d.roles[0] ?? ctx.roles[0]?.key ?? '';
                set('rates', [...d.rates, { role, unit: roleUnit(role), price: '' }]);
              }}
            >
              <Plus aria-hidden className="h-4 w-4" />
              Ücret
            </button>
          </div>
          {!d.rates.length && <p className="mt-1 text-[11.5px] text-canvas-muted">Görev açılırken birim ücret buradan önerilir.</p>}
          <ul className="mt-1.5 space-y-1.5">
            {d.rates.map((r, i) => (
              <li key={i} className="grid grid-cols-[minmax(0,1fr)_96px_110px_auto] gap-1.5">
                <select aria-label="Rol" value={r.role} onChange={(e) => set('rates', d.rates.map((x, j) => (j === i ? { ...x, role: e.target.value, unit: roleUnit(e.target.value) } : x)))} className={field}>
                  {ctx.roles.map((o) => (
                    <option key={o.key} value={o.key}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <select aria-label="Birim" value={r.unit} onChange={(e) => set('rates', d.rates.map((x, j) => (j === i ? { ...x, unit: e.target.value } : x)))} className={field}>
                  {ctx.units.map((u) => (
                    <option key={u} value={u}>
                      {u}
                    </option>
                  ))}
                </select>
                <input aria-label="Ücret (₺)" value={r.price} onChange={(e) => set('rates', d.rates.map((x, j) => (j === i ? { ...x, price: e.target.value } : x)))} className={field} inputMode="decimal" placeholder="₺" />
                <button type="button" aria-label="Satırı kaldır" onClick={() => set('rates', d.rates.filter((_, j) => j !== i))} className={`${btnGhost} min-h-9 bg-white px-2`}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        </fieldset>

        <fieldset className="rounded-xl bg-slate-50 p-2.5">
          <div className="flex items-center justify-between gap-2">
            <legend className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Müsait olmadığı günler</legend>
            <button type="button" className={`${btnGhost} min-h-9 bg-white px-2.5`} onClick={() => set('away', [...d.away, { from: '', to: '', note: '' }])}>
              <Plus aria-hidden className="h-4 w-4" />
              Aralık
            </button>
          </div>
          <ul className="mt-1.5 space-y-1.5">
            {d.away.map((a, i) => (
              <li key={i} className="grid grid-cols-2 gap-1.5 sm:grid-cols-[130px_130px_minmax(0,1fr)_auto]">
                <input aria-label="Başlangıç" type="date" value={a.from} onChange={(e) => set('away', d.away.map((x, j) => (j === i ? { ...x, from: e.target.value } : x)))} className={field} />
                <input aria-label="Bitiş" type="date" value={a.to} onChange={(e) => set('away', d.away.map((x, j) => (j === i ? { ...x, to: e.target.value } : x)))} className={field} />
                <input aria-label="Not" value={a.note} onChange={(e) => set('away', d.away.map((x, j) => (j === i ? { ...x, note: e.target.value } : x)))} className={field} placeholder="İzin, başka proje…" />
                <button type="button" aria-label="Aralığı kaldır" onClick={() => set('away', d.away.filter((_, j) => j !== i))} className={`${btnGhost} min-h-9 bg-white px-2`}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        </fieldset>

        <FieldBox label="Not">
          <textarea value={d.note} onChange={(e) => set('note', e.target.value)} rows={3} className={field} placeholder="Çalışma biçimi, tercihleri, fatura/makbuz durumu…" />
        </FieldBox>

        {error && <Note tone="err">{error}</Note>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onCancel}>
            Vazgeç
          </button>
          <button type="submit" className={btnPrimary} disabled={save.isPending || !d.name.trim() || !d.roles.length}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            {initial ? 'Kaydet' : 'Havuza ekle'}
          </button>
        </div>
      </form>
    </Panel>
  );
}

/** CRM'de eser katılımı olan kişiyi seçer (çizer, çevirmen…); kayıt CRM kişisine bağlanır, ad oradan gelir. */
function CrmPicker({ value, name, onPick }: { value: string; name: string; onPick: (id: string, name: string) => void }) {
  const [text, setText] = useState('');
  const q = useDebounced(text.trim(), 350);
  const roles = useMemo(() => [...CONTRIBUTOR_ROLES.freelancers, ...CONTRIBUTOR_ROLES.translators], []);
  const res = useQuery({ queryKey: ['fl', 'crm-pick', q], queryFn: () => contributorsApi.list({ roles, q, order: 'eser' }), enabled: q.length >= 2 });
  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-xl bg-canvas-violet/10 px-3 py-2 text-[12px]">
        <span className="min-w-0">
          <span className="font-bold text-canvas-violet">CRM kişisi bağlı</span>
          {name && <span className="ml-1 text-canvas-ink">· {name}</span>}
        </span>
        <button type="button" className="text-[11.5px] font-bold text-canvas-violet hover:underline" onClick={() => onPick('', '')}>
          Bağı kaldır
        </button>
      </div>
    );
  }
  return (
    <FieldBox label="CRM'den seç (isteğe bağlı)" hint="CRM'de çizer, çevirmen, redaktör… olarak eser kaydı olan kişi. Seçilirse eserleri kişi kartında görünür.">
      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
        <input type="search" value={text} onChange={(e) => setText(e.target.value)} className={`${field} pl-9`} placeholder="En az iki harf" />
      </div>
      {q.length >= 2 && (
        <ul className="mt-1 max-h-48 overflow-y-auto rounded-xl border border-slate-100 bg-white">
          {res.isLoading && <li className="px-3 py-2 text-[12px] text-canvas-muted">CRM'de aranıyor…</li>}
          {res.error && <li className="px-3 py-2 text-[12px] text-red-700">{errText(res.error, 'CRM okunamadı.')}</li>}
          {res.data && !res.data.items.length && <li className="px-3 py-2 text-[12px] text-canvas-muted">Eşleşen kişi yok.</li>}
          {res.data?.items.map((c) => (
            <li key={c.id}>
              <button type="button" onClick={() => onPick(c.id, c.name || '')} className="w-full px-3 py-2 text-left text-[12px] hover:bg-slate-50">
                <span className="font-bold">{c.name || 'Adı kayıtlı değil'}</span>
                <span className="ml-1 text-canvas-muted">{c.roles.map((r) => `${r.role} ${r.works}`).join(' · ')}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </FieldBox>
  );
}

/** Logo cari kartı arar; özel kodu serbest çalışan olan kartlar önce gelir. */
function LogoPicker({ value, onPick }: { value: string; onPick: (code: string) => void }) {
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const q = useDebounced(text.trim(), 400);
  const res = useQuery({ queryKey: ['fl', 'logo-cards', q], queryFn: () => freelanceApi.logoCards(q), enabled: open && q.length >= 2, staleTime: 5 * 60_000 });
  useEffect(() => {
    if (!open) setText('');
  }, [open]);
  return (
    <FieldBox label="Logo cari kodu" hint="Hakedişin Logo'daki ödeme karşılığını göstermek için.">
      <div className="flex gap-1.5">
        <input value={value} onChange={(e) => onPick(e.target.value)} className={`${field} font-mono`} placeholder="320.01.…" />
        <button type="button" className={`${btnGhost} shrink-0 px-2.5`} onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label="Logo'da ara">
          <Search aria-hidden className="h-4 w-4" />
        </button>
      </div>
      {open && (
        <div className="mt-1 rounded-xl border border-slate-100 bg-white p-1.5">
          <input autoFocus type="search" value={text} onChange={(e) => setText(e.target.value)} className={field} placeholder="Ad ya da kod (en az iki harf)" />
          <ul className="mt-1 max-h-48 overflow-y-auto">
            {res.isFetching && <li className="px-2 py-1.5 text-[12px] text-canvas-muted">Logo'da aranıyor…</li>}
            {res.error && <li className="px-2 py-1.5 text-[12px] text-red-700">{errText(res.error, 'Logo okunamadı.')}</li>}
            {res.data && !res.data.items.length && <li className="px-2 py-1.5 text-[12px] text-canvas-muted">Eşleşen cari yok.</li>}
            {res.data?.items.map((c: FlLogoCard) => (
              <li key={c.code ?? ''}>
                <button
                  type="button"
                  onClick={() => {
                    onPick(c.code ?? '');
                    setOpen(false);
                  }}
                  className="w-full rounded-lg px-2 py-1.5 text-left text-[12px] hover:bg-slate-50"
                >
                  <span className="font-mono font-bold">{c.code}</span> <span>{c.name}</span>
                  {c.specode && <span className={`ml-1 text-[11px] ${c.freelance ? 'font-bold text-canvas-violet' : 'text-canvas-muted'}`}>{c.specode}</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </FieldBox>
  );
}
