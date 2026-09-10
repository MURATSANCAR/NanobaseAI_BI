import type { AlertSummary, ScheduleSummary } from '../data';
import { conditionLabel, dateTime, num, recurrenceLabel, relative } from '../format';
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
const rail = (certified?: number): StitchRailItem[] => [
  { to: '/bi/chat', label: 'Sohbet', badge: 'Aktif' },
  { to: '/bi', label: 'Dashboard' },
  { to: '/bi/semantic-catalog', label: 'Anlamsal Katalog', badge: certified ? `${certified} sertifikalı` : 'katalog' },
  { to: '/bi/budget', label: 'Bütçe yönetimi' },
  { to: '/bi/templates', label: 'Şablonlar' },
  { to: '/bi/queries', label: 'Kayıtlı sorgular' },
  { to: '/bi/glossary', label: 'Sözlük' },
  { to: '/bi/sources', label: 'Veri kaynakları' },
  { to: '/bi/schema', label: 'Şema / ilişkiler' },
  { to: '/bi/alerts', label: 'Uyarılar' },
];

const base = (crumb: string, source: string, ask: string, q: StitchCanvasData['q']) => ({
  tenant: 'Timaş Yayınları',
  section: 'Yapay Zeka Raporları',
  crumb,
  source,
  presence: 'canlı veri',
  zoom: '%100',
  minimap: '1440 × 1000',
  askPlaceholder: ask,
  rail: rail(),
  dock: ['Genel bakış', 'Panolar', 'Planlı raporlar', 'Uyarılar'] as [string, string, string, string],
  q,
});

/* ------------------------------- Uyarılar ------------------------------- */

