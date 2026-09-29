/** Dosya yükleme alanının (FileDrop) saf kuralları: tür/boyut denetimi, kabul edilen türlerin okunur adı,
 *  dosya adından başlık ve yükleme işlemlerinin yetki adları. React'e bağlı değil; vitest doğrudan sınar. */

export type FileLike = { name: string; size: number; type?: string };

export const MB = 1024 * 1024;

/** `accept` özniteliğini parçalar: ".docx,.pdf, image/*" → ['.docx', '.pdf', 'image/*'] (küçük harf). */
export function acceptTokens(accept: string | undefined): string[] {
  return (accept ?? '')
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean);
}

const MIME_NAMES: Record<string, string> = {
  'image/*': 'görsel',
  'audio/*': 'ses',
  'video/*': 'video',
  'text/*': 'metin',
  'application/pdf': 'PDF',
  'text/csv': 'CSV',
  'text/plain': 'TXT',
  'image/jpeg': 'JPG',
  'image/png': 'PNG',
  'image/webp': 'WEBP',
  'image/heic': 'HEIC',
  'image/heif': 'HEIF',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
};

/** Kabul edilen türlerin ekranda yazılan adı: ".docx,.pdf,image/*" → "DOCX, PDF, görsel". Boşsa "her tür dosya". */
export function acceptLabel(accept: string | undefined): string {
  const seen: string[] = [];
  for (const t of acceptTokens(accept)) {
    const name = t.startsWith('.') ? t.slice(1).toUpperCase() : MIME_NAMES[t] ?? t;
    if (!seen.includes(name)) seen.push(name);
  }
  return seen.length ? seen.join(', ') : 'her tür dosya';
}

