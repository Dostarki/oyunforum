# LastZhood kampanya ayarları

## Yönetici paneli (güncel kaynak)

`/admin` sayfasına yönetici şifresiyle girin. Like bağlantısı, Repost bağlantısı, Reply metni/bağlantısı ve CLAIM ON X paylaşım metni buradan değiştirilip **Kaydet** ile MongoDB `campaign_settings` koleksiyonuna yazılır. Bu beş alan yalnızca kaydedilmiş panel verisinden okunur; `.env` değişiklikleri bunları geçersiz kılamaz.

- İlk başlangıçta yalnızca bir kez, mevcut aktif kampanya `.env` değerlerinden aktarılır. Önceki davranışı korumak için başlangıçta Like/Repost/Reply aynı Like bağlantısını alır. Sonra panelden bağımsız düzenlenebilir.
- Like ve Repost kendi bağlantılarını açar. Reply, kendi metni ve altında kendi bağlantısıyla X post bestecisini açar.
- CLAIM ON X / mevcut POST ON X düğmesi: paneldeki paylaşım metni + paneldeki Like bağlantısı + `PUBLIC_APP_URL/?ref=KOD`. Referans biçimi korunur.
- `/api/config` her istekte MongoDB'deki kaydı okur. Açık ziyaretçi sayfası yeniden odaklanınca ayarları yeniler; yeni sayfa açılışlarında da güncel kayıt okunur. Backend yeniden başlatmak gerekmez.
- Bağlantılar HTTPS x.com/twitter.com olmalıdır. Beş alan zorunludur. Ayarlar tek işlemde kaydedilir; eşzamanlı eski sürüm kaydı 409 ile reddedilir.

## Sunucu yapılandırması

Takip bağlantısı, görevlerin kısa açıklamaları, resmî X hesabı ve altyapı ayarları `.env` içinde kalır. Aşağıdaki kampanya değişkenleri panel kaydı yoksa **yalnızca ilk aktarım** için kullanılır; mevcut bir kaydı değiştirmez.

| Değişken | Açıklama |
| --- | --- |
| X_PROFILE_LINK | Resmî LastZhood X profil bağlantısı |
| X_FOLLOW_TEXT / X_FOLLOW_LINK | Takip görevinin görünen metni ve X bağlantısı |
| X_LIKE_TEXT / X_LIKE_LINK | Beğeni görevinin metni ve bağlantısı |
| X_REPOST_TEXT / X_REPOST_LINK | RT görevinin metni ve bağlantısı |
| X_COMMENT_TEXT / X_COMMENT_LINK | Yorum görevinin görünen metni ve yanıt bağlantısı |
| X_COMMENT_MESSAGE | X yorum penceresinde önceden yazılan mesaj |
| X_SHARE_TEXT / X_SHARE_LINK | POST ON X paylaşım metni ve X paylaşım adresi (intent); metnin altına X_LIKE_LINK, en alta katılımcının referans bağlantısı (PUBLIC_APP_URL/?ref=KOD) eklenir |
| PUBLIC_APP_URL | Kart ve referans bağlantılarının uygulama adresi |

`ADMIN_PASSWORD` ilk ve sonraki sunucu açılışlarında bcrypt ile hashlenir; MongoDB'de düz metin saklanmaz. Ortam şifresi değiştirilip sunucu yeniden başlatılırsa önceki oturumlar iptal olur. `JWT_SECRET` rastgele en az 32 karakter olmalıdır.

### Kaynak bağımsız admin girişi (2026-09-28)

`CORS_ORIGINS="*"` artık desteklenir: sunucu herhangi bir HTTP(S) web kaynağı için somut Origin değerini döndürür. Çerezli isteklerle birlikte geçersiz `Access-Control-Allow-Origin: *` yanıtı kullanılmaz. lastzhood.fun, www ve önizleme adresleri için tek tek izin kaydı gerekmez. İstenirse virgülle ayrılmış açık CORS listesi de kullanılabilir; admin API'sinde ayrıca bir kaynak engeli yoktur.

Güvenlik için giriş application/json ve `X-Admin-Client: lastzhood-admin` gerektirir. Şifre doğrulandıktan sonra cevapta bir `csrf_token` döner; bunun yalnızca SHA256 özeti MongoDB oturumuna yazılır. Arayüz bu kanıtı origin/sekme bağımsız `sessionStorage` içinde tutar ve tüm yönetici okuma/yazma, refresh ve logout çağrılarına `X-CSRF-Token` olarak ekler. JWT çerezleri HttpOnly kalır. Yalnızca çerez taşıyan yabancı site istekleri yetki alamaz; kanıtı şifresiz veren bir uç nokta yoktur. Eski çerez oturumları veya yeni sekme normal şifreli girişe döner; önbellek temizleme gerekmez.

