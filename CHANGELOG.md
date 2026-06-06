# Changelog

Bu dosya, FinansTakip projesindeki önemli değişiklikleri listeler.

## [Geliştirme] - 2026-06-06

### Eklendi
- Kullanıcı kayıt, giriş ve çıkış sistemi eklendi.
- Gelir ve gider kayıtları kullanıcı hesabına bağlandı.
- Her kullanıcının yalnızca kendi gelir, gider, rapor ve PDF rapor verilerini görmesi sağlandı.
- Giriş yapmayan kullanıcıların gelir, gider, rapor ve kayıt yönetimi sayfalarına erişimi engellendi.
- ReportLab ile gerçek PDF rapor indirme özelliği eklendi.
- Kullanıcıya özel aylık bütçe hedefi ekleme ve düzenleme sistemi eklendi.
- Dashboard'da aylık bütçe hedefi, bu ayki gider, kalan bütçe ve harcama uyarıları gösterildi.
- Kullanıcıya özel gelir ve gider kategori yönetimi eklendi.
- Gelir ve gider formlarında sadece ilgili türdeki kullanıcı kategorilerinin seçilmesi sağlandı.
- Kişisel, ev ve işyeri finans türleri için ayrı gelir, gider, kategori, bütçe hedefi ve rapor filtreleme sistemi eklendi.
- Finans türüne bağlı tekrarlayan ödeme yönetimi ve girişte otomatik gider oluşturma sistemi eklendi.
- Tekrarlayan ödemelerde günlük, haftalık, aylık, yıllık ve özel tekrar aralığı desteği eklendi.
- Tekrarlayan ödemeler için bekliyor, ödendi, gecikti ve iptal edildi durum takibi eklendi.
- Tekrarlayan ödemeler için dönem bazlı ödeme takibi ve dönem üzerinden ödendi işaretleme eklendi.
- Uygulama arayüzü sol sidebar, üst navbar, modern dashboard kartları, tutarlı form düzenleri ve profesyonel tablo/grafik alanlarıyla yenilendi.
- Production ayarları, environment variable desteği, PostgreSQL bağlantısı, WhiteNoise static dosya servisi ve Render deploy dosyaları eklendi.
- `.env` desteği, Render için `Procfile`, CSRF trusted origin yönetimi ve `psycopg2-binary` PostgreSQL sürücüsü deploy hazırlığına eklendi.
- GitHub hazırlığı için yerel veritabanı, environment dosyaları, Python cache dosyaları ve static build çıktıları `.gitignore` kapsamına alındı.
- Render build sürecinde Django 6 uyumluluğu için Python sürümü `.python-version` ile 3.12 olarak sabitlendi.
- Render dış ağ kontrolü için `health/` endpoint'i eklendi ve host/CSRF environment değerleri şema, boşluk ve son slash hatalarına karşı normalize edildi.

### Düzeltildi
- Tekrarlayan ödeme tablosunda eksik kalan `tekrar_turu` ve `tekrar_araligi` kolonlarını veri silmeden ekleyen migration düzeltmesi eklendi.

## [İlk Sürüm] - 2026-06-05

### Eklendi
- Django tabanlı bütçe takip uygulaması oluşturuldu.
- Gelir ve gider modelleri eklendi.
- Gelir ekleme, listeleme, düzenleme ve silme ekranları eklendi.
- Gider ekleme, listeleme, düzenleme ve silme ekranları eklendi.
- Ana sayfada toplam gelir, toplam gider, bakiye ve son kayıtlar gösterildi.
- Raporlar ekranında toplam ve aylık finans özeti eklendi.
- Kategori bazlı gider özeti ve grafik alanları eklendi.
- SQLite veritabanı ve ilk migration dosyaları eklendi.
