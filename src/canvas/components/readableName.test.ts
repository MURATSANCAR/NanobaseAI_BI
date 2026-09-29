import { afterEach, describe, expect, it } from 'vitest';
import { rawTitle, readableName, readableText, setDisplayWords, setLogoNames, splitCompound } from './readableName';

afterEach(() => {
  setDisplayWords({});
  setLogoNames({ tables: {}, columns: {} });
});

describe('readableName: ham veritabanı adı → ekrandaki başlık', () => {
  it('Logo tablo adı: firma/dönem öneki atılır, Logo ekran adı yazılır', () => {
    expect(readableName('LG_411_CLCARD')).toBe('Cari kart');
    expect(readableName('LG_411_01_STLINE')).toBe('Stok hareketi');
    expect(readableName('LG_211_01_INVOICE')).toBe('Fatura');
    expect(readableName('LG_411_ITEMS')).toBe('Malzeme kartı');
    expect(readableName('L_CAPIWHOUSE')).toBe('Ambar');
  });

  it('Logo kolon adı ve nitelikli ad', () => {
    expect(readableName('NETTOTAL')).toBe('Net tutar');
    expect(readableName('TRCODE')).toBe('İşlem türü');
    expect(readableName('DATE_')).toBe('Tarih');
    expect(readableName('SPECODE2')).toBe('Özel kod 2');
    expect(readableName('CLCARD.SPECODE')).toBe('Cari kart · Özel kod');
    expect(readableName('LG_411_CLCARD.SPECODE')).toBe('Cari kart · Özel kod');
    expect(readableName('I.[NETTOTAL]')).toBe('Net tutar');
    expect(readableName('dbo.LG_411_01_STLINE')).toBe('Stok hareketi');
  });

  it('CRM adı: new_ öneki ve Base soneki atılır, birleşik yazım bölünür', () => {
    expect(readableName('new_projekarti')).toBe('Proje kartı');
    expect(readableName('new_kitapBase')).toBe('Kitap');
    expect(readableName('new_hedefkitle')).toBe('Hedef kitle');
    expect(readableName('new_iletimhakki')).toBe('İletim hakkı');
    expect(readableName('new_anasozlesmeid')).toBe('Ana sözleşme no');
    expect(readableName('new_sosyalmedyametni')).toBe('Sosyal medya metni');
    expect(readableName('new_EKitap')).toBe('E-kitap');
    expect(readableName('systemuser')).toBe('Kullanıcı');
    expect(readableName('createdon')).toBe('Oluşturma tarihi');
  });

  it('SQL takma adı, camelCase ve portal tablosu', () => {
    expect(readableName('okur_no')).toBe('Okur no');
    expect(readableName('ad_soyad')).toBe('Ad soyad');
    expect(readableName('net_12ay')).toBe('Net (12 ay)');
    expect(readableName('son_30_gun')).toBe('Son 30 gün');
    expect(readableName('iadeOrani')).toBe('İade oranı');
    expect(readableName('netTl')).toBe('Net TL');
    expect(readableName('semantic_seo_products')).toBe('SEO ürünler');
    expect(readableName('NET_CIRO')).toBe('Net ciro');
    expect(readableName('d2026')).toBe('2026');
    expect(readableName('is_active')).toBe('Aktif');
    expect(readableName('new_isPlaniAsamasi')).toBe('İş planı aşaması');
    expect(readableName('new_tckimlikno')).toBe('TC kimlik no');
  });

  it('katalog yazım haritası gelince onun Türkçesi kullanılır', () => {
    expect(readableName('gecen_yila_net_ciro')).toBe('Geçen yıla net ciro');
    setDisplayWords({ ciro: 'ciro', hasilat: 'hâsılat' });
    expect(readableName('toplam_hasilat')).toBe('Toplam hâsılat');
  });

  it('zaten okunur metne, sayıya, e-postaya dokunmaz', () => {
    expect(readableName('Net ciro')).toBe('Net ciro');
    expect(readableName('Satış tutarı (TL)')).toBe('Satış tutarı (TL)');
    expect(readableName('2026-09')).toBe('2026-09');
    expect(readableName('12.5')).toBe('12.5');
    expect(readableName('zeki@timas.com.tr')).toBe('zeki@timas.com.tr');
    expect(readableName('')).toBe('');
    expect(readableName(null)).toBe('');
    expect(readableName('KDV')).toBe('KDV');
  });

  it('ham ad üstüne gelince görünür; okunur adla aynıysa title yok', () => {
    expect(rawTitle('LG_411_CLCARD')).toBe('LG_411_CLCARD');
    expect(rawTitle('Net ciro')).toBeUndefined();
  });
});

