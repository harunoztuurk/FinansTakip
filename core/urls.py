from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('gelir-ekle/', views.gelir_ekle, name='gelir_ekle'),
    path('gider-ekle/', views.gider_ekle, name='gider_ekle'),
    path('raporlar/', views.raporlar, name='raporlar'),
    path('gelir-sil/<int:id>/', views.gelir_sil, name='gelir_sil'),
    path('gider-sil/<int:id>/', views.gider_sil, name='gider_sil'),
    path('gider-duzenle/<int:id>/', views.gider_duzenle, name='gider_duzenle'),
    path('gelir-duzenle/<int:id>/', views.gelir_duzenle, name='gelir_duzenle'),
]