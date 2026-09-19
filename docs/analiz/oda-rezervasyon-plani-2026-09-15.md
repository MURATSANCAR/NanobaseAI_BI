# Toplantı odası rezervasyonu: plan (2026-09-15)

## Amaç
Kampüs ekranındaki sabit "Kampüs Odaları & Stüdyo" kartı gerçek veriye bağlanır. Kişi takvimi açar, oda, gün ve
saat aralığı seçer, "Rezerve et" der. Başka biri baktığında o saat dolu görünür ve kimin aldığı yazar.

## Kurallar
- Rezervasyonlar **herkese açık**: oda, saat, rezerve edenin adı soyadı ve konu herkese görünür. (Kişiye özel CRM
  kartlarından farklı olarak bu ortak bir kaynaktır.)
- Kim olduğu istekten alınmaz; oturum çerezinden giriş servisine sorulur (`/timas/auth/session`: username + displayName).
- Saatler İstanbul saatiyle seçilir, UTC saklanır. Tarayıcının saat dilimi hesaba katılmaz: ekran "2026-09-17" ve
  "14:00" gönderir, sunucu Europe/Istanbul ile birleştirir.
- Aralık yarı açık: 14:00–15:00 ile 15:00–16:00 çakışmaz.
- Çakışma sunucuda, oda satırı kilitlenerek denetlenir (iki kişi aynı anda aynı saate basarsa biri kazanır, diğeri
  "az önce X aldı" mesajını görür).
- Geçmişe rezervasyon yapılmaz. Bitmiş rezervasyon iptal edilmez.
- İptali yalnız rezervasyonu yapan kişi ya da yönetici yapar. Silinmez, `cancelled_at` işaretlenir.
- Süre, gün sayısı veya kişi başı adet tavanı yok (sınır koyma kuralı). Izgara adımı ve gün başlangıcı/bitişi yönetim
  ayarıdır: `ROOM_DAY_START` 08:00, `ROOM_DAY_END` 20:00, `ROOM_SLOT_MINUTES` 30.
- Odaları yönetici tanımlar (ad, yer, kapasite). Sahte oda tohumlanmaz; oda yoksa kart bunu söyler, yöneticiye
  "Oda ekle" gösterir.
- Oluşturma, iptal, oda ekleme/kaldırma değişiklik kaydına (`semantic_audit`, kind `room`) yazılır.

## Veri (bi_meta, köprünün katalog veritabanı)
`semantic_rooms`: id, tenant_id, name, location, capacity, active, created_by, created_at.
`semantic_room_bookings`: id, tenant_id, room_id, starts_at, ends_at, username, display_name, title, created_at,
cancelled_at, cancelled_by. Dizin: (room_id, starts_at).

## Uçlar (köprü, :8795)
| Yöntem | Yol | Ne yapar |
|---|---|---|
| GET | /api/v1/rooms?date=YYYY-MM-DD | Odalar + o günün rezervasyonları + ayarlar + ben kimim, yönetici miyim |
| GET | /api/v1/rooms/now | Kampüs kartı: her odanın şu anki ve sıradaki rezervasyonu |
| POST | /api/v1/rooms/{roomId}/bookings | {date, start, end, title} → 201, çakışırsa 409 kimin aldığıyla |
| DELETE | /api/v1/rooms/bookings/{id} | İptal (sahibi ya da yönetici) |
| POST | /api/v1/admin/rooms | Oda ekle (yönetici) |
| DELETE | /api/v1/admin/rooms/{roomId} | Odayı kaldır, gelecekteki rezervasyonları iptal et (yönetici) |

## Ekran
1. **Kampüs kartı:** her oda bir satır. Boşsa yeşil nokta ve "Şu an boş · sıradaki 15:00 Ayşe K.". Doluysa kırmızı
   nokta ve "Dolu · Ayşe Kaya · 16:00'ya kadar". Satırdaki "Rezerve et" takvimi o oda seçili açar. 30 sn'de bir yenilenir.
2. **Takvim penceresi** (yerel `<dialog>`: odak tuzağı, Esc, erişilebilirlik tarayıcıdan):
   - Üstte gün şeridi: bugünden itibaren 14 gün + herhangi bir güne atlamak için tarih kutusu.
   - Ortada ızgara: satırlar saat aralıkları, sütunlar odalar. Dolu bloklarda ad soyad, konu, saat; kendi bloğumda "İptal".
   - Boş hücreye tıkla = 30 dk seçilir; fareyle sürükle ya da aynı sütunda başka hücreye Shift+tıkla = aralık uzar.
     Aralık dolu bir bloğun üstünden geçerse seçim orada durur. Dokunmatikte dokunuş seçer (kaydırma seçmez), satır
     44 px olur, aralık başlangıç/bitiş kutularıyla uzatılır. Klavyede boş hücreler sekmeyle gezilir, Enter seçer.
   - Karttan bir oda için açılınca o odanın ilk boş aralığı seçili gelir ve ızgara o saate kayar.
   - Altta özet çubuğu: oda, gün, başlangıç/bitiş seçim kutuları (ızgarayla eşleşir), konu kutusu, "Rezerve et".
   - 409 gelirse satır içi mesaj ve ızgara yenilenir. Başarıda blok hemen görünür.
   - Ekran açıkken 30 sn'de bir ve pencereye dönüldüğünde yenilenir; başkasının aldığı saat kendiliğinden dolar.
3. **Hareket:** yalnız pencere açılış/kapanışı (opacity + scale 0.96→1, 200 ms ease-out, kapanış 150 ms). Hücre seçimi
   anında, animasyonsuz (sık tekrarlanan etkileşim). Azaltılmış harekette yalnız opaklık.

## Test
- Çakışma: aynı oda, kesişen aralık → 409; bitişik aralık → kabul; başka oda → kabul.
- Geçmiş saat → 422. Bitiş ≤ başlangıç → 422. Izgara dışı dakika (14:10) → 422.
- İptal: başkası → 403, sahibi → tamam, yönetici → tamam; iptal edilen saat yeniden alınabilir.
- Gün sorgusu İstanbul gününe göre döner (23:30 UTC kaydı ertesi günde).
- Kimlik: çerez yoksa 401; istek gövdesindeki username yok sayılır.

## Uygulandı (2026-09-15)
- Sunucu: `backend/semantic_bridge/rooms.py`, uçlar `app.py` içinde, oturumdan ad soyad `board.session_of`,
  ayarlar ve değişiklik kaydı türleri `admin.py`. Test: `backend/semantic_layer/tests/test_rooms.py` (15 test).
- Ekran: `src/canvas/rooms/` (RoomsCard, RoomBookingDialog, time, rooms.css), istemci `roomsApi` (`engine.ts`).
  Kampüs'teki sabit oda kartı kaldırıldı.
- Doğrulama: sunucuda geçici kopyada test ve derleme; derlenmiş arayüz gerçek modülle deneme sunucusunda üç kullanıcıyla
  (yönetici, Ayşe, Mehmet) masaüstü ve telefon genişliğinde denendi: ekleme, sürükleyerek seçim, çakışmada 409 mesajı,
  başkasının kaydında İptal olmaması, kendi kaydını iptal, Esc ile kapanış.
- Canlıya alınmadı.