describe('splitCompound', () => {
  it('bilinen köklerle böler, sondaki eki ayırmaz', () => {
    expect(splitCompound('projekarti')).toEqual(['proje', 'karti']);
    expect(splitCompound('stakkarti')).toEqual(['stak', 'karti']);
    expect(splitCompound('musteriler')).toBeNull();
    expect(splitCompound('hastag')).toBeNull();
    expect(splitCompound('kitap')).toBeNull();
    expect(splitCompound('uzunbilgi')).toEqual(['uzun', 'bilgi']);
    expect(splitCompound('toplamsatistutari')).toEqual(['toplam', 'satis', 'tutari']);
  });
});

describe('readableText: cümle içindeki ham adlar', () => {
  it('yalnız ham adı çevirir, geri kalan metne dokunmaz', () => {
    expect(readableText('Logo STLINE faturalı satış (TRCODE 7,8) — OUTCOST = 0')).toBe(
      'Logo stok hareketi faturalı satış (işlem türü 7,8) — birim maliyet = 0',
    );
    expect(readableText('Okuma · LG_411_CLCARD')).toBe('Okuma · cari kart');
    expect(readableText('Katalog terimleri · sl_concept, sl_mapping')).toBe('Katalog terimleri · kavram, eşleme');
    expect(readableText('new_projeBase/new_sozlesmeBase OwnerId')).toBe('Proje/sözleşme sahip no');
    expect(readableText('STLINE kayıtları 2021–2026')).toBe('Stok hareketi kayıtları 2021–2026');
  });

  it('marka adına, kısaltmaya ve düz cümleye dokunmaz', () => {
    expect(readableText('YouTube ve LinkedIn gönderileri')).toBe('YouTube ve LinkedIn gönderileri');
    expect(readableText('KDV dahil net ciro, TİMAŞ')).toBe('KDV dahil net ciro, TİMAŞ');
    expect(readableText('Bu rakam Logo satış faturalarından gelir.')).toBe('Bu rakam Logo satış faturalarından gelir.');
  });
});

describe('Logo alan sözlüğü haritası', () => {
  it('çekirdek sözlükte olmayan Logo adı haritadan; harita yoksa yarım çevrilmez', () => {
    expect(readableName('ACCOUNTEDCNT')).toBe('ACCOUNTEDCNT');
    expect(readableName('ADDTAXPRCOST')).toBe('ADDTAXPRCOST');
    setLogoNames({ tables: { SRVTOT: 'Aylık hizmet toplamları', NET: 'Network kontrolü' }, columns: { ACCOUNTEDCNT: 'Muhasebeleştirme sayısı', MONTH: 'Geri ödeme planı ayı' } });
    expect(readableName('ACCOUNTEDCNT')).toBe('Muhasebeleştirme sayısı');
    expect(readableName('LG_411_01_SRVTOT')).toBe('Aylık hizmet toplamları');
    expect(readableText('Kaynak: ACCOUNTEDCNT alanı')).toBe('Kaynak: ACCOUNTEDCNT alanı');
    // Genel sözcükler ve SQL takma adları haritaya takılmaz
    expect(readableName('MONTH')).toBe('Ay');
    expect(readableName('NET_CIRO')).toBe('Net ciro');
  });

  it('B2B ve marka yazımı', () => {
    expect(readableName('b2c_no')).toBe('B2C no');
    expect(readableName('new_yenib2b')).toBe('Yeni B2B');
    expect(readableName('new_youtubelink')).toBe('YouTube bağlantı');
    expect(readableName('new_Instagram')).toBe('Instagram');
  });
});
