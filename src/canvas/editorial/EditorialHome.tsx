import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BookOpenCheck, CalendarClock, FileSignature, PenLine, Users } from 'lucide-react';
import { ENGINE_ENABLED, type Work, type ContractPage } from '../engine';
import { useTimasSession } from '../TimasSession';
import { editorialHomeOptions } from './homeQuery';
import { Note, Pill, errText, nf, fmtDate } from '../admin/ui';
import { dateTime } from '../format';
import { ModuleFrame, Panel } from './kit';
import SearchBox from './SearchBox';
import AskBox from './AskBox';

/** Editoryal Süreç ana ekranı: sekiz modülün özeti tek yerde ve kişinin masasında bekleyen iş.
 *  Her rakam modülün kendi ucundan gelir; kaynağı olmayan kart yoktur. */

type Card = {
  to: string;
  title: string;
  icon: typeof Users;
  /** Modülün kendi özetinden tek satır; veri yüklenmediyse boş. */
  line?: string;
  extra?: string;
};

function ModuleCard({ c }: { c: Card }) {
  const Icon = c.icon;
  return (
    <li>
      <Link
        to={c.to}
        className="group flex h-full flex-col rounded-2xl border border-slate-100 bg-white/85 p-3.5 transition-[transform,background-color] duration-150 ease-out hover:bg-white active:scale-[0.99]"
      >
        <span className="flex items-center gap-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-canvas-violet/10 text-canvas-violet">
            <Icon aria-hidden className="h-4 w-4" />
          </span>
          <ArrowRight aria-hidden className="ml-auto h-4 w-4 shrink-0 text-canvas-muted transition-transform duration-150 ease-out group-hover:translate-x-0.5" />
        </span>
        <span className="mt-2 block text-[13.5px] font-extrabold leading-snug">{c.title}</span>
        {c.line && <span className="mt-1 block text-[12px] font-semibold leading-snug text-canvas-ink">{c.line}</span>}
        {c.extra && <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{c.extra}</span>}
      </Link>
    </li>
  );
}