export function alertsData(s: AlertSummary, loading: boolean, source: string): StitchCanvasData {
  const hot = s.proximity[0];
  const latest = [...s.triggered].sort((a, b) => ((a.last_triggered_at ?? '') < (b.last_triggered_at ?? '') ? 1 : -1))[0];
  const withMail = s.total - s.browserOnly.length;
  const sp = spark(s.proximity.map((p) => p.pct));
  return {
    ...base('Uyarılar', source, 'ZEKİ’ye sor… örn. stok 500 adedin altına inerse haber ver', {
      initials: 'TY',
      role: 'Timaş Yayınları · Uyarılar',
      at: loading ? 'Yükleniyor' : 'Şimdi',
      text: '“Hangi eşik patlamak üzere?”',
    }),
    c1: {
      icon: '🔔',
      title: 'Tetiklenenler',
      badge: s.triggered.length ? 'Kritik' : 'Sakin',
      big: num(s.triggered.length),
      bigSuffix: 'kural',
      subLabel: 'Aktif kural:',
      subValue: num(s.active),
      pct: s.active ? (s.triggered.length / s.active) * 100 : 0,
      footL: latest ? `Son tetikleme: ${relative(latest.last_triggered_at)}` : 'Tetikleme yok',
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
      arcs: arcs([Math.max(0, s.active - s.triggered.length), s.triggered.length, s.paused, 0]),
      rows: [
        { label: 'Sakin:', value: num(Math.max(0, s.active - s.triggered.length)) },
        { label: 'Tetikte:', value: num(s.triggered.length) },
        { label: 'Duraklatıldı:', value: num(s.paused) },
        { label: 'Diğer:', value: '0' },
      ],
      footLabel: 'Son kontrol:',
      footValue: s.lastCheckedAt ? relative(s.lastCheckedAt) : 'hiç',
    },
    c4: {
      title: 'Bildirim kanalı',
      badge: s.browserOnly.length ? 'Eksik kanal' : 'Tam',
      initials: 'EP',
      name: `${num(withMail)} kuralda e-posta`,
      sub: 'channels[type=email]',
      valueLabel: 'Yalnız tarayıcı:',
      value: num(s.browserOnly.length),
      note: 'Tarayıcı kapalıyken bu kurallar duyulmaz',
      footLabel: 'Hiç kontrol edilmemiş:',
      footValue: num(s.neverChecked.length),
    },
    c5: {
      title: 'Kanıt & Kaynak',
      badge: 'Canlı veri',
      summary: `${num(s.total)} kural · ${num(s.proximity.length)} ölçüm · portal API`,
      rows: [
        { name: 'bi/alerts', tag: 'Portal API' },
        { name: 'alerts.check-now', tag: 'Motor' },
        { name: 'last_checked_at', tag: 'Kayıt' },
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
          ? '“Henüz uyarı kuralı yok. Sohbete ‘stok 500 adedin altına inerse haber ver’ yazarak ilkini kurabilirsiniz.”'
          : `“${num(s.active)} kural aktif${s.triggered.length ? `, ${num(s.triggered.length)} tanesi tetikte` : ''}.${
              hot && hot.distance != null
                ? ` Eşiğe en yakın kural “${hot.rule.title}”: son değer ${num(hot.rule.last_value ?? null)}, eşik ${num(hot.rule.threshold)}.`
                : ''
            }${s.neverChecked.length ? ` ${num(s.neverChecked.length)} kural hiç çalıştırılmamış.` : ''}”`,
      m1: { label: 'Aktif:', value: num(s.active) },
      m2: { label: 'Duraklatılmış:', value: num(s.paused) },
      m3: { label: 'Yalnız tarayıcı:', value: num(s.browserOnly.length) },
      primary: 'Şimdi kontrol et',
      secondary: 'Kuralları yönet',
      note: s.neverChecked.length ? `${num(s.neverChecked.length)} kural hiç çalıştırılmamış` : 'Tüm kurallar denenmiş',
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
      badge: num(s.browserOnly.length),
      text: '“E-posta alıcısı olmayan kurallar yalnız tarayıcı açıkken duyulur.”',
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
    ...base('Planlı raporlar', source, 'ZEKİ’ye sor… örn. her pazartesi 09:00 satış özeti gönder', {
      initials: 'TY',
      role: 'Timaş Yayınları · Planlı raporlar',
      at: loading ? 'Yükleniyor' : 'Şimdi',
      text: '“Raporlar zamanında ve doğru kişiye gidiyor mu?”',
    }),
    c1: {
      icon: '📅',
      title: 'Sıradaki gönderim',
      badge: next ? 'Etkin' : 'Boş',
      big: next ? relative(next.run_at) : '—',
      bigSuffix: '',
      subLabel: 'Konu:',
      subValue: next?.subject ?? 'planlı rapor yok',
      pct: s.total ? (s.active / s.total) * 100 : 0,
      footL: next ? dateTime(next.run_at) : 'Sırada rapor yok',
      footR: next ? recurrenceLabel(next.recurrence) : '',
      rowLabel: 'Alıcı:',
      rowValue: next?.recipient?.trim() || 'yok',
    },
    c2: {
      title: 'Takvim',
      badge: `${num(s.active)} etkin`,
      label: 'Sıradaki beş gönderim',
      big: num(s.upcoming.length),
      unit: 'rapor',
      delta: s.total ? `${num(s.total)} kayıt` : '—',
      tick1: s.upcoming[0] ? dateTime(s.upcoming[0].run_at).slice(0, 5) : '—',
      tick2: s.upcoming[1] ? dateTime(s.upcoming[1].run_at).slice(0, 5) : '—',
      tick3: s.upcoming[2] ? dateTime(s.upcoming[2].run_at).slice(0, 5) : '—',
      foot: 'Yalnız bekleyen (pending) raporlar sıraya girer',
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
      name: `${num(s.recipientless.length)} rapor alıcısız`,
      sub: s.recipientless[0]?.subject ?? 'hepsinde alıcı var',
      valueLabel: 'Alıcısı tanımlı:',
      value: `${num(withRecipient)} / ${num(s.total)}`,
      note: 'Bu raporlar çalışır ama kimseye ulaşmaz',
      footLabel: 'Yorum metni eklenen:',
      footValue: num(s.withNarrative),
    },
    c5: {
      title: 'Kanıt & Kaynak',
      badge: 'Canlı veri',
      summary: `${num(s.total)} kayıt · portal API · bi/schedules`,
      rows: [
        { name: 'bi/schedules', tag: 'Portal API' },
        { name: 'run_at', tag: 'Sıra' },
        { name: 'error', tag: 'Hata' },
      ],
      latency: s.lastFailure ? dateTime(s.lastFailure.sent_at ?? s.lastFailure.run_at) : 'hata yok',
    },
    main: {
      badge: 'ZEKİ AI ÖZETİ',
      subject: `Planlı raporlar · ${num(s.total)} kayıt`,
      model: s.recipientless.length ? 'Dikkat gerektiren durum var' : 'Kuyruk sağlıklı',
      text: loading
        ? '“Rapor kuyruğu okunuyor…”'
        : s.total === 0
          ? '“Henüz planlı rapor yok. Sohbete ‘her pazartesi 09:00 satış özeti gönder’ yazarak ilkini kurabilirsiniz.”'
          : `“${num(s.active)} rapor etkin${next ? `, en yakını ${relative(next.run_at)}` : ''}.${
              s.recipientless.length ? ` ${num(s.recipientless.length)} raporun alıcısı boş.` : ''
            }${s.failed ? ` ${num(s.failed)} gönderim başarısız.` : ''}”`,
      m1: { label: 'Etkin:', value: num(s.active) },
      m2: { label: 'Duraklatılmış:', value: num(s.paused) },
      m3: { label: 'Başarısız:', value: num(s.failed) },
      primary: 'Raporları yönet',
      secondary: 'Sohbetten yeni rapor kur',
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
      foot: `${num(s.total)} kayıt · bi/schedules`,
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
    }),
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
      secondary: 'Sohbetten pano kur',
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
      summary: 'Üç modül · portal API · anlık okuma',
      rows: [
        { name: 'bi/schedules', tag: 'Rapor' },
        { name: 'bi/alerts', tag: 'Uyarı' },
        { name: 'bi/analytics', tag: 'Pano' },
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
      secondary: 'Planlı raporlara git',
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
