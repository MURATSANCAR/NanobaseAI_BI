import type { AlertSummary, ScheduleSummary } from '../data';
import { conditionLabel, dateTime, money, num, recurrenceLabel, relative } from '../format';
import type { CfoData } from '../cfo';
import type { ConceptRow, ReviewItem } from '../engine';
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
  { to: '/', label: 'Genel bakış', badge: active === '/' ? 'Aktif' : undefined },
  { to: '/uyarilar', label: 'Uyarılar', badge: active === '/uyarilar' ? 'Aktif' : undefined },
  { to: '/planli-raporlar', label: 'Planlı raporlar', badge: active === '/planli-raporlar' ? 'Aktif' : undefined },
  { to: '/panolar', label: 'Panolar', badge: active === '/panolar' ? 'Aktif' : undefined },
  { to: '/veri-sozlugu', label: 'Veri Sözlüğü', badge: active === '/veri-sozlugu' ? 'Aktif' : undefined },
  { to: '/onaylar', label: 'Onaylar', badge: active === '/onaylar' ? 'Aktif' : undefined },
];

const DOCK = [
  { to: '/', label: 'Genel bakış' },
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

/* --------------------------- Planlı raporlar ---------------------------- */

export function schedulesData(s: ScheduleSummary, loading: boolean, source: string): StitchCanvasData {
  const next = s.next;
  const withRecipient = s.total - s.recipientless.length;
  const sp = spark(s.upcoming.map((_, i) => s.upcoming.length - i));
  return {
    ...base('Planlı raporlar', source, 'ZEKİ’ye sor… örn. geçen haftanın satış özeti', {
      initials: 'TY',
      role: 'Timaş Yayınları · Planlı raporlar',
      at: loading ? 'Yükleniyor' : 'Şimdi',
      text: '“Raporlar zamanında ve doğru kişiye gidiyor mu?”',
    }, 2),
    c1: {
      icon: '📅',
      title: 'Sıradaki gönderim',
      badge: next ? 'Etkin' : 'Boş',
      big: next ? relative(next.run_at) : 'Yok',
      bigSuffix: '',
      subLabel: 'Konu:',
      subValue: next?.subject ?? 'Sohbetten rapor kurun',
      pct: s.total ? (s.active / s.total) * 100 : 0,
      footL: next ? dateTime(next.run_at) : 'Sırada rapor yok',
      footR: next ? recurrenceLabel(next.recurrence) : '',
      rowLabel: 'Alıcı:',
      rowValue: next?.recipient?.trim() || 'yok',
    },
    c2: {
      title: 'Takvim',
      badge: `${num(s.active)} etkin`,
      label: s.upcoming.length ? 'Sıradaki beş gönderim' : 'Sırada rapor yok',
      big: num(s.upcoming.length),
      unit: 'rapor',
      delta: s.total ? `${num(s.total)} kayıt` : '—',
      tick1: s.upcoming[0] ? dateTime(s.upcoming[0].run_at).slice(0, 5) : '—',
      tick2: s.upcoming[1] ? dateTime(s.upcoming[1].run_at).slice(0, 5) : '—',
      tick3: s.upcoming[2] ? dateTime(s.upcoming[2].run_at).slice(0, 5) : '—',
      foot: s.total ? 'Yalnız bekleyen raporlar sıraya girer' : 'Henüz planlı rapor kurulmadı',
      ...sp,
    },
    c3: {
      title: 'Durum dağılımı',
      badge: `${num(s.total)} rapor`,
      center: num(s.total),
      arcs: arcs([s.active, s.paused, s.failed, s.sent]),
      rows: [
        { label: 'Etkin:', value: num(s.active) },
        { label: 'Duraklatıldı:', value: num(s.paused) },
        { label: 'Başarısız:', value: num(s.failed) },
        { label: 'Gönderildi:', value: num(s.sent) },
      ],
      footLabel: 'Uyarı eklenen:',
      footValue: num(s.withAlerts),
    },
    c4: {
      title: 'Alıcısız raporlar',
      badge: s.recipientless.length ? 'Düzeltilmeli' : 'Temiz',
      initials: 'AL',
      name: s.total ? `${num(s.recipientless.length)} rapor alıcısız` : 'Rapor yok',
      sub: s.total ? (s.recipientless[0]?.subject ?? 'hepsinde alıcı var') : 'kayıt bekleniyor',
      valueLabel: 'Alıcısı tanımlı:',
      value: `${num(withRecipient)} / ${num(s.total)}`,
      note: 'Bu raporlar çalışır ama kimseye ulaşmaz',
      footLabel: 'Yorum metni eklenen:',
      footValue: num(s.withNarrative),
    },
    c5: {
      title: 'Kanıt & Kaynak',
      badge: 'Canlı veri',
      summary: `${num(s.total)} kayıt · ${num(s.active)} etkin`,
      rows: [
        { name: 'Etkin', tag: num(s.active) },
        { name: 'Duraklatılmış', tag: num(s.paused) },
        { name: 'Başarısız', tag: num(s.failed) },
      ],
      latency: s.lastFailure ? dateTime(s.lastFailure.sent_at ?? s.lastFailure.run_at) : 'hata yok',
    },
    main: {
      badge: 'ZEKİ AI ÖZETİ',
      subject: `Planlı raporlar · ${num(s.total)} kayıt`,
      model: s.recipientless.length ? 'Dikkat gerektiren durum var' : 'Kuyruk sağlıklı',
      text: !s.total && !loading
        ? '“Planlı rapor gönderimi e-posta ile çalışır; gönderici hesap tanımlanınca burada rapor kurulabilecek. O zamana kadar eşik takibi için Uyarılar, kalıcı grafikler için Panolar hazır.”'
        : loading
        ? '“Rapor kuyruğu okunuyor…”'
        : s.total === 0
          ? '“Henüz planlı rapor yok. Sohbete ‘her pazartesi 09:00 satış özeti gönder’ yazarak ilkini kurabilirsiniz.”'
          : `“${num(s.active)} rapor etkin${next ? `, en yakını ${relative(next.run_at)}` : ''}.${
              s.recipientless.length ? ` ${num(s.recipientless.length)} raporun alıcısı boş.` : ''
            }${s.failed ? ` ${num(s.failed)} gönderim başarısız.` : ''}”`,
      m1: { label: 'Etkin:', value: num(s.active) },
      m2: { label: 'Duraklatılmış:', value: num(s.paused) },
      m3: { label: 'Başarısız:', value: num(s.failed) },
      primary: 'Uyarılara git',
      primaryTo: '/uyarilar',
      secondary: 'Panolara git',
      secondaryTo: '/panolar',
      note: s.lastFailure?.error ? `Son hata: ${s.lastFailure.error.slice(0, 60)}` : 'Kayıtlarda başarısız gönderim yok',
    },
    sticker: {
      kicker: 'Sıradaki',
      meta: next ? recurrenceLabel(next.recurrence) : '—',
      title: next?.subject ?? 'PLANLI RAPOR YOK',
      sub: next?.recipient?.trim() || '',
      footL: next ? dateTime(next.run_at).slice(0, 10) : '—',
      footR: next?.local_time ?? '',
      badge: s.recipientless.length ? 'Alıcı eksik' : 'Hazır ★',
    },
    ghost: {
      title: 'Önceki: Gönderilenler',
      badge: num(s.sent),
      text: '“Kuyruktan çıkmış gönderimler burada birikiyor.”',
      foot: `${num(s.total)} kayıt`,
    },
  };
}

/* -------------------------------- Panolar -------------------------------- */

type Board = { id: number; title?: string; chart_count?: number; changed_on?: string; changed_on_delta?: string };
type EngineStatus = { enabled?: boolean; url?: string; health?: { ok?: boolean; message?: string; dashboard_count?: number } };

export function boardsData(status: EngineStatus | undefined, boards: Board[], loading: boolean, source: string): StitchCanvasData {
  const on = Boolean(status?.enabled) && status?.health?.ok !== false;
  const charts = boards.reduce((a, b) => a + (b.chart_count ?? 0), 0);
  const empty = boards.filter((b) => !(b.chart_count ?? 0));
  const byCharts = [...boards].sort((a, b) => (b.chart_count ?? 0) - (a.chart_count ?? 0));
  const newest = [...boards].sort((a, b) => ((a.changed_on ?? '') < (b.changed_on ?? '') ? 1 : -1))[0];
  const top = byCharts[0];
  return {
    ...base('Panolar', source, 'ZEKİ’ye sor… örn. bayi bazında satış panosu kur', {
      initials: 'TY',
      role: 'Timaş Yayınları · Panolar',
      at: loading ? 'Yükleniyor' : 'Şimdi',
      text: '“Panolarımız güncel mi, boş kalan var mı?”',
    }, 1),
    c1: {
      icon: '📊',
      title: 'Analitik motoru',
      badge: on ? 'Bağlı' : 'Kapalı',
      big: on ? 'Açık' : 'Kapalı',
      bigSuffix: '',
      subLabel: 'Durum:',
      subValue: status?.health?.message ?? (on ? 'sağlıklı' : 'yapılandırılmadı'),
      pct: on ? 100 : 0,
      footL: `Motorun saydığı pano: ${num(status?.health?.dashboard_count ?? null)}`,
      footR: `Listelenen: ${num(boards.length)}`,
      rowLabel: 'Toplam grafik:',
      rowValue: num(charts),
    },
    c2: {
      title: 'Panolar',
      badge: `${num(boards.length)} pano`,
      label: newest ? (newest.title ?? `Pano ${newest.id}`) : 'Kayıtlı pano yok',
      big: num(charts),
      unit: 'grafik',
      delta: newest?.changed_on_delta ?? '—',
      tick1: byCharts[0] ? `${num(byCharts[0].chart_count ?? 0)}` : '—',
      tick2: byCharts[1] ? `${num(byCharts[1].chart_count ?? 0)}` : '—',
      tick3: byCharts[2] ? `${num(byCharts[2].chart_count ?? 0)}` : '—',
      foot: 'Grafik sayısına göre ilk üç pano',
      ...spark(byCharts.slice(0, 5).map((b) => b.chart_count ?? 0)),
    },
    c3: {
      title: 'Grafik dağılımı',
      badge: `${num(charts)} grafik`,
      center: num(charts),
      arcs: arcs([
        byCharts[0]?.chart_count ?? 0,
        byCharts[1]?.chart_count ?? 0,
        byCharts[2]?.chart_count ?? 0,
        byCharts.slice(3).reduce((a, b) => a + (b.chart_count ?? 0), 0),
      ]),
      rows: [
        { label: (byCharts[0]?.title ?? 'Pano 1').slice(0, 14) + ':', value: num(byCharts[0]?.chart_count ?? 0) },
        { label: (byCharts[1]?.title ?? 'Pano 2').slice(0, 14) + ':', value: num(byCharts[1]?.chart_count ?? 0) },
        { label: (byCharts[2]?.title ?? 'Pano 3').slice(0, 14) + ':', value: num(byCharts[2]?.chart_count ?? 0) },
        { label: 'Diğer:', value: num(byCharts.slice(3).reduce((a, b) => a + (b.chart_count ?? 0), 0)) },
      ],
      footLabel: 'En dolu pano:',
      footValue: top?.title ?? '—',
    },
    c4: {
      title: 'Boş panolar',
      badge: empty.length ? 'Düzeltilmeli' : 'Temiz',
      initials: 'BP',
      name: `${num(empty.length)} pano boş`,
      sub: empty[0]?.title ?? 'her panoda grafik var',
      valueLabel: 'Dolu pano:',
      value: `${num(boards.length - empty.length)} / ${num(boards.length)}`,
      note: 'Boş pano açılır ama hiçbir şey göstermez',
      footLabel: 'Son güncelleme:',
      footValue: newest?.changed_on_delta ?? dateTime(newest?.changed_on),
    },
    c5: {
      title: 'Kanıt & Kaynak',
      badge: 'Canlı veri',
      summary: `${num(boards.length)} pano · ${num(charts)} grafik · analytics API`,
      rows: [
        { name: 'analytics/status', tag: on ? 'Açık' : 'Kapalı' },
        { name: 'analytics/dashboards', tag: 'Liste' },
        { name: 'chart_count', tag: 'Sayaç' },
      ],
      latency: status?.url ?? 'uç nokta yok',
    },
    main: {
      badge: 'ZEKİ AI ÖZETİ',
      subject: `Panolar · ${num(boards.length)} pano`,
      model: on ? 'Analitik motoru bağlı' : 'Analitik motoru kapalı',
      text: loading
        ? '“Panolar okunuyor…”'
        : !on
          ? '“Analitik motoru kapalı. Açıldığında her veri kaynağı için bir pano kurulur ve grafikler buraya düşer.”'
          : boards.length === 0
            ? '“Motor açık ama kayıtlı pano yok. Sohbetten bir sonucu panoya iliştirerek ilkini kurabilirsiniz.”'
            : `“${num(boards.length)} pano, toplam ${num(charts)} grafik.${empty.length ? ` ${num(empty.length)} pano boş.` : ''}”`,
      m1: { label: 'Pano:', value: num(boards.length) },
      m2: { label: 'Grafik:', value: num(charts) },
      m3: { label: 'Boş pano:', value: num(empty.length) },
      primary: 'Panoyu aç',
      primaryTo: '/panolar',
      secondary: 'Sohbetten pano kur',
      secondaryTo: '/',
      note: on ? 'Panolar analytics motorundan gelir' : 'analytics_disabled',
    },
    sticker: {
      kicker: 'En dolu pano',
      meta: top ? `${num(top.chart_count ?? 0)} grafik` : '—',
      title: top?.title ?? 'PANO YOK',
      sub: top ? `#${top.id}` : '',
      footL: 'grafik',
      footR: num(top?.chart_count ?? 0),
      badge: empty.length ? 'Boş pano var' : 'Dolu ★',
    },
    ghost: {
      title: 'Önceki: Grafik toplamı',
      badge: num(charts),
      text: '“Tüm panolardaki grafiklerin toplamı.”',
      foot: `${num(boards.length)} pano · analytics API`,
    },
  };
}

/* ------------------------------ Genel bakış ------------------------------ */

export function overviewData(
  sched: ScheduleSummary,
  alerts: AlertSummary,
  status: EngineStatus | undefined,
  boardCount: number,
  loading: boolean,
  source: string,
): StitchCanvasData {
  const on = Boolean(status?.enabled) && status?.health?.ok !== false;
  const attention = sched.recipientless.length + alerts.triggered.length + alerts.neverChecked.length + sched.failed;
  return {
    ...base('Genel bakış', source, 'ZEKİ’ye sor… örn. bu ay satışlar geçen yıla göre nasıl?', {
      initials: 'TY',
      role: 'Timaş Yayınları · Genel bakış',
      at: loading ? 'Yükleniyor' : 'Şimdi',
      text: '“Bugün neye bakmam gerekiyor?”',
    }),
    c1: {
      icon: '📅',
      title: 'Planlı raporlar',
      badge: sched.recipientless.length ? 'Alıcı eksik' : 'Düzenli',
      big: num(sched.active),
      bigSuffix: 'etkin',
      subLabel: 'Sıradaki:',
      subValue: sched.next ? relative(sched.next.run_at) : 'yok',
      pct: sched.total ? ((sched.total - sched.recipientless.length) / sched.total) * 100 : 0,
      footL: `Toplam: ${num(sched.total)}`,
      footR: `Başarısız: ${num(sched.failed)}`,
      rowLabel: 'Alıcısız rapor:',
      rowValue: num(sched.recipientless.length),
    },
    c2: {
      title: 'Uyarılar',
      badge: alerts.triggered.length ? 'Tetikte' : 'Sakin',
      label: 'Aktif kural',
      big: num(alerts.active),
      unit: 'kural',
      delta: alerts.triggered.length ? `${num(alerts.triggered.length)} tetikte` : 'sakin',
      tick1: `${num(alerts.total)} toplam`,
      tick2: `${num(alerts.paused)} duraklatıldı`,
      tick3: `${num(alerts.neverChecked.length)} bakılmamış`,
      foot: alerts.lastCheckedAt ? `Son kontrol ${relative(alerts.lastCheckedAt)}` : 'Henüz kontrol edilmedi',
      ...spark(alerts.proximity.map((p) => p.pct)),
    },
    c3: {
      title: 'Dikkat isteyen',
      badge: `${num(attention)} madde`,
      center: num(attention),
      arcs: arcs([sched.recipientless.length, alerts.triggered.length, alerts.neverChecked.length, sched.failed]),
      rows: [
        { label: 'Alıcısız rapor:', value: num(sched.recipientless.length) },
        { label: 'Tetikte uyarı:', value: num(alerts.triggered.length) },
        { label: 'Bakılmamış:', value: num(alerts.neverChecked.length) },
        { label: 'Başarısız:', value: num(sched.failed) },
      ],
      footLabel: 'Toplam kural:',
      footValue: num(alerts.total),
    },
    c4: {
      title: 'Panolar',
      badge: on ? 'Motor bağlı' : 'Motor kapalı',
      initials: 'PN',
      name: `${num(boardCount)} pano`,
      sub: status?.health?.message ?? (on ? 'analytics sağlıklı' : 'analytics kapalı'),
      valueLabel: 'Motorun saydığı:',
      value: num(status?.health?.dashboard_count ?? null),
      note: on ? 'Panolar analytics motorundan gelir' : 'Motor açılınca panolar listelenir',
      footLabel: 'Veri kaynağı:',
      footValue: source,
    },
    c5: {
      title: 'Kanıt & Kaynak',
      badge: 'Canlı veri',
      summary: 'Üç modül · anlık okuma',
      rows: [
        { name: 'Planlı rapor', tag: num(sched.total) },
        { name: 'Uyarı kuralı', tag: num(alerts.total) },
        { name: 'Pano', tag: num(boardCount) },
      ],
      latency: 'sayfa açılışında okundu',
    },
    main: {
      badge: 'ZEKİ AI ÖZETİ',
      subject: 'Günün durumu',
      model: attention ? 'Dikkat gerektiren durum var' : 'Bekleyen sorun yok',
      text: loading
        ? '“Modüller okunuyor…”'
        : attention === 0
          ? '“Bekleyen bir sorun görünmüyor: raporların alıcısı tam, uyarılar sakin.”'
          : `“${num(attention)} madde dikkat istiyor.${sched.recipientless.length ? ` ${num(sched.recipientless.length)} raporun alıcısı boş.` : ''}${
              alerts.triggered.length ? ` ${num(alerts.triggered.length)} uyarı eşiği aşmış.` : ''
            }${alerts.neverChecked.length ? ` ${num(alerts.neverChecked.length)} kural hiç çalıştırılmamış.` : ''}”`,
      m1: { label: 'Etkin rapor:', value: num(sched.active) },
      m2: { label: 'Aktif kural:', value: num(alerts.active) },
      m3: { label: 'Pano:', value: num(boardCount) },
      primary: 'Uyarılara git',
      primaryTo: '/uyarilar',
      secondary: 'Planlı raporlara git',
      secondaryTo: '/planli-raporlar',
      note: alerts.lastCheckedAt ? `Son kontrol ${relative(alerts.lastCheckedAt)}` : 'Uyarılar henüz kontrol edilmedi',
    },
    sticker: {
      kicker: 'Dikkat',
      meta: `${num(attention)} madde`,
      title: attention ? 'AKSİYON BEKLİYOR' : 'HER ŞEY YOLUNDA',
      sub: attention ? 'uyarılar ve raporlar' : 'bekleyen iş yok',
      footL: 'modül',
      footR: '3',
      badge: attention ? 'İncele ★' : 'Temiz ★',
    },
    ghost: {
      title: 'Önceki: Modül durumu',
      badge: '3',
      text: '“Planlı raporlar, uyarılar ve panolar tek ekranda.”',
      foot: 'portal API · canlı',
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
  const durum = c.authRequired ? 'Oturum gerekli' : c.failed ? 'Motor yanıt vermedi' : !c.ready ? 'Yükleniyor' : '';
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
      latency: durum ? '—' : `${c.year} dönemi`,
    },
    main: {
      badge: 'ZEKİ AI ÖZETİ',
      subject: `Net ciro · ${c.year}`,
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


/* ----------------------- Veri Sözlüğü ve Onaylar ------------------------ */


type Loadable<T> = { data: T | null; loading: boolean; authRequired: boolean };

/** Veri Sözlüğü: motorun sertifikalı kavramları. Eski sistemdeki Katalog
 *  Gezgini'nin yerini tutar. */
export function glossaryData(q: Loadable<{ items: ConceptRow[] }>, source: string): StitchCanvasData {
  const durum = q.authRequired ? 'Oturum gerekli' : q.loading ? 'Yükleniyor' : !q.data ? 'Motor yanıt vermedi' : '';
  const items = (q.data?.items ?? []).map((r) => r.concept);
  const byType = (t: string) => items.filter((c) => c.semantic_type === t).length;
  const metrics = items.filter((c) => c.semantic_type === 'METRIC');
  const top = metrics.slice(0, 4);
  const yok = (v: string) => (durum ? '—' : v);

  return {
    ...base('Veri Sözlüğü', source, 'ZEKİ’ye sor… örn. net ciro nasıl hesaplanıyor?', {
      initials: 'TY',
      role: 'Timaş Yayınları · Veri Sözlüğü',
      at: durum || 'Şimdi',
      text: '“Hangi terim neye karşılık geliyor?”',
    }, 0),
    c1: {
      icon: '📖',
      title: 'Sertifikalı kavram',
      badge: durum ? 'Bağlantı' : 'Onaylı',
      big: yok(num(items.length)),
      bigSuffix: 'terim',
      subLabel: 'Metrik:',
      subValue: yok(num(byType('METRIC'))),
      pct: items.length ? (byType('METRIC') / items.length) * 100 : 0,
      footL: `Kolon: ${yok(num(byType('COLUMN')))}`,
      footR: `İlişki: ${yok(num(byType('RELATIONSHIP')))}`,
      rowLabel: 'Değer eşlemesi:',
      rowValue: yok(num(byType('DIMENSION_VALUE'))),
    },
    c2: {
      title: 'Metrikler',
      badge: `${num(metrics.length)} metrik`,
      label: top[0]?.term ?? yok('Metrik yok'),
      big: yok(num(metrics.length)),
      unit: 'tanım',
      delta: top[0]?.confidence != null ? `%${Math.round(top[0].confidence * 100)} güven` : '—',
      tick1: top[1]?.term ?? '—',
      tick2: top[2]?.term ?? '—',
      tick3: top[3]?.term ?? '—',
      foot: 'İş tarafının onayladığı hesap tanımları',
      ...spark(metrics.slice(0, 6).map((m) => (m.confidence ?? 0) * 100)),
    },
    c3: {
      title: 'Tür dağılımı',
      badge: `${num(items.length)} kavram`,
      center: yok(num(items.length)),
      arcs: arcs([byType('DIMENSION_VALUE'), byType('COLUMN'), byType('METRIC'), byType('RELATIONSHIP')]),
      rows: [
        { label: 'Değer:', value: yok(num(byType('DIMENSION_VALUE'))) },
        { label: 'Kolon:', value: yok(num(byType('COLUMN'))) },
        { label: 'Metrik:', value: yok(num(byType('METRIC'))) },
        { label: 'İlişki:', value: yok(num(byType('RELATIONSHIP'))) },
      ],
      footLabel: 'Varsayılan filtre:',
      footValue: yok(num(byType('DEFAULT_FILTER'))),
    },
    c4: {
      title: 'Örnek tanım',
      badge: 'Sertifikalı',
      initials: 'NC',
      name: metrics[0]?.term ?? yok('Tanım yok'),
      sub: metrics[0]?.domain ?? '',
      valueLabel: 'Güven:',
      value: metrics[0]?.confidence != null ? `%${Math.round(metrics[0].confidence * 100)}` : '—',
      note: 'Bu tanım sorularda doğrudan kullanılır',
      footLabel: 'Eş anlamlı:',
      footValue: yok(num(metrics[0]?.synonyms?.length ?? 0)),
    },
    c5: {
      title: 'Kanıt & Kaynak',
      badge: durum ? 'Bağlantı' : 'Canlı',
      summary: durum || `${num(items.length)} kavram`,
      rows: [
        { name: 'Sertifikalı', tag: num(items.length) },
        { name: 'Metrik', tag: num(byType('METRIC')) },
        { name: 'Kolon', tag: num(byType('COLUMN')) },
      ],
      latency: durum ? '—' : 'canlı',
    },
    main: {
      badge: 'ZEKİ AI ÖZETİ',
      subject: 'Veri Sözlüğü',
      model: durum || 'Sertifikalı katalog',
      text: durum
        ? `“${durum}.”`
        : `“${num(items.length)} kavram sertifikalı: ${num(byType('METRIC'))} metrik, ${num(byType('COLUMN'))} kolon, ${num(byType('RELATIONSHIP'))} ilişki.”`,
      m1: { label: 'Metrik:', value: yok(num(byType('METRIC'))) },
      m2: { label: 'Kolon:', value: yok(num(byType('COLUMN'))) },
      m3: { label: 'İlişki:', value: yok(num(byType('RELATIONSHIP'))) },
      primary: 'Onay kuyruğu',
      primaryTo: '/onaylar',
      secondary: 'Verine sor',
      secondaryTo: '/',
      note: 'Sertifikalı tanımlar sorularda kullanılır',
    },
    sticker: {
      kicker: 'Sözlük',
      meta: `${num(items.length)} terim`,
      title: metrics[0]?.term?.toLocaleUpperCase('tr') ?? 'SÖZLÜK',
      sub: 'sertifikalı',
      footL: 'metrik',
      footR: num(byType('METRIC')),
      badge: 'Onaylı ★',
    },
    ghost: { title: '', badge: '', text: '', foot: '' },
  };
}

/** Onaylar: insana sorulmayı bekleyen terimler. Eski sistemdeki Terim
 *  İnceleme ekranının karşılığı. */
export function approvalsData(
  q: Loadable<{ waiting: number; used: number; total: number; items: ReviewItem[] }>,
  source: string,
): StitchCanvasData {
  const durum = q.authRequired ? 'Oturum gerekli' : q.loading ? 'Yükleniyor' : !q.data ? 'Motor yanıt vermedi' : '';
  const d0 = q.data;
  const items = d0?.items ?? [];
  const yok = (v: string) => (durum ? '—' : v);
  const byType = (t: string) => items.filter((i) => i.type === t).length;
  const first = items[0];

  return {
    ...base('Onaylar', source, 'ZEKİ’ye sor… örn. bekleyen terimleri özetle', {
      initials: 'TY',
      role: 'Timaş Yayınları · Onaylar',
      at: durum || 'Şimdi',
      text: '“Hangi terim onay bekliyor?”',
    }, 0),
    c1: {
      icon: '✅',
      title: 'Bekleyen',
      badge: (d0?.waiting ?? 0) > 0 ? 'İnceleme' : 'Temiz',
      big: yok(num(d0?.waiting ?? 0)),
      bigSuffix: 'terim',
      subLabel: 'Toplam aday:',
      subValue: yok(num(d0?.total ?? 0)),
      pct: d0?.total ? ((d0.waiting ?? 0) / d0.total) * 100 : 0,
      footL: `Kullanılan: ${yok(num(d0?.used ?? 0))}`,
      footR: `Toplam: ${yok(num(d0?.total ?? 0))}`,
      rowLabel: 'Listelenen:',
      rowValue: yok(num(items.length)),
    },
    c2: {
      title: 'Kuyruktakiler',
      badge: `${num(items.length)} kayıt`,
      label: first?.term ?? yok('Kuyruk boş'),
      big: yok(num(items.length)),
      unit: 'terim',
      delta: first?.confidence != null ? `%${Math.round(first.confidence * 100)} güven` : '—',
      tick1: items[1]?.term ?? '—',
      tick2: items[2]?.term ?? '—',
      tick3: items[3]?.term ?? '—',
      foot: 'Sırayla insana sorulacak adaylar',
      ...spark(items.slice(0, 6).map((i) => (i.confidence ?? 0) * 100)),
    },
    c3: {
      title: 'Tür dağılımı',
      badge: `${num(items.length)} kayıt`,
      center: yok(num(items.length)),
      arcs: arcs([byType('COLUMN'), byType('METRIC'), byType('DIMENSION_VALUE'), byType('RELATIONSHIP')]),
      rows: [
        { label: 'Kolon:', value: yok(num(byType('COLUMN'))) },
        { label: 'Metrik:', value: yok(num(byType('METRIC'))) },
        { label: 'Değer:', value: yok(num(byType('DIMENSION_VALUE'))) },
        { label: 'İlişki:', value: yok(num(byType('RELATIONSHIP'))) },
      ],
      footLabel: 'Sertifikaya giden:',
      footValue: yok(num(d0?.used ?? 0)),
    },
    c4: {
      title: 'Sıradaki terim',
      badge: 'Onay bekliyor',
      initials: (first?.term ?? '??').slice(0, 2).toLocaleUpperCase('tr'),
      name: first?.term ?? yok('Kuyruk boş'),
      sub: first?.mapping?.entity ?? '',
      valueLabel: 'Eşleşme:',
      value: first?.mapping?.column ?? '—',
      note: first?.mapping?.table_pattern ?? '',
      footLabel: 'Güven:',
      footValue: first?.confidence != null ? `%${Math.round(first.confidence * 100)}` : '—',
    },
    c5: {
      title: 'Kanıt & Kaynak',
      badge: durum ? 'Bağlantı' : 'Canlı',
      summary: durum || `${num(d0?.waiting ?? 0)} bekleyen · ${num(d0?.total ?? 0)} aday`,
      rows: [
        { name: 'Bekleyen', tag: num(d0?.waiting ?? 0) },
        { name: 'Kullanılan', tag: num(d0?.used ?? 0) },
        { name: 'Toplam aday', tag: num(d0?.total ?? 0) },
      ],
      latency: durum ? '—' : 'canlı',
    },
    main: {
      badge: 'ZEKİ AI ÖZETİ',
      subject: 'Onay kuyruğu',
      model: durum || `${num(d0?.total ?? 0)} aday`,
      text: durum
        ? `“${durum}.”`
        : `“${num(d0?.waiting ?? 0)} terim onay bekliyor. Onaylanan tanım sonraki sorularda doğrudan kullanılır.”`,
      m1: { label: 'Bekleyen:', value: yok(num(d0?.waiting ?? 0)) },
      m2: { label: 'Kullanılan:', value: yok(num(d0?.used ?? 0)) },
      m3: { label: 'Toplam:', value: yok(num(d0?.total ?? 0)) },
      primary: 'Veri Sözlüğü',
      primaryTo: '/veri-sozlugu',
      secondary: 'Verine sor',
      secondaryTo: '/',
      note: 'Onay kalıcıdır; gece taraması düşüremez',
    },
    sticker: {
      kicker: 'Onay bekliyor',
      meta: num(d0?.waiting ?? 0),
      title: first?.term?.toLocaleUpperCase('tr') ?? 'KUYRUK BOŞ',
      sub: first?.mapping?.entity ?? '',
      footL: 'aday',
      footR: num(d0?.total ?? 0),
      badge: 'İncele ★',
    },
    ghost: { title: '', badge: '', text: '', foot: '' },
  };
}