/** Bayt → "850 KB" / "12,4 MB" (Türkçe ondalık). */
export function fmtSize(bytes: number): string {
  if (bytes >= MB) {
    const v = Math.round((bytes / MB) * 10) / 10;
    return `${String(v).replace('.', ',')} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Dosya bu alana uygun mu: türü `accept` ile, boyutu `maxBytes` ile. Uygunsa null, değilse kişiye gösterilecek cümle.
 *  Uzantı büyük/küçük harf duyarsız; `image/*` gibi joker MIME türün başıyla eşleşir. Tarayıcı türü boş bırakırsa
 *  (bazı sistemlerde .md, .xliff) yalnız uzantıya bakılır. */
export function checkFile(file: FileLike, accept?: string, maxBytes?: number): string | null {
  const tokens = acceptTokens(accept);
  const name = file.name.toLowerCase();
  const mime = (file.type ?? '').toLowerCase();
  if (tokens.length) {
    const ok = tokens.some((t) => {
      if (t.startsWith('.')) return name.endsWith(t);
      if (t.endsWith('/*')) return !!mime && mime.startsWith(t.slice(0, -1));
      return !!mime && mime === t;
    });
    if (!ok) return `«${file.name}» bu alana uygun değil. Kabul edilen: ${acceptLabel(accept)}.`;
  }
  if (file.size <= 0) return `«${file.name}» boş bir dosya.`;
  if (maxBytes && file.size > maxBytes) return `«${file.name}» ${fmtSize(file.size)}; bu alanın sınırı ${fmtSize(maxBytes)}.`;
  return null;
}

/** Dosya adından okunur başlık: uzantı düşer, alt çizgi/tire boşluğa döner, fazla boşluk toplanır.
 *  "Kayip_Zaman-son.v3.docx" → "Kayip Zaman son.v3". Boş kalırsa dosya adının kendisi. Köprüdeki
 *  `editorial_desk.title_from_filename` ile aynı kural. */
export function titleFromFilename(filename: string): string {
  const base = filename.replace(/^.*[\\/]/, '');
  const stem = base.includes('.') ? base.slice(0, base.lastIndexOf('.')) : base;
  const t = stem.replace(/[_]+/g, ' ').replace(/\s+-\s+|-+/g, ' ').replace(/\s+/g, ' ').trim();
  return t || base.trim();
}

/** Sürükleme sayacı: iç öğelere geçerken dragleave/dragenter çifti gelir; vurgu sayaç sıfıra inince söner. */
export function dragDepth(depth: number, ev: 'enter' | 'leave' | 'drop'): number {
  if (ev === 'enter') return depth + 1;
  if (ev === 'leave') return Math.max(0, depth - 1);
  return 0;
}

/** Yükleme yapan işlemlerin yetki adları (`ozellik:<anahtar>`). Ad, access_catalog.json'daki etiketle birebir
 *  aynı olmalı (vitest denetler); yetkisi olmayan kişi alanı pasif görür ve hangi yetkinin gerektiğini okur. */
export const UPLOAD_FEATURES: Record<string, string> = {
  'son-okuma.belge': 'Belge yükleyip inceletme',
  'ceviri.yonet': 'Çeviri işi yönetme',
  'ceviri.terim': 'Terim bankası düzenleme',
  'basvuru.yaz': 'Başvuru kaydı ve editör raporu',
  'sozlesme.sablon': 'Sözleşme şablonları',
  'sozlesme-karsilastirma.belge': 'Karşılaştırma belgesi',
  'serbest.yonet': 'Serbest çalışan kaydı ve iş dağıtımı',
  'tasarim.uret': 'Kitap tasarımında üretim ve düzenleme',
  'ihale.belge': 'Şirket belge arşivi',
  'ihale.duzenle': 'İhale kaydı ve teklif hazırlığı',
  'pazar.rapor-yukle': 'Sektör raporu yükleme',
  'dijital.rapor-yukle': 'Dijital satış raporu yükleme',
  'okul.baglam-yukle': 'İlçe endeksi ve akademik takvim yükleme',
  'okur.ice-aktar': 'Okur: etkinlik dosyası yükleme',
  'kanal.yukle': 'Panel dosyası yükleme',
  'trendyol.yukle': 'Trendyol panel dosyası yükleme',
  'amazon.yukle': 'Amazon panel dosyası yükleme',
  'reklam.duzenle': 'Reklam verisi ve bağlar',
  'sosyal.duzenle': 'Sosyal medya takvimi düzenleme',
  'etkinlik.duzenle': 'Fuar ve etkinlik kartı hazırlama',
  'icerik.marka': 'Marka kiti ve yasaklı kalıplar',
  'icerik.talep': 'Görsel/metin talebi açma',
  'ik.aday-karar': 'Aday aşama kararı',
  'ik.calisan-yonet': 'Çalışan ve birim kaydını düzenleme',
  'ik.egitim-yonet': 'Eğitim kayıtlarını yönetme',
  'ik.sablon': 'İK şablonlarını düzenleme',
  'amazon.taslak': 'Listeleme ve pazar kartı taslağı',
  'katalog.duzenle': 'Katalog hazırlama',
  'bulten.duzenle': 'Bülten hazırlama',
  'uyum.yaz': 'Uyum takvimi',
  'risk.sigorta-bcp': 'Sigorta ve iş sürekliliği',
  'risk.yaz': 'Risk kaydı ve aksiyon',
  'icerik.uret': 'Görsel ve metin üretme',
  'ik.aday-hepsi': 'Bütün adayları görme',
  'isbirligi.duzenle': 'İşbirliği kaydı ve takibi',
};

/** Yetkisiz kişiye yazılan açıklama. */
export function noPermissionText(feature: string): string {
  const name = UPLOAD_FEATURES[feature] ?? feature;
  return `Bu işlem için yetkiniz yok. Gereken yetki: «${name}». Bir yönetici Portal ayarları → Yetkiler'den rolünüze ekleyebilir.`;
}

/** Alan kilitli mi, kilitliyse ne yazılır. `featureAllowed`: rolde `ozellik:<feature>` var mı (yetki bilinmiyorken
 *  true); `allowed`: ekranın kendi bilgisi (kayıt sahipliği, köprünün `can*` bayrağı). Kilitli değilse null. */
export function lockReason(o: { feature?: string; featureAllowed: boolean; allowed?: boolean; deniedText?: string }): string | null {
  if (o.feature && !o.featureAllowed) return noPermissionText(o.feature);
  if (o.allowed === false) return o.feature ? noPermissionText(o.feature) : o.deniedText ?? 'Bu işlem için yetkiniz yok.';
  return null;
}
