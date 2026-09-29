import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  BookOpenCheck, BookUser, Cake, CircleHelp, FilePlus2, FolderOpen, Lightbulb, Megaphone, MessageSquareHeart, Settings2,
  Target, UserRound, UtensilsCrossed,
} from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, errText, nf } from '../../admin/ui';
import SqlInfo from '../../components/SqlInfo';
import { Block, HrFrame } from '../parts';
import { Avatar, BarList, Stat, Tile } from './parts';
import { dayMonth, longDay, portalApi, type Home, type Stats } from './portalApi';

/** İK ana sayfası (/ik): İnsan Kaynakları modülünün girişi. Eski «Timaş Personel Portal» ana sayfasının kutucukları
 *  (Profilim, rehber, duyurular, doğum günleri, yemek listesi, evrak, SSS) + bugünün özeti; İK yetkilisine kadro
 *  sayıları, yaklaşan tarihler ve eksik belgeler. */

const DIST: { key: keyof Stats['by']; title: string }[] = [
  { key: 'departman', title: 'Departman' },
  { key: 'firma', title: 'Firma' },
  { key: 'ofis_lokasyon', title: 'Ofis lokasyonu' },
  { key: 'calisma_sekli', title: 'Çalışma şekli' },
  { key: 'sube', title: 'Şube' },
  { key: 'cinsiyet', title: 'Cinsiyet' },
];

export default function HrHome() {
  const home = useQuery({ queryKey: ['hr', 'portal', 'home'], queryFn: portalApi.home, enabled: ENGINE_ENABLED });
  const h = home.data;
  // İK'nın öbür ekranları (performans, eğitim, anket…) sayfa yetkisiyle açılır; kutucuk yalnız yetkisi olana görünür.
  const pages = new Set(h?.pages ?? []);
  const hasPage = (id: string) => pages.has('*') || pages.has(`sayfa:${id}`);
  const r = h?.rights;
  const manages = !!r && (r.view || r.edit || r.portal || r.fields);
  return (
    <HrFrame
      crumb="İK ana sayfası"
      title="İnsan Kaynakları"
      lead="Profiliniz, personel rehberi, şirket içi duyurular, doğum günleri, yemek listesi, evrak talebi ve sık sorulan sorular tek yerde."
    >
      {home.error && <Note tone="err">{errText(home.error, 'İK ana sayfası okunamadı.')}</Note>}
      {home.isLoading && <Loading />}
      {h && (
        <>
          <Welcome h={h} />
          <section aria-label="İK ekranları" className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 lg:gap-3">
            <Tile to="/ik/profilim" icon={UserRound} label="Profilim" hint="Özlük bilgilerim ve belgelerim" tone="bg-sky-100 text-sky-700" />
            <Tile to="/ik/rehber" icon={BookUser} label="Personel rehberi" hint="Departman, unvan, e-posta, dahili" tone="bg-amber-100 text-amber-700" />
            <Tile to="/ik/duyurular" icon={Megaphone} label="Şirket içi duyurular" hint="Etkinlik, işe giriş, genel duyuru" tone="bg-rose-100 text-rose-700" />
            <Tile to="/ik/dogum-gunleri" icon={Cake} label="Doğum günleri" hint="Bu ay ve önümüzdeki günler" tone="bg-pink-100 text-pink-700" badge={h.birthdays.filter((b) => b.inDays === 0).length || null} />
            <Tile to="/ik/yemek" icon={UtensilsCrossed} label="Yemek listesi" hint="Bu haftanın ve gelecek haftanın menüsü" tone="bg-orange-100 text-orange-700" />
            <Tile to="/ik/evrak?sekme=talep" icon={FilePlus2} label="Evrak talebi" hint="Çalışma belgesi, bordro, hizmet dökümü…" tone="bg-emerald-100 text-emerald-700" badge={h.myOpenRequests || null} />
            <Tile to="/ik/evrak" icon={FolderOpen} label="Evrak deposu" hint="Formlar ve rehberler" tone="bg-teal-100 text-teal-700" />
            <Tile to="/ik/sss" icon={CircleHelp} label="Sık sorulan sorular" hint="İzin, ücret, çalışma düzeni" tone="bg-indigo-100 text-indigo-700" />
            {hasPage('ik-oneriler') && <Tile to="/ik/oneriler" icon={Lightbulb} label="Öneri kutusu" hint="Adlı ya da adsız öneri ve geri bildirim" tone="bg-yellow-100 text-yellow-700" />}
            {hasPage('ik-egitimlerim') && <Tile to="/ik/egitimlerim" icon={BookOpenCheck} label="Eğitimlerim" hint="Zorunlu eğitimler, oturumlar, sertifikalar" tone="bg-lime-100 text-lime-700" />}
            {hasPage('ik-performansim') && <Tile to="/ik/performansim" icon={Target} label="Performansım" hint="Hedeflerim ve değerlendirmelerim" tone="bg-cyan-100 text-cyan-700" />}
            {hasPage('ik-anketlerim') && <Tile to="/ik/anketlerim" icon={MessageSquareHeart} label="Anketlerim" hint="Açık çalışan anketleri (adsız)" tone="bg-fuchsia-100 text-fuchsia-700" />}
            {manages && <Tile to="/ik/yonetim" icon={Settings2} label="İK yönetimi" hint="Personel girişi, içerik, alanlar ve ayarlar" tone="bg-violet-100 text-canvas-violet" badge={h.stats?.pendingRequests || null} />}
          </section>
          <Today h={h} />
          {h.stats && <HrStats s={h.stats} />}
        </>
      )}
    </HrFrame>
  );
}