Resmî hesap `https://x.com/LastZhood` olarak ayarlanmıştır. Kullanıcı belirli bir gönderi bağlantısı vermediği ve X gönderileri herkese açık taramada okunamadığı için beğeni, RT ve yorum görevleri bu profili açar. Katılımcılar bir LastZhood gönderisi üzerinde işlemlerini tamamlayıp beyan eder. Eski projenin gönderi bağlantıları kaldırılmıştır.

Belirli bir gönderiyi hedeflemek için `/admin` panelindeki ilgili bağlantıyı düzenleyin. Reply alanındaki bağlantı hedef gönderiye doğrudan yanıt atmak yerine paylaşım metninin altına eklenir; önceki istenen akış korunmuştur.

MONGO_URL, DB_NAME ve frontend REACT_APP_BACKEND_URL değerlerini değiştirmeyin. Giriş oturumları HttpOnly/Secure çerez ve oturuma bağlı CSRF kanıtıyla yönetilir; logout MongoDB oturumunu da iptal eder. Beş başarısız denemeden sonra 15 dakikalık pencere sınırı vardır.

Kullanıcı adı ve görev tamamlama kullanıcı beyanıdır; X hesabı sahipliği, gerçek takip/RT/yorum veya paylaşım doğrulanmaz. Cüzdan yalnızca EVM adresi olarak saklanır; özel anahtar, cüzdan bağlantısı veya işlem imzası istenmez. Cüzdan adresi herkese açık API yanıtlarına dahil edilmez.

Taslak aynı tarayıcının yerel belleğinde tutulur; son talep MongoDB'ye kaydedilir. Hesap girişi bulunmadığından farklı tarayıcıdan mevcut bir kaydın özel alanları görüntülenemez/değiştirilemez. Her X kullanıcı adı için tek kayıt vardır.

## X profil fotoğrafı

Kullanıcı adıyla devam edildiğinde FxTwitter'ın herkese açık profil kaynağı sorgulanır. API anahtarı/OAuth gerekmez. Hesap sahipliği doğrulanmaz. Özel fotoğraf bulunamazsa, hesap erişilemezse veya kaynak geçici hata verirse mevcut karakter görseli korunur; katılım engellenmez.

- `FXTWITTER_BASE_URL`, `FXTWITTER_USER_AGENT`: kaynak adresi ve LastZhood tanımlayıcısı
- `X_LOOKUP_TIMEOUT_SECONDS`: kaynak isteğinin azami süresi
- `X_AVATAR_MAX_BYTES`: indirilecek görsel boyutu sınırı
- `X_AVATAR_CDN_HOSTS`: izin verilen X görsel sunucuları; varsayılan `pbs.twimg.com`
- `X_AVATAR_CACHE_SECONDS`: başarılı fotoğraf adresi için metadata önbelleği (21600 saniye)
- `X_AVATAR_FAILURE_CACHE_SECONDS`: başarısız sorgu önbelleği (60 saniye)
- `X_LOOKUP_RATE_LIMIT`: istemci başına dakikalık fotoğraf uç noktası sınırı

Bu sağlayıcı ayarları değiştiğinde backend yeniden başlatılmalıdır. MongoDB `x_avatar_metadata` koleksiyonunda yalnızca kullanıcı adı, fotoğraf adresi, kaynak ve UTC geçerlilik tarihi saklanır; fotoğraf/Base64 tutulmaz. Dosya yüklemesi yoktur. Görsel sunucuda geçici olarak işlenip PNG'ye dönüştürülür ve bellekte en fazla 64 görsel/1 saat tutulur.

`GET /api/x/profile/{handle}` herkese açık fotoğraf durumunu döndürür. `GET /api/x/avatar/{handle}` yalnızca doğrulanmış X CDN adreslerinden görsel geçirir; kullanıcıdan URL kabul etmez. Tarayıcı/canvas bu ara bağlantıyı kullandığı için kart indirme ve panoya kopyalama çalışır. Görselin tamamı kırpılmadan karta yerleştirilir.

Ara sunucular HTTP `Cache-Control` başlığını `no-store` olarak sıkılaştırabilir. Bu, uygulamanın metadata/bellek önbelleğini kapatmaz; tekrar isteğinde `X-Avatar-Cache: HIT` gerçek bellek kullanımını belirtir. Tarayıcı/CDN önbelleğine bağımlı çalışılmaz.

FxTwitter üçüncü taraf, anahtarsız ve en iyi çaba esaslı bir kaynaktır; tüm hesaplar için kesintisiz/fotoğraf güncelliği garantisi yoktur. Varsayılan X silüeti, özel profil fotoğrafı sayılmadığından mevcut karaktere dönüş yapılır.