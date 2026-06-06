from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health, name='health'),
    path('kayit/', views.kayit, name='kayit'),
    path('giris/', views.giris, name='giris'),
    path('cikis/', views.cikis, name='cikis'),
    path('', views.home, name='home'),
    path('butce-hedefi/', views.butce_hedefi, name='butce_hedefi'),
    path('kategoriler/', views.kategoriler, name='kategoriler'),
    path('kategori-duzenle/<int:id>/', views.kategori_duzenle, name='kategori_duzenle'),
    path('kategori-sil/<int:id>/', views.kategori_sil, name='kategori_sil'),
    path('tekrarlayan-odemeler/', views.tekrarlayan_odemeler, name='tekrarlayan_odemeler'),
    path('tekrarlayan-odeme-duzenle/<int:id>/', views.tekrarlayan_odeme_duzenle, name='tekrarlayan_odeme_duzenle'),
    path('tekrarlayan-odeme-sil/<int:id>/', views.tekrarlayan_odeme_sil, name='tekrarlayan_odeme_sil'),
    path('tekrarlayan-odeme-odendi/<int:id>/', views.tekrarlayan_odeme_odendi, name='tekrarlayan_odeme_odendi'),
    path('odeme-donemi-odendi/<int:id>/', views.odeme_donemi_odendi, name='odeme_donemi_odendi'),
    path('gelir-ekle/', views.gelir_ekle, name='gelir_ekle'),
    path('gider-ekle/', views.gider_ekle, name='gider_ekle'),
    path('raporlar/', views.raporlar, name='raporlar'),
    path('raporlar/pdf/', views.rapor_pdf, name='rapor_pdf'),
    path('gelir-sil/<int:id>/', views.gelir_sil, name='gelir_sil'),
    path('gider-sil/<int:id>/', views.gider_sil, name='gider_sil'),
    path('gider-duzenle/<int:id>/', views.gider_duzenle, name='gider_duzenle'),
    path('gelir-duzenle/<int:id>/', views.gelir_duzenle, name='gelir_duzenle'),
]