/** Kişinin masasında duran iş: karar bekleyen öneri, onaylanmamış bölüm, imza bekleyen prova. */
function Desk({ works, user }: { works: Work[]; user: string }) {
  const mine = works.filter((w) => w.createdBy.toLowerCase() === user.toLowerCase() || w.members.includes(user.toLowerCase()) || w.signatures.total > 0);
  const openChapters = mine.reduce((a, w) => a + (w.chapters.total - w.chapters.approved), 0);
  const waitingProofs = mine.filter((w) => w.proof && w.signatures.signed < w.signatures.total);
  if (!mine.length) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Masanızdaki eserler</h2>
        <Link to="/redaksiyon" className="text-[11.5px] font-bold text-canvas-violet underline">
          Redaksiyona git
        </Link>
      </div>
      <ul className="mt-2 space-y-1.5">
        {mine.slice(0, 6).map((w) => {
          const open = w.chapters.total - w.chapters.approved;
          return (
            <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
              <span className="min-w-0">
                <span className="block break-words font-semibold leading-snug">{w.title}</span>
                <span className="block text-[11px] text-canvas-muted">
                  {w.manuscript ? `${nf.format(w.chapters.approved)}/${nf.format(w.chapters.total)} bölüm onaylı` : 'Metin yüklenmedi'}
                  {w.proof ? ` · prova v${w.proof.version}` : ''}
                </span>
              </span>
              <span className="flex shrink-0 gap-1.5">
                {open > 0 && <Pill tone="warn">{nf.format(open)} bölüm sürüyor</Pill>}
                {w.proof && w.signatures.total > 0 && w.signatures.signed < w.signatures.total && (
                  <Pill tone="err">{nf.format(w.signatures.total - w.signatures.signed)} imza bekliyor</Pill>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      {(openChapters > 0 || waitingProofs.length > 0) && (
        <p className="mt-2 px-1 text-[11.5px] leading-snug text-canvas-muted">
          Toplam {nf.format(openChapters)} bölüm sürüyor
          {waitingProofs.length ? `, ${nf.format(waitingProofs.length)} prova imza bekliyor` : ''}.
        </p>
      )}
    </Panel>
  );
}

function Expiring({ data }: { data?: ContractPage }) {
  const items = (data?.items ?? []).slice(0, 5);
  if (!items.length) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Süresi yaklaşan sözleşmeler</h2>
        <Link to="/telif-sozlesme" className="text-[11.5px] font-bold text-canvas-violet underline">
          Hepsi ({nf.format(data?.total ?? 0)})
        </Link>
      </div>
      <ul className="mt-2 space-y-1.5">
        {items.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
            <span className="min-w-0">
              <span className="block break-words font-semibold leading-snug">{c.books.map((b) => b.title).join(' · ') || 'Kitap bağlanmamış'}</span>
              <span className="block text-[11px] text-canvas-muted">
                {c.parties.map((p) => p.name).join(', ') || 'Taraf kaydı yok'} · {c.no}
              </span>
            </span>
            <Pill tone={c.daysLeft != null && c.daysLeft <= 14 ? 'err' : 'warn'}>{c.daysLeft != null ? `${nf.format(c.daysLeft)} gün` : dateTime(c.end)}</Pill>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default function EditorialHome() {
  const session = useTimasSession();
  const home = useQuery(editorialHomeOptions(session.data?.username ?? ''));
  const parts = home.data?.parts;
  const works = { data: home.data?.works, isLoading: !home.data?.works };
  const contracts = { data: parts?.contracts.data, isLoading: !parts?.contracts.data };
  const board = { data: parts?.board.data, isLoading: !parts?.board.data };
  const editors = { data: parts?.editors.data, isLoading: !parts?.editors.data };
  const roles = { data: parts?.roles.data };
  const updated = Object.values(parts ?? {}).flatMap((part) => part.updatedAt ? [part.updatedAt] : []);
  const lastUpdated = updated.length ? Math.min(...updated) : null;
  const refreshFailed = Object.values(parts ?? {}).some((part) => part.error);

  const c = contracts.data;
  const year = board.data?.years?.[0];
  const o = editors.data;
  const byRole = (name: string) => roles.data?.items.find((r) => r.role === name)?.people ?? 0;
  const assigned = (o?.items ?? []).reduce((a, b) => a + b.total, 0);
  const unassigned = (o?.unassigned ?? []).reduce((a, b) => a + b.count, 0);
  const desk = works.data?.items ?? [];
  const freelancers = ['Çizer', 'Kapak Tasarım', 'Mizanpaj Yapan', 'Redaktör', 'Tashih', 'Yayına Hazırlayan', 'Derleyen', 'Danışman'].reduce((a, r) => a + byRole(r), 0);

  const cards: Card[] = [
    {
      to: '/yayin-kurulu',
      title: 'Başvuru & Yayın Kurulu',
      icon: BookOpenCheck,
      line: year ? `${year.year}: ${nf.format(year.total)} karar` : undefined,
      extra: year ? `${nf.format(year.sessions)} oturum · son ${dateTime(year.last)}` : undefined,
    },
    {
      to: '/editor-atama',
      title: 'Editör Atama',
      icon: Users,
      line: o ? `${nf.format(o.items.length)} editör` : undefined,
      extra: o ? `${nf.format(assigned)} projede editör var, ${nf.format(unassigned)} projede yok` : undefined,
    },
    {
      to: '/redaksiyon',
      title: 'Redaksiyon',
      icon: PenLine,
      line: !works.data ? 'Okunuyor…' : desk.length ? `${nf.format(desk.filter((w) => w.manuscript).length)} eserde metin var` : 'Henüz metin yüklenmedi',
      extra: !works.data ? undefined : desk.length ? `${nf.format(desk.reduce((a, w) => a + w.chapters.total, 0))} bölüm` : 'DOCX, PDF ya da TXT yükleyin',
    },
    {
      to: '/cevirmenler',
      title: 'Çeviri Yönetimi',
      icon: Users,
      line: roles.data ? `${nf.format(byRole('Tercüme'))} çevirmen` : undefined,
      extra: 'Eser katılım kayıtlarından',
    },
    {
      to: '/son-okuma',
      title: 'Son Okuma',
      icon: FileSignature,
      line: !works.data ? 'Okunuyor…' : desk.length ? `${nf.format(desk.filter((w) => w.proof).length)} eserde prova var` : 'Henüz prova yüklenmedi',
      extra: !works.data ? undefined : desk.some((w) => w.proof) ? `${nf.format(desk.reduce((a, w) => a + w.signatures.signed, 0))}/${nf.format(desk.reduce((a, w) => a + w.signatures.total, 0))} imza` : 'Baskıya giden PDF’i yükleyin',
    },
    {
      to: '/telif-sozlesme',
      title: 'Telif & Sözleşme',
      icon: FileSignature,
      line: c ? `${nf.format(c.active)} yürürlükte sözleşme` : undefined,
      extra: c ? `${nf.format(c.expiring)} tanesi ${c.warnDays} günde bitiyor` : undefined,
    },
    {
      to: '/yazarlar',
      title: 'Yazar İlişkileri',
      icon: Users,
      line: roles.data ? `${nf.format(byRole('Yazar'))} yazar` : undefined,
      extra: 'Eserleri, sözleşmeleri, projeleri',
    },
    {
      to: '/cizer-freelancer',
      title: 'Çizer & Freelancer',
      icon: Users,
      line: roles.data ? `${nf.format(freelancers)} kişi` : undefined,
      extra: roles.data ? `${nf.format(byRole('Çizer'))} çizer, ${nf.format(byRole('Kapak Tasarım'))} kapak tasarımcısı` : undefined,
    },
  ];

  const err = errText(home.error, 'Özet okunamadı.');

  return (
    <ModuleFrame
      route="/editoryal"
      crumb="Editoryal masa"
      title="Editoryal masa"
      lead="Başvurudan baskı onayına kadar sekiz modül. Rakamlar CRM'den ve editoryal masanın kendi kayıtlarından gelir; kaynağı olmayan bir sayı gösterilmez."
      source="Editoryal Süreç"
      aside={<SearchBox />}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{home.data ? 'Veriler yenilenemedi; son alınan bilgiler gösteriliyor.' : err}</Note>}
      <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-canvas-muted" role="status">
        <span>{lastUpdated ? `Son güncelleme: ${fmtDate(new Date(lastUpdated * 1000).toISOString())}` : 'Kaydedilmiş veriler alınıyor…'}</span>
        {home.isFetching && home.data && <span>Güncelleniyor…</span>}
      </div>
      {(refreshFailed || home.data?.stale) && <Note tone="warn">Bazı veriler henüz yenilenemedi. Son başarılı bilgiler korunuyor; güncelleme yeniden denenecek.</Note>}

      {/* Sohbet açılışta ilk sırada: sayılar modül kartlarında zaten var (kullanıcı kararı 09-22). */}
      <AskBox />

      <section>
        <h2 className="px-1 text-[13px] font-extrabold">Modüller</h2>
        <ul className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {cards.map((x) => (
            <ModuleCard key={x.to} c={x} />
          ))}
        </ul>
      </section>

      <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
        <Expiring data={parts?.expiring.data} />
        {works.data && <Desk works={desk} user={works.data.user} />}
      </div>

      <Panel>
        <h2 className="px-1 text-[13px] font-extrabold">Bu masada olmayanlar</h2>
        <ul className="mt-2 space-y-1 px-1 text-[12px] leading-snug text-canvas-muted">
          <li>
            <CalendarClock aria-hidden className="mr-1 inline h-3.5 w-3.5 align-[-2px]" />
            Başvuru kuyruğu ve puanlama: CRM'deki başvuru tablosu kullanılmıyor (19 kayıt, son 2024).
          </li>
          <li>Redaksiyon takvimi ve iş yükü yüzdesi: proje kartındaki aşama ve teslim tarihi alanları neredeyse boş.</li>
          <li>Telif hakedişi ve ödeme takvimi: CRM'de hakediş kaydı yok.</li>
          <li>Kurul oyu, atama, randevu ve freelancer kaydı gibi yazma işlemleri: CRM'e yazma yolu henüz yok.</li>
        </ul>
      </Panel>
    </ModuleFrame>
  );
}