function Welcome({ h }: { h: Home }) {
  const sub = [h.me.unvan, h.me.departman].filter(Boolean).join(' · ');
  return (
    <section className="glass-panel flex items-center gap-3 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <Avatar name={h.me.display} src={h.me.hasPhoto ? '/portal/me/photo' : null} size={52} />
      <div className="min-w-0">
        <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Hoş geldiniz</div>
        <div className="truncate text-[18px] font-extrabold tracking-tight">{h.me.display}</div>
        {sub ? <div className="truncate text-[12.5px] text-canvas-muted">{sub}</div> : !h.me.linked && (
          <div className="text-[12px] leading-snug text-canvas-muted">Hesabınız henüz bir özlük kaydına bağlı değil; Profilim boş görünür. İK kaydınızı bağlayınca dolar.</div>
        )}
      </div>
    </section>
  );
}

function Today({ h }: { h: Home }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 lg:gap-4">
      <Block title="Doğum günleri" help="Bugün ve önümüzdeki 7 gün." action={<Link to="/ik/dogum-gunleri" className="text-[12px] font-bold text-canvas-violet hover:underline">Bu ayın listesi</Link>}>
        {h.birthdays.length ? (
          <ul className="flex flex-col gap-2">
            {h.birthdays.map((b) => (
              <li key={b.id} className="flex items-center gap-2.5">
                <Cake aria-hidden className={`h-4 w-4 shrink-0 ${b.inDays === 0 ? 'text-pink-600' : 'text-canvas-muted'}`} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-bold">{b.adSoyad}</div>
                  <div className="truncate text-[11.5px] text-canvas-muted">{[b.departman, b.unvan].filter(Boolean).join(' · ') || '—'}</div>
                </div>
                <span className={`shrink-0 text-[12px] font-bold ${b.inDays === 0 ? 'text-pink-700' : 'text-canvas-muted'}`}>
                  {b.inDays === 0 ? 'Bugün' : b.inDays === 1 ? 'Yarın' : dayMonth(b.day, b.month)}
                </span>
              </li>
            ))}
          </ul>
        ) : <p className="text-[12.5px] text-canvas-muted">Önümüzdeki 7 günde doğum günü yok.</p>}
      </Block>
      <Block title="Son duyurular" action={<Link to="/ik/duyurular" className="text-[12px] font-bold text-canvas-violet hover:underline">Hepsi</Link>}>
        {h.posts.length ? (
          <ul className="flex flex-col divide-y divide-slate-100">
            {h.posts.map((p) => (
              <li key={p.id} className="py-2 first:pt-0 last:pb-0">
                <Link to={`/ik/duyurular#${p.id}`} className="block">
                  <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-violet">{p.category} · {longDay(p.publishDate)}</div>
                  <div className="text-[13px] font-bold leading-snug">{p.title}</div>
                  <div className="line-clamp-2 text-[12px] leading-snug text-canvas-muted">{p.body}</div>
                </Link>
              </li>
            ))}
          </ul>
        ) : <p className="text-[12.5px] text-canvas-muted">Henüz duyuru yok.</p>}
      </Block>
      <Block title="Bugünün menüsü" action={<Link to="/ik/yemek" className="text-[12px] font-bold text-canvas-violet hover:underline">Haftalık menü</Link>}>
        {h.menuToday?.items.length ? (
          <ul className="flex flex-col gap-1 text-[13px]">
            {h.menuToday.items.map((x, i) => (
              <li key={i} className="flex items-start gap-2"><UtensilsCrossed aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-orange-600" />{x}</li>
            ))}
          </ul>
        ) : <p className="text-[12.5px] text-canvas-muted">Bugün için menü girilmemiş.</p>}
      </Block>
    </div>
  );
}

