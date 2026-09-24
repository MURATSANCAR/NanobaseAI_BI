import { createElement } from 'react';
import { BookImage, Contact, FileSignature, House, Newspaper, Languages, LayoutDashboard, PenLine, Route, SpellCheck, UserCog, UsersRound } from 'lucide-react';
import type { AlertSummary } from '../data';
import { conditionLabel, dateTime, money, num, relative } from '../format';
import type { CfoData } from '../cfo';
import type { StitchArc, StitchCanvasData, StitchRailItem } from './data';

/** Halka dilimleri: çevre 87.96 (2πr, r=14). Paylar değerlerden hesaplanır. */
function arcs(values: number[]): [StitchArc, StitchArc, StitchArc, StitchArc] {
  const C = 87.96;
  const total = values.reduce((a, v) => a + Math.max(0, v), 0);
  let off = 0;
  const out = values.slice(0, 4).map((v) => {
    const len = total > 0 ? (C * Math.max(0, v)) / total : 0;
    const a: StitchArc = { dash: `${len.toFixed(2)} ${C}`, offset: `${(-off).toFixed(2)}` };
    off += len;
    return a;
  });
  while (out.length < 4) out.push({ dash: `0 ${C}`, offset: '0' });
  return out as [StitchArc, StitchArc, StitchArc, StitchArc];
}

