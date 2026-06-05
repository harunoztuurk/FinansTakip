from django.shortcuts import render, redirect
from django.db.models import Sum
from .models import Gelir, Gider


def home(request):

    toplam_gelir = Gelir.objects.aggregate(
        Sum("tutar")
    )["tutar__sum"] or 0

    toplam_gider = Gider.objects.aggregate(
        Sum("tutar")
    )["tutar__sum"] or 0

    bakiye = toplam_gelir - toplam_gider

    son_gelirler = Gelir.objects.all().order_by("-id")[:5]
    son_giderler = Gider.objects.all().order_by("-id")[:5]

    return render(request, "home.html", {
        "toplam_gelir": toplam_gelir,
        "toplam_gider": toplam_gider,
        "bakiye": bakiye,
        "son_gelirler": son_gelirler,
        "son_giderler": son_giderler,
    })

def gelir_ekle(request):
    if request.method == "POST":
        Gelir.objects.create(
            tarih=request.POST["tarih"],
            aciklama=request.POST["aciklama"],
            tutar=request.POST["tutar"],
            kategori=request.POST["kategori"]
        )

    gelirler = Gelir.objects.all().order_by("-tarih")

    baslangic = request.GET.get("baslangic")
    bitis = request.GET.get("bitis")
    kategori = request.GET.get("kategori")

    if baslangic:
        gelirler = gelirler.filter(tarih__gte=baslangic)

    if bitis:
        gelirler = gelirler.filter(tarih__lte=bitis)
    if kategori:
        gelirler = gelirler.filter(kategori=kategori)
    
    return render(request, "gelir_ekle.html", {"gelirler": gelirler})


def gider_ekle(request):
    if request.method == "POST":
        Gider.objects.create(
            tarih=request.POST["tarih"],
            aciklama=request.POST["aciklama"],
            tutar=request.POST["tutar"],
            kategori=request.POST["kategori"]
        )

    giderler = Gider.objects.all().order_by("-tarih")

    baslangic = request.GET.get("baslangic")
    bitis = request.GET.get("bitis")
    kategori = request.GET.get("kategori")

    if baslangic:
        giderler = giderler.filter(tarih__gte=baslangic)

    if bitis:
        giderler = giderler.filter(tarih__lte=bitis)

    if kategori:
        giderler = giderler.filter(kategori=kategori)

    return render(request, "gider_ekle.html", {"giderler": giderler})

def raporlar(request):
    toplam_gelir = Gelir.objects.aggregate(Sum("tutar"))["tutar__sum"] or 0
    toplam_gider = Gider.objects.aggregate(Sum("tutar"))["tutar__sum"] or 0
    bakiye = toplam_gelir - toplam_gider

    ay = request.GET.get("ay")

    gelirler = Gelir.objects.all()
    giderler = Gider.objects.all()

    if ay:
        yil, ay_numarasi = ay.split("-")
        gelirler = gelirler.filter(tarih__year=yil, tarih__month=ay_numarasi)
        giderler = giderler.filter(tarih__year=yil, tarih__month=ay_numarasi)

    aylik_gelir = gelirler.aggregate(Sum("tutar"))["tutar__sum"] or 0
    aylik_gider = giderler.aggregate(Sum("tutar"))["tutar__sum"] or 0
    aylik_bakiye = aylik_gelir - aylik_gider

    kategori_giderler = Gider.objects.values("kategori").annotate(toplam=Sum("tutar"))

    kategori_adlari = []
    kategori_tutarlari = []
    kategori_detaylari = []

    for item in kategori_giderler:
        kategori_adlari.append(item["kategori"])
        kategori_tutarlari.append(float(item["toplam"]))
        kategori_detaylari.append({
            "ad": item["kategori"],
            "tutar": item["toplam"]
        })

    return render(request, "raporlar.html", {
        "toplam_gelir": toplam_gelir,
        "toplam_gider": toplam_gider,
        "bakiye": bakiye,
        "kategori_adlari": kategori_adlari,
        "kategori_tutarlari": kategori_tutarlari,
        "kategori_detaylari": kategori_detaylari,
        "aylik_gelir": aylik_gelir,
        "aylik_gider": aylik_gider,
        "aylik_bakiye": aylik_bakiye,
        "secilen_ay": ay,
    })   

def gelir_sil(request, id):
    gelir = Gelir.objects.get(id=id)
    gelir.delete()
    return redirect("gelir_ekle")


def gider_sil(request, id):
    gider = Gider.objects.get(id=id)
    gider.delete()
    return redirect("gider_ekle")

def gider_duzenle(request, id):
    gider = Gider.objects.get(id=id)

    if request.method == "POST":
        gider.tarih = request.POST["tarih"]
        gider.aciklama = request.POST["aciklama"]
        gider.tutar = request.POST["tutar"]
        gider.kategori = request.POST["kategori"]
        gider.save()

        return redirect("gider_ekle")

    return render(request, "gider_duzenle.html", {"gider": gider})

def gelir_duzenle(request, id):
    gelir = Gelir.objects.get(id=id)

    if request.method == "POST":
        gelir.tarih = request.POST["tarih"]
        gelir.aciklama = request.POST["aciklama"]
        gelir.tutar = request.POST["tutar"]
        gelir.kategori = request.POST["kategori"]
        gelir.save()

        return redirect("gelir_ekle")

    return render(request, "gelir_duzenle.html", {"gelir": gelir})