function HrStats({ s }: { s: Stats }) {
  const k = s.kaynaklar;
  const active = s.headcount.active;
  const docsMissing = s.completeness.docs.filter((d) => d.missing > 0);
  return (
    <>
      <div className="px-1 pt-2">
        <h2 className="text-[16px] font-extrabold tracking-tight">İK özeti</h2>
        <p className="text-[12px] text-canvas-muted">Yalnız İK yetkililerine görünür. Rakamlar özlük kaydından, {longDay(s.today)} itibarıyla.</p>
      </div>
      <section aria-label="Kadro sayıları" className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6 lg:gap-3">
        <Stat label="Aktif personel" value={nf.format(active)} help={s.headcount.passive ? `${nf.format(s.headcount.passive)} pasif kayıt` : undefined}
          info={<SqlInfo k={k} alan="headcount" label="Aktif personel" />} />
        <Stat label="Bu ay giren" value={nf.format(s.joined.month)} help={`Yıl içinde ${nf.format(s.joined.year)}`}
          info={<SqlInfo k={k} alan="joined" label="İşe giren" />} />
        <Stat label="Bu ay ayrılan" value={nf.format(s.left.month)} help={`Yıl içinde ${nf.format(s.left.year)}`}
          info={<SqlInfo k={k} alan="left" label="Ayrılan" />} />
        <Stat label="Yıllık devir" value={`%${String(s.left.turnoverYearPct).replace('.', ',')}`} help="Yıl içinde ayrılan ÷ ortalama kadro"
          info={<SqlInfo k={k} alan="left" label="Devir oranı" />} />
        <Stat label="Ortalama kıdem" value={s.avgTenureYears === null ? '—' : `${String(s.avgTenureYears).replace('.', ',')} yıl`}
          help={s.avgAgeYears === null ? undefined : `Ortalama yaş ${String(s.avgAgeYears).replace('.', ',')}`}
          info={<SqlInfo k={k} alan="avgTenureYears" label="Ortalama kıdem" />} />
        <Stat label="Açık evrak talebi" value={nf.format(s.pendingRequests)} help={<Link to="/ik/yonetim?sekme=talepler" className="font-bold text-canvas-violet hover:underline">Talepleri aç</Link>}
          info={<SqlInfo k={k} alan="pendingRequests" label="Açık evrak talebi" />} />
      </section>
      {active === 0 && (
        <Note tone="info">
          Henüz aktif personel kaydı yok. <Link to="/ik/yonetim" className="font-bold text-canvas-violet underline">İK yönetimi</Link>nden personel ekleyin ya da Excel listesini yükleyin.
        </Note>
      )}
      {active > 0 && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 lg:gap-4">
          {DIST.filter((d) => s.by[d.key]).map((d) => (
            <Block key={d.key} title={d.title} help={`Aktif ${nf.format(active)} kişinin dağılımı.`} info={<SqlInfo k={k} alan="by" label={`${d.title} dağılımı`} />}>
              <BarList rows={s.by[d.key] ?? []} total={active} />
            </Block>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 lg:gap-4">
        <Block title="Yaklaşan tarihler" help={`Çalışma izni ve askerlik tecili; ${s.expiryDays} gün içinde bitenler ve geçmiş olanlar.`} info={<SqlInfo k={k} alan="upcoming[]" label="Yaklaşan tarihler" />}>
          {s.upcoming.length ? (
            <ul className="flex flex-col gap-1.5 text-[12.5px]">
              {s.upcoming.map((u) => (
                <li key={`${u.id}-${u.what}`} className="flex items-start justify-between gap-2">
                  <Link to={`/ik/yonetim?kisi=${u.id}`} className="min-w-0">
                    <span className="block truncate font-bold text-canvas-violet hover:underline">{u.adSoyad}</span>
                    <span className="block text-[11.5px] text-canvas-muted">{u.what}</span>
                  </Link>
                  <span className={`shrink-0 text-right text-[12px] font-bold ${u.inDays < 0 ? 'text-red-700' : u.inDays <= 14 ? 'text-amber-700' : 'text-canvas-muted'}`}>
                    {longDay(u.date)}
                    <span className="block text-[11px] font-normal">{u.inDays < 0 ? `${-u.inDays} gün geçti` : u.inDays === 0 ? 'bugün' : `${u.inDays} gün kaldı`}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : <p className="text-[12.5px] text-canvas-muted">Yaklaşan bitiş tarihi yok.</p>}
        </Block>
        <Block title="Bu ayın iş yıldönümleri" info={<SqlInfo k={k} alan="anniversaries[]" label="İş yıldönümleri" />}>
          {s.anniversaries.length ? (
            <ul className="flex flex-col gap-1.5 text-[12.5px]">
              {s.anniversaries.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate font-bold">{a.adSoyad}</span>
                  <span className="shrink-0 text-canvas-muted">{a.day}. gün · {a.years}. yıl</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-[12.5px] text-canvas-muted">Bu ay iş yıldönümü yok.</p>}
        </Block>
        <Block title="Eksik bilgi ve belge" help="Aktif kayıtlarda boş zorunlu alan ve yüklenmemiş belge türü." info={<SqlInfo k={k} alan="completeness" label="Eksik bilgi ve belge" />}>
          <p className="mb-2 text-[12.5px]">
            <span className="font-extrabold tabular-nums">{nf.format(s.completeness.activeMissingRequired)}</span> kayıtta zorunlu alan boş.
          </p>
          {docsMissing.length ? (
            <BarList rows={docsMissing.map((d) => ({ label: d.label, value: d.missing }))} total={active} max={6} />
          ) : s.completeness.docs.length ? <p className="text-[12.5px] text-canvas-muted">Bütün belgeler yüklenmiş.</p> : (
            <p className="text-[12.5px] text-canvas-muted">Belge alanlarını görme yetkiniz yok.</p>
          )}
        </Block>
      </div>
    </>
  );
}