/** Kart 2'deki 210×50 kıvrım. Tasarımdaki sabit yolun yerine gerçek noktalar. */
function spark(values: number[]): { areaPath: string; linePath: string; dot: [number, number] } {
  if (values.length < 2) {
    return { areaPath: '', linePath: '', dot: [210, 42] };
  }
  const max = Math.max(...values) * 1.08 || 1;
  const min = Math.min(0, ...values);
  const pts = values.map((v, i) => {
    const x = (i * 210) / (values.length - 1);
    const y = 46 - ((v - min) / (max - min || 1)) * 38;
    return [x, y] as [number, number];
  });
  const line = pts.map((p, i) => `${i ? 'L' : 'M'} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const last = pts[pts.length - 1];
  return { areaPath: `${line} L 210 50 L 0 50 Z`, linePath: line, dot: last };
}

/** Raydaki on yuva: tasarımın kendi sırası, uygulamanın gerçek ekranları.
 *  Etiketler src/i18n/tr.json'daki adlarla birebir aynı. */
/** Ray yalnız var olan kanvas ekranlarını gösterir. Ölü bağlantı bırakmıyoruz:
 *  yeni ekran eklendikçe buraya bir satır girer. */
export const railFor = (active: string): StitchRailItem[] => [
  { to: '/genel-bakis', label: 'Genel bakış', badge: active === '/genel-bakis' ? 'Aktif' : undefined },
  { to: '/finansal-denetim', label: 'Finansal Denetim', badge: active === '/finansal-denetim' ? 'Aktif' : undefined },
  { to: '/uyarilar', label: 'Uyarılar', badge: active === '/uyarilar' ? 'Aktif' : undefined },
  { to: '/planli-raporlar', label: 'Planlı raporlar', badge: active === '/planli-raporlar' ? 'Aktif' : undefined },
  { to: '/panolar', label: 'Panolar', badge: active === '/panolar' ? 'Aktif' : undefined },
  { to: '/veri-sozlugu', label: 'Veri Sözlüğü', badge: active === '/veri-sozlugu' ? 'Aktif' : undefined, adminOnly: true },
  { to: '/onaylar', label: 'Onaylar', badge: active === '/onaylar' ? 'Aktif' : undefined, adminOnly: true },
  { to: '/es-anlamlilar', label: 'Eş anlamlılar', badge: active === '/es-anlamlilar' ? 'Aktif' : undefined },
  { to: '/yonetim', label: 'Yönetim', badge: active === '/yonetim' ? 'Aktif' : undefined, adminOnly: true },
  // Editoryal Süreç'e kapı; oradan ray kendi modüllerine döner.
  { to: '/editoryal', label: 'Editoryal', badge: active === '/editoryal' ? 'Aktif' : undefined },
  // Girişten sonraki ana sayfaya dönüş.
  { to: '/', label: 'Kampüs', badge: active === '/' ? 'Aktif' : undefined },
];

/** Editoryal Süreç ekranlarının kendi rayı: üç grup (günlük iş, yayına hazırlık, kayıtlar) ve Kampüs'e dönüş.
 *  Her öğe kendi ikonunu taşır; grup başlığı menü açıkken görünür. */
const railIcon = (icon: typeof House) => createElement(icon, { className: 'w-5 h-5', 'aria-hidden': true });

export const editorialRail = (active: string): StitchRailItem[] =>
  [
    { to: '/editoryal', label: 'Masam', group: 'Günlük', icon: railIcon(LayoutDashboard) },
    { to: '/yazar-giris', label: 'Yazar giriş süreci', group: 'Günlük', icon: railIcon(Route) },
    { to: '/yayin-kurulu', label: 'Yayın kurulu', group: 'Günlük', icon: railIcon(UsersRound) },
    { to: '/redaksiyon', label: 'Redaksiyon', group: 'Yayına hazırlık', icon: railIcon(PenLine) },
    { to: '/kisiler?rol=cevirmen', label: 'Çeviri', group: 'Yayına hazırlık', icon: railIcon(Languages) },
    { to: '/son-okuma', label: 'Son okuma', group: 'Yayına hazırlık', icon: railIcon(SpellCheck) },
    { to: '/kitap-tasarim', label: 'Kitap tasarım', group: 'Yayına hazırlık', icon: railIcon(BookImage) },
    { to: '/kisiler', label: 'Kişiler', group: 'Kayıtlar', icon: railIcon(Contact) },
    { to: '/basin-web', label: 'Basın ve web', group: 'Kayıtlar', icon: railIcon(Newspaper) },
    { to: '/telif-sozlesme', label: 'Sözleşmeler', group: 'Kayıtlar', icon: railIcon(FileSignature) },
    { to: '/editor-atama', label: 'Editörler', group: 'Kayıtlar', icon: railIcon(UserCog) },
    { to: '/', label: 'Kampüs', icon: railIcon(House) },
  ].map((x) => ({ ...x, badge: active === x.to ? 'Aktif' : undefined }));

/** Yönetim Raporları modülünün kendi rayı: grup ana sayfası, raporlar, Kampüs'e dönüş. */
export const managementRail = (active: string): StitchRailItem[] =>
  [
    { to: '/yonetim-raporlari', label: 'Yönetim raporları' },
    { to: '/yonetim-raporlari/baski-oneri', label: 'Yeni baskı öneri' },
    { to: '/', label: 'Kampüs' },
  ].map((x) => ({ ...x, badge: active === x.to ? 'Aktif' : undefined }));

const DOCK = [
  { to: '/genel-bakis', label: 'Genel bakış' },
  { to: '/panolar', label: 'Panolar' },
  { to: '/planli-raporlar', label: 'Planlı raporlar', dot: true },
  { to: '/uyarilar', label: 'Uyarılar' },
];

const base = (crumb: string, source: string, ask: string, q: StitchCanvasData['q'], activeDock = 0) => ({
  tenant: 'Timaş Yayınları',
  section: 'Yapay Zeka Raporları',
  crumb,
  source,
  presence: 'canlı veri',
  zoom: '%100',
  askPlaceholder: ask,
  rail: railFor(DOCK[activeDock]?.to ?? '/'),
  dockLinks: DOCK.map((c, i) => ({ to: c.to, active: i === activeDock, dot: c.dot })),
  dock: DOCK.map((c) => c.label) as [string, string, string, string],
  q,
});

/* ------------------------------- Uyarılar ------------------------------- */

export function alertsData(s: AlertSummary, loading: boolean, source: string): StitchCanvasData {
  const hot = s.proximity[0];
  const latest = [...s.triggered].sort((a, b) => ((a.last_triggered_at ?? '') < (b.last_triggered_at ?? '') ? 1 : -1))[0];
  const withMail = s.total - s.noRecipient.length;
  const calm = Math.max(0, s.active - s.triggered.length - s.errored.length);
  const sp = spark(s.proximity.map((p) => p.pct));
  return {
    ...base('Uyarılar', source, 'Kural yaz… örn. bu ayın iade tutarı 5 milyonu aşarsa haber ver', {
      initials: 'TY',
      role: 'Timaş Yayınları · Uyarılar',
      at: loading ? 'Yükleniyor' : 'Şimdi',
      text: '“Hangi eşik patlamak üzere?”',
    }, 3),
    c1: {
      icon: '🔔',
      title: 'Eşiği aşanlar',
      badge: s.triggered.length ? 'Kritik' : 'Sakin',
      big: num(s.triggered.length),
      bigSuffix: 'kural',
      subLabel: 'Aktif kural:',
      subValue: num(s.active),
      pct: s.active ? (s.triggered.length / s.active) * 100 : 0,
      footL: latest ? `Eşik aşıldı: ${relative(latest.last_triggered_at)}` : 'Aşan kural yok',
      footR: `Toplam: ${num(s.total)}`,
      rowLabel: 'Duraklatılmış:',
      rowValue: num(s.paused),
    },
    c2: {
      title: 'Eşiğe yakınlık',
      badge: `${num(s.active)} aktif`,
      label: hot ? hot.rule.title : 'Ölçüm yok',
      big: hot ? `${Math.round(hot.pct)}` : '—',
      unit: '% yakın',
      delta: hot && hot.distance != null ? `${conditionLabel(hot.rule.condition)} ${num(hot.rule.threshold)}` : '—',
      tick1: s.proximity[1] ? `${Math.round(s.proximity[1].pct)}%` : '—',
      tick2: s.proximity[2] ? `${Math.round(s.proximity[2].pct)}%` : '—',
      tick3: s.proximity[3] ? `${Math.round(s.proximity[3].pct)}%` : '—',
      foot: 'Eşiğe en yakın dört aktif kural',
      ...sp,
    },
    c3: {
      title: 'Durum dağılımı',
      badge: `${num(s.total)} kural`,
      center: num(s.total),
      arcs: arcs([calm, s.triggered.length, s.paused, s.errored.length]),
      rows: [
        { label: 'Sakin:', value: num(calm) },
        { label: 'Eşik aşıldı:', value: num(s.triggered.length) },
        { label: 'Duraklatıldı:', value: num(s.paused) },
        { label: 'Ölçülemedi:', value: num(s.errored.length) },
      ],
      footLabel: 'Son kontrol:',
      footValue: s.lastCheckedAt ? relative(s.lastCheckedAt) : 'henüz yok',
    },
    c4: {
      title: 'Bildirim kanalı',
      badge: !s.email.configured ? 'E-posta kapalı' : s.noRecipient.length ? 'Alıcı eksik' : 'Tam',
      initials: 'EP',
      name: `${num(withMail)} kuralda alıcı var`,
      sub: s.email.configured ? `gönderen: ${s.email.sender ?? ''}` : 'gönderici hesap tanımlı değil',
      valueLabel: 'Alıcısız kural:',
      value: num(s.noRecipient.length),
      note: s.email.configured
        ? 'Alıcısı olmayan kural eşiği aşınca kimseye yazılmaz'
        : 'Hesap tanımlanana kadar uyarılar yalnız bu ekranda görünür',
      footLabel: 'Henüz ölçülmemiş:',
      footValue: num(s.neverChecked.length),
    },
    c5: {
      title: 'Kanıt & Kaynak',
      badge: 'Canlı veri',
      summary: `${num(s.total)} kural · ${num(s.proximity.length)} ölçüm`,
      rows: [
        { name: 'Aktif kural', tag: num(s.active) },
        { name: 'Eşik aşıldı', tag: num(s.triggered.length) },
        { name: 'Ölçülemedi', tag: num(s.errored.length) },
      ],
      latency: s.lastCheckedAt ? dateTime(s.lastCheckedAt) : 'kontrol yok',
    },
    main: {
      badge: 'ZEKİ AI ÖZETİ',
      subject: `Uyarılar · ${num(s.total)} kural`,
      model: s.lastCheckedAt ? `Son kontrol ${relative(s.lastCheckedAt)}` : 'Henüz kontrol edilmedi',
      text: loading
        ? '“Kurallar okunuyor…”'
        : s.total === 0
          ? '“Henüz uyarı kuralı yok. Aşağıya ‘bu ayın iade tutarı 5 milyonu aşarsa haber ver’ yazarak ilkini kurabilirsiniz.”'
          : `“${num(s.active)} kural aktif${s.triggered.length ? `, ${num(s.triggered.length)} tanesi eşiği aşmış` : ''}.${
              hot && hot.distance != null
                ? ` Eşiğe en yakın kural “${hot.rule.title}”: son değer ${num(hot.rule.last_value ?? null)}, eşik ${num(hot.rule.threshold)}.`
                : ''
            }${s.errored.length ? ` ${num(s.errored.length)} kural ölçülemedi.` : ''}${
              s.email.configured ? '' : ' E-posta hesabı tanımlı olmadığı için uyarılar şimdilik yalnız bu ekranda.'
            }”`,
      m1: { label: 'Aktif:', value: num(s.active) },
      m2: { label: 'Duraklatılmış:', value: num(s.paused) },
      m3: { label: 'Alıcısız:', value: num(s.noRecipient.length) },
      primary: 'Kuralları aç',
      primaryTo: '/uyarilar?panel=kurallar',
      secondary: 'Yeni kural',
      secondaryTo: '/uyarilar?panel=yeni',
      note: s.errored.length
        ? `${num(s.errored.length)} kural ölçülemedi`
        : s.neverChecked.length
          ? `${num(s.neverChecked.length)} kural henüz ölçülmedi`
          : s.total
            ? 'Tüm kurallar ölçüldü'
            : 'Kural yok',
    },
    sticker: {
      kicker: 'Eşiğe en yakın',
      meta: hot ? `${Math.round(hot.pct)}%` : '—',
      title: hot?.rule.title ?? 'AKTİF KURAL YOK',
      sub: hot ? `eşik ${num(hot.rule.threshold)}` : '',
      footL: 'son değer',
      footR: hot ? num(hot.rule.last_value ?? null) : '—',
      badge: s.triggered.length ? 'Tetikte ★' : 'Sakin',
    },
    ghost: {
      title: 'Önceki: Bildirim kanalı',
      badge: num(s.noRecipient.length),
      text: s.email.configured
        ? '“Alıcısı olmayan kurallar eşiği aşsa da kimseye e-posta gitmez.”'
        : '“E-posta gönderici hesabı tanımlanınca bekleyen uyarılar gönderilir.”',
      foot: s.lastCheckedAt ? `${dateTime(s.lastCheckedAt)} · son kontrol` : 'kontrol kaydı yok',
    },
  };
}

/* --------------------------- CFO · Genel bakış --------------------------- */


const AY = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
const trPct = (v: number | null, d = 1) => (v == null ? '—' : `%${v.toFixed(d).replace('.', ',')}`);

/**
 * CFO ekranı: canlı rakamlar. Metinler kısa tutulur; kart başına tek
 * cümle, gerisi sayı. Veri gelmiyorsa kart sayı uydurmaz, durumu yazar.
 */
/** Özet saati İstanbul saatiyle. Konteyner UTC'de yazar; metni kesip göstermek saati 3 saat kaydırır. */
function summaryTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(11, 16);
  return d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Istanbul' });
}

export function cfoData(c: CfoData, source: string): StitchCanvasData {
  const durum = c.authRequired ? 'Oturum gerekli' : c.failed ? 'Zeki AI yanıt vermedi' : !c.ready ? 'Yükleniyor' : '';
  const yok = (v: string) => (durum ? '—' : v);
  const son = c.totals?.son_fatura?.slice(0, 10);
  const sonTR = son ? `${son.slice(8, 10)}.${son.slice(5, 7)}` : '—';
  const lastFull = c.months.filter((m) => m.ay < c.observedMonths).slice(-1)[0];
  const prevSame = c.prevMonths.find((m) => m.ay === lastFull?.ay);
  const monthYoY = lastFull && prevSame && prevSame.net_ciro > 0 ? (lastFull.net_ciro / prevSame.net_ciro - 1) * 100 : null;

  const net = (t: number) => c.channels.find((x) => x.trcode === t)?.net_ciro ?? 0;
  const toptan = net(8);
  const perakende = net(7);
  const diger = net(9);
  const iade = Math.abs(net(2) + net(3));

  const top = c.customers[0];
  const item = c.items[0];
  const last3 = c.months.slice(-3);

  return {
    ...base('Genel bakış', source, 'ZEKİ’ye sor… örn. bu ay kanal bazında net ciro', {
      initials: 'TY',
      role: `Timaş Yayınları · ${c.year}`,
      at: durum || (c.generatedAt ? `${summaryTime(c.generatedAt)} özeti` : `${sonTR} itibarıyla`),
      text: '“Bu yıl nasıl gidiyoruz?”',
    }),
    c1: {
      icon: '💰',
      title: 'Net ciro',
      badge: c.yoyPct == null ? String(c.year) : `${c.yoyPct >= 0 ? '+' : ''}${trPct(c.yoyPct)}`,
      big: yok(money(c.netYtd)),
      bigSuffix: '₺',
      subLabel: 'Geçen yıl aynı dönem:',
      subValue: yok(`${money(c.netPrevSame)} ₺`),
      pct: (c.observedMonths / 12) * 100,
      footL: `${c.observedMonths || 0} / 12 ay`,
      footR: `Veri: ${sonTR}`,
      rowLabel: 'Aylık ortalama:',
      rowValue: yok(`${money(c.observedMonths ? c.netYtd / c.observedMonths : 0)} ₺`),
    },
    c2: {
      title: 'Aylık seyir',
      badge: `${c.observedMonths || 0} ay`,
      label: lastFull ? `${AY[lastFull.ay - 1]} (son tam ay)` : 'Ay verisi yok',
      big: yok(money(lastFull?.net_ciro ?? 0)),
      unit: '₺',
      delta: monthYoY == null ? '—' : `${monthYoY >= 0 ? '+' : ''}${trPct(monthYoY)}`,
      tick1: last3[0] ? `${AY[last3[0].ay - 1]} ${money(last3[0].net_ciro)}` : '—',
      tick2: last3[1] ? `${AY[last3[1].ay - 1]} ${money(last3[1].net_ciro)}` : '—',
      tick3: last3[2] ? `${AY[last3[2].ay - 1]} ${money(last3[2].net_ciro)}` : '—',
      foot: `${c.observedMonths || 0} ay gerçekleşti`,
      ...spark(c.months.map((m) => m.net_ciro)),
    },
    c3: {
      title: 'Kanal dağılımı',
      badge: `${c.year} · brüt`,
      center: yok(money(toptan + perakende + diger + iade)),
      arcs: arcs([toptan, perakende, diger, iade]),
      rows: [
        { label: 'Toptan:', value: yok(money(toptan)) },
        { label: 'Perakende:', value: yok(money(perakende)) },
        { label: 'Diğer:', value: yok(money(diger)) },
        { label: 'İade:', value: yok(money(iade)) },
      ],
      footLabel: 'İade oranı:',
      footValue: yok(trPct(c.returnPct)),
    },
    c4: {
      title: 'En büyük cari',
      badge: top && c.netYtd > 0 ? trPct((top.net_ciro / c.netYtd) * 100) : '—',
      initials: (top?.cari ?? '??').slice(0, 2).toUpperCase(),
      name: top?.cari ?? yok('Cari yok'),
      sub: `${c.customers.length} cari listelendi`,
      valueLabel: 'Net ciro:',
      value: yok(`${money(top?.net_ciro ?? 0)} ₺`),
      note: c.customers[1] ? `2. ${c.customers[1].cari.slice(0, 22)}` : '',
      footLabel: 'İlk 5 payı:',
      footValue:
        c.netYtd > 0 ? trPct((c.customers.reduce((a, x) => a + x.net_ciro, 0) / c.netYtd) * 100) : '—',
    },
    c5: {
      title: 'Kanıt & Kaynak',
      badge: durum ? 'Bağlantı' : 'Canlı',
      summary: durum || `${money(c.units?.satir ?? 0)} satır · ${money(c.units?.baslik_sayisi ?? 0)} başlık`,
      rows: [
        { name: 'Fatura', tag: yok(money(c.totals?.toplam_fatura ?? 0)) },
        { name: 'Satır', tag: yok(money(c.units?.satir ?? 0)) },
        { name: 'Cari', tag: yok(num(c.customers.length)) },
      ],
      sql: durum ? undefined : (c.sql ?? undefined),
      latency: durum ? '—' : `${c.year} dönemi`,
      timing: durum ? null : c.db,
    },
    main: {
      badge: 'ZEKİ AI ÖZETİ',
      subject: `Net ciro · ${c.year}`,
      timing: durum ? null : c.db,
      model: durum || `${sonTR} itibarıyla`,
      text: durum
        ? `“${durum}.”`
        : `“${money(c.netYtd)} ₺ net ciro, geçen yılın aynı dönemine göre ${trPct(c.yoyPct)}. İade oranı ${trPct(c.returnPct)}.”`,
      m1: { label: 'Satılan adet:', value: yok(money(c.units?.satilan_adet ?? 0)) },
      m2: { label: 'Fatura:', value: yok(money(c.totals?.toplam_fatura ?? 0)) },
      m3: { label: 'İade faturası:', value: yok(money(c.totals?.iade_fatura ?? 0)) },
      primary: 'Verine sor',
      primaryTo: '/',
      secondary: 'Uyarılar',
      secondaryTo: '/uyarilar',
      note: `${c.observedMonths || 0} ay gerçekleşti`,
    },
    sticker: {
      kicker: 'En çok satan',
      meta: item ? `${money(item.adet)} adet` : '—',
      title: item?.urun ?? yok('VERİ YOK'),
      sub: item?.kod ?? '',
      footL: 'net ciro',
      footR: item ? `${money(item.net_ciro)} ₺` : '—',
      badge: 'İlk sıra ★',
    },
    ghost: {
      title: 'Önceki: İade',
      badge: trPct(c.returnPct),
      text: `“${money(iade)} ₺ iade, brüt satışın ${trPct(c.returnPct)}'i.”`,
      foot: `${money(c.totals?.iade_fatura ?? 0)} iade faturası`,
    },
  };
}
