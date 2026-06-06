from io import BytesIO
import calendar
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
    FINANS_KISISEL,
    FINANS_TURU_SECENEKLERI,
    ButceHedefi,
    Gelir,
    Gider,
    Kategori,
    OdemeDonemi,
    TekrarlayanOdeme,
)


def health(request):
    return JsonResponse({"status": "ok"})


def favicon(request):
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#2563eb"/><path fill="#fff" d="M18 20h28a6 6 0 0 1 6 6v20a6 6 0 0 1-6 6H18a6 6 0 0 1-6-6V26a6 6 0 0 1 6-6Zm0 8v18h28V28H18Zm23 7h6v6h-6z"/><path fill="#93c5fd" d="M20 12h22a4 4 0 0 1 4 4v4H18v-6a2 2 0 0 1 2-2Z"/></svg>"""
    response = HttpResponse(svg, content_type="image/svg+xml")
    response["Cache-Control"] = "public, max-age=86400"
    return response


def _secilen_finans_turu(veri):
    finans_turu = veri.get("finans_turu") or FINANS_KISISEL
    gecerli_turler = [deger for deger, _ in FINANS_TURU_SECENEKLERI]
    if finans_turu not in gecerli_turler:
        return FINANS_KISISEL
    return finans_turu


def _finans_turu_context(finans_turu):
    return {
        "finans_turleri": FINANS_TURU_SECENEKLERI,
        "secilen_finans_turu": finans_turu,
    }


def _ay_sonu(yil, ay):
    return calendar.monthrange(yil, ay)[1]


def _ay_ekle(tarih, ay_sayisi):
    toplam_ay = tarih.month - 1 + ay_sayisi
    yil = tarih.year + toplam_ay // 12
    ay = toplam_ay % 12 + 1
    gun = min(tarih.day, _ay_sonu(yil, ay))
    return tarih.replace(year=yil, month=ay, day=gun)


def _yil_ekle(tarih, yil_sayisi):
    yil = tarih.year + yil_sayisi
    gun = min(tarih.day, _ay_sonu(yil, tarih.month))
    return tarih.replace(year=yil, day=gun)


def _sonraki_odeme_tarihi(odeme, referans_tarihi):
    tarih = odeme.baslangic_tarihi
    aralik = max(odeme.tekrar_araligi or 1, 1)

    if tarih > referans_tarihi:
        return tarih

    while tarih < referans_tarihi:
        if odeme.tekrar_turu == TekrarlayanOdeme.GUNLUK:
            tarih = tarih + timedelta(days=aralik)
        elif odeme.tekrar_turu == TekrarlayanOdeme.HAFTALIK:
            tarih = tarih + timedelta(weeks=aralik)
        elif odeme.tekrar_turu == TekrarlayanOdeme.OZEL:
            tarih = tarih + timedelta(days=aralik)
        elif odeme.tekrar_turu == TekrarlayanOdeme.YILLIK:
            tarih = _yil_ekle(tarih, aralik)
        else:
            tarih = _ay_ekle(tarih, aralik)

    return tarih


def _bekleyen_odeme_tarihi(odeme):
    if odeme.son_olusturma_tarihi:
        referans_tarihi = odeme.son_olusturma_tarihi + timedelta(days=1)
    else:
        referans_tarihi = odeme.baslangic_tarihi

    return _sonraki_odeme_tarihi(odeme, referans_tarihi)


def _tekrarlayan_odeme_gideri_olustur(odeme, vade_tarihi):
    if odeme.son_gider and odeme.son_olusturma_tarihi == vade_tarihi:
        gider = odeme.son_gider
    else:
        gider = Gider.objects.create(
            kullanici=odeme.kullanici,
            finans_turu=odeme.finans_turu,
            tarih=vade_tarihi,
            aciklama=odeme.aciklama or odeme.odeme_adi,
            tutar=odeme.tutar,
            kategori=odeme.kategori.ad,
        )

    odeme.son_olusturma_tarihi = vade_tarihi
    odeme.son_gider = gider
    odeme.odeme_durumu = TekrarlayanOdeme.ODENDI
    odeme.save(update_fields=["son_olusturma_tarihi", "son_gider", "odeme_durumu"])
    return gider


def _odeme_donemi_gideri_olustur(donem):
    odeme = donem.tekrarlayan_odeme
    gider = Gider.objects.create(
        kullanici=odeme.kullanici,
        finans_turu=odeme.finans_turu,
        tarih=donem.vade_tarihi,
        aciklama=odeme.aciklama or odeme.odeme_adi,
        tutar=odeme.tutar,
        kategori=odeme.kategori.ad,
    )
    donem.durum = OdemeDonemi.ODENDI
    donem.save(update_fields=["durum"])
    odeme.son_olusturma_tarihi = donem.vade_tarihi
    odeme.son_gider = gider
    odeme.odeme_durumu = TekrarlayanOdeme.ODENDI
    odeme.save(update_fields=["son_olusturma_tarihi", "son_gider", "odeme_durumu"])
    return gider


def _donem_durum_verisi(donem, bugun):
    if donem.durum == OdemeDonemi.ODENDI:
        return {"deger": OdemeDonemi.ODENDI, "etiket": "Ödendi", "renk": "success"}
    if donem.durum == OdemeDonemi.IPTAL:
        return {"deger": OdemeDonemi.IPTAL, "etiket": "İptal Edildi", "renk": "secondary"}
    if donem.vade_tarihi < bugun:
        return {"deger": OdemeDonemi.GECIKTI, "etiket": "Gecikti", "renk": "danger"}
    return {"deger": OdemeDonemi.BEKLIYOR, "etiket": "Bekliyor", "renk": "warning"}


def _donem_durumu_guncelle(donem, bugun):
    durum = _donem_durum_verisi(donem, bugun)
    if donem.durum in [OdemeDonemi.ODENDI, OdemeDonemi.IPTAL]:
        return durum
    if donem.durum != durum["deger"]:
        donem.durum = durum["deger"]
        donem.save(update_fields=["durum"])
    return durum


def _donem_vade_tarihi(odeme, yil, ay):
    ay_baslangici = date(yil, ay, 1)
    ay_bitisi = ay_baslangici.replace(day=_ay_sonu(yil, ay))
    if odeme.baslangic_tarihi > ay_bitisi:
        return None

    referans_tarihi = max(ay_baslangici, odeme.baslangic_tarihi)
    vade_tarihi = _sonraki_odeme_tarihi(odeme, referans_tarihi)
    if vade_tarihi <= ay_bitisi:
        return vade_tarihi
    return None


def _odeme_donemlerini_olustur(kullanici, finans_turu=None):
    bugun = timezone.now().date()
    ay_bitisi = bugun.replace(day=_ay_sonu(bugun.year, bugun.month))
    odemeler = TekrarlayanOdeme.objects.filter(
        kullanici=kullanici,
        aktif=True,
        baslangic_tarihi__lte=ay_bitisi,
    ).select_related("kategori")

    if finans_turu:
        odemeler = odemeler.filter(finans_turu=finans_turu)

    for odeme in odemeler:
        yil = odeme.baslangic_tarihi.year
        ay = odeme.baslangic_tarihi.month

        while (yil, ay) <= (bugun.year, bugun.month):
            vade_tarihi = _donem_vade_tarihi(odeme, yil, ay)
            if vade_tarihi:
                OdemeDonemi.objects.get_or_create(
                    tekrarlayan_odeme=odeme,
                    donem_yil=yil,
                    donem_ay=ay,
                    defaults={
                        "vade_tarihi": vade_tarihi,
                        "durum": OdemeDonemi.BEKLIYOR,
                    },
                )

            ay += 1
            if ay > 12:
                ay = 1
                yil += 1


def _odeme_durumu_verisi(odeme, vade_tarihi, bugun):
    if not odeme.aktif or odeme.odeme_durumu == TekrarlayanOdeme.IPTAL:
        return {
            "deger": TekrarlayanOdeme.IPTAL,
            "etiket": "İptal edildi",
            "renk": "secondary",
        }

    if odeme.son_olusturma_tarihi == vade_tarihi and odeme.son_gider_id:
        return {
            "deger": TekrarlayanOdeme.ODENDI,
            "etiket": "Ödendi",
            "renk": "success",
        }

    if vade_tarihi < bugun:
        return {
            "deger": TekrarlayanOdeme.GECIKTI,
            "etiket": "Gecikti",
            "renk": "danger",
        }

    return {
        "deger": TekrarlayanOdeme.BEKLIYOR,
        "etiket": "Bekliyor",
        "renk": "warning",
    }


def _tekrarlayan_odemeleri_olustur(kullanici):
    _odeme_donemlerini_olustur(kullanici)


def _tekrarlayan_odeme_verileri(kullanici, finans_turu):
    bugun = timezone.now().date()
    ay_baslangici = bugun.replace(day=1)
    ay_bitisi = bugun.replace(day=_ay_sonu(bugun.year, bugun.month))
    _odeme_donemlerini_olustur(kullanici, finans_turu)

    donemler = OdemeDonemi.objects.filter(
        tekrarlayan_odeme__kullanici=kullanici,
        tekrarlayan_odeme__finans_turu=finans_turu,
        vade_tarihi__gte=ay_baslangici,
        vade_tarihi__lte=ay_bitisi,
    ).select_related("tekrarlayan_odeme", "tekrarlayan_odeme__kategori").order_by("vade_tarihi")

    bu_ay_odemeler = []
    yaklasan_odemeler = []
    geciken_odemeler = []

    for donem in donemler:
        durum = _donem_durumu_guncelle(donem, bugun)
        kayit = {
            "donem": donem,
            "odeme": donem.tekrarlayan_odeme,
            "vade_tarihi": donem.vade_tarihi,
            "durum": durum,
        }
        bu_ay_odemeler.append(kayit)

        if durum["deger"] == OdemeDonemi.GECIKTI:
            geciken_odemeler.append(kayit)
        elif durum["deger"] == OdemeDonemi.BEKLIYOR:
            yaklasan_odemeler.append(kayit)

    return {
        "bu_ay_tekrarlayan_odemeler": bu_ay_odemeler,
        "yaklasan_odemeler": yaklasan_odemeler,
        "geciken_odemeler": geciken_odemeler,
    }


def _aylik_butce_verileri(kullanici, finans_turu):
    bugun = timezone.now().date()
    yil = bugun.year
    ay = bugun.month

    bu_ay_gider = Gider.objects.filter(
        kullanici=kullanici,
        finans_turu=finans_turu,
        tarih__year=yil,
        tarih__month=ay,
    ).aggregate(Sum("tutar"))["tutar__sum"] or 0

    butce_hedefi = ButceHedefi.objects.filter(
        kullanici=kullanici,
        finans_turu=finans_turu,
        yil=yil,
        ay=ay,
    ).first()

    hedef_tutar = butce_hedefi.hedef_tutar if butce_hedefi else None
    kalan_butce = hedef_tutar - bu_ay_gider if hedef_tutar is not None else None
    butce_uyari = None

    if hedef_tutar and hedef_tutar > 0:
        kullanim_orani = (bu_ay_gider / hedef_tutar) * 100
        if bu_ay_gider > hedef_tutar:
            butce_uyari = "danger"
        elif kullanim_orani > 80:
            butce_uyari = "warning"
    else:
        kullanim_orani = 0

    return {
        "butce_hedefi": butce_hedefi,
        "butce_yil": yil,
        "butce_ay": ay,
        "aylik_butce_hedefi": hedef_tutar,
        "bu_ay_gider": bu_ay_gider,
        "kalan_butce": kalan_butce,
        "butce_uyari": butce_uyari,
        "butce_kullanim_orani": round(float(kullanim_orani), 2),
        **_finans_turu_context(finans_turu),
    }


def _rapor_verileri(kullanici, finans_turu, ay=None):
    tum_gelirler = Gelir.objects.filter(kullanici=kullanici, finans_turu=finans_turu)
    tum_giderler = Gider.objects.filter(kullanici=kullanici, finans_turu=finans_turu)

    toplam_gelir = tum_gelirler.aggregate(Sum("tutar"))["tutar__sum"] or 0
    toplam_gider = tum_giderler.aggregate(Sum("tutar"))["tutar__sum"] or 0
    bakiye = toplam_gelir - toplam_gider

    gelirler = tum_gelirler
    giderler = tum_giderler

    import re
    if ay and re.match(r'^\d{4}-\d{2}$', ay):
        yil, ay_numarasi = ay.split("-")
        gelirler = gelirler.filter(tarih__year=yil, tarih__month=ay_numarasi)
        giderler = giderler.filter(tarih__year=yil, tarih__month=ay_numarasi)
    else:
        ay = None

    aylik_gelir = gelirler.aggregate(Sum("tutar"))["tutar__sum"] or 0
    aylik_gider = giderler.aggregate(Sum("tutar"))["tutar__sum"] or 0
    aylik_bakiye = aylik_gelir - aylik_gider

    kategori_giderler = giderler.values("kategori").annotate(toplam=Sum("tutar"))

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

    return {
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
        **_finans_turu_context(finans_turu),
    }


def _pdf_font_adi():
    font_adi = "TurkceFont"
    if font_adi in pdfmetrics.getRegisteredFontNames():
        return font_adi

    font_yollari = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ]

    for font_yolu in font_yollari:
        if font_yolu.exists():
            pdfmetrics.registerFont(TTFont(font_adi, str(font_yolu)))
            return font_adi

    return "Helvetica"


def kayit(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            kullanici = form.save()
            login(request, kullanici)
            return redirect("home")
    else:
        form = UserCreationForm()

    return render(request, "kayit.html", {"form": form})


def giris(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            kullanici = form.get_user()
            login(request, kullanici)
            _tekrarlayan_odemeleri_olustur(kullanici)
            return redirect("home")
    else:
        form = AuthenticationForm()

    return render(request, "giris.html", {"form": form})


@login_required
def cikis(request):
    logout(request)
    return redirect("giris")


@login_required
def home(request):
    finans_turu = _secilen_finans_turu(request.GET)

    toplam_gelir = Gelir.objects.filter(kullanici=request.user, finans_turu=finans_turu).aggregate(
        Sum("tutar")
    )["tutar__sum"] or 0

    toplam_gider = Gider.objects.filter(kullanici=request.user, finans_turu=finans_turu).aggregate(
        Sum("tutar")
    )["tutar__sum"] or 0

    bakiye = toplam_gelir - toplam_gider

    son_gelirler = Gelir.objects.filter(kullanici=request.user, finans_turu=finans_turu).order_by("-id")[:5]
    son_giderler = Gider.objects.filter(kullanici=request.user, finans_turu=finans_turu).order_by("-id")[:5]

    context = {
        "toplam_gelir": toplam_gelir,
        "toplam_gider": toplam_gider,
        "bakiye": bakiye,
        "son_gelirler": son_gelirler,
        "son_giderler": son_giderler,
    }
    context.update(_aylik_butce_verileri(request.user, finans_turu))
    context.update(_tekrarlayan_odeme_verileri(request.user, finans_turu))

    return render(request, "home.html", context)


@login_required
def butce_hedefi(request):
    finans_turu = _secilen_finans_turu(request.POST if request.method == "POST" else request.GET)
    butce_verileri = _aylik_butce_verileri(request.user, finans_turu)
    hedef = butce_verileri["butce_hedefi"]
    hata = None

    if request.method == "POST":
        hedef_tutar = request.POST.get("hedef_tutar")

        try:
            hedef_tutar = Decimal(hedef_tutar)
        except (InvalidOperation, TypeError):
            hata = "Lütfen geçerli bir bütçe hedefi girin."
        else:
            if hedef_tutar <= 0:
                hata = "Bütçe hedefi sıfırdan büyük olmalıdır."
            else:
                hedef, _ = ButceHedefi.objects.update_or_create(
                    kullanici=request.user,
                    finans_turu=finans_turu,
                    yil=butce_verileri["butce_yil"],
                    ay=butce_verileri["butce_ay"],
                    defaults={"hedef_tutar": hedef_tutar},
                )
                return redirect(f"/?finans_turu={finans_turu}")

    return render(request, "butce_hedefi.html", {
        **butce_verileri,
        "hedef": hedef,
        "hata": hata,
    })


@login_required
def kategoriler(request):
    finans_turu = _secilen_finans_turu(request.POST if request.method == "POST" else request.GET)
    hata = None

    if request.method == "POST":
        ad = request.POST.get("ad", "").strip()
        tur = request.POST.get("tur")

        if not ad or tur not in [Kategori.GELIR, Kategori.GIDER]:
            hata = "Lütfen kategori adı ve türünü doğru girin."
        elif Kategori.objects.filter(kullanici=request.user, finans_turu=finans_turu, ad=ad, tur=tur).exists():
            hata = "Bu kategori zaten mevcut."
        else:
            Kategori.objects.create(kullanici=request.user, finans_turu=finans_turu, ad=ad, tur=tur)
            return redirect(f"/kategoriler/?finans_turu={finans_turu}")

    kullanici_kategorileri = Kategori.objects.filter(
        kullanici=request.user,
        finans_turu=finans_turu,
    ).order_by("tur", "ad")
    return render(request, "kategoriler.html", {
        "kategoriler": kullanici_kategorileri,
        "turler": Kategori.TUR_SECENEKLERI,
        "hata": hata,
        **_finans_turu_context(finans_turu),
    })


@login_required
def kategori_duzenle(request, id):
    kategori = get_object_or_404(Kategori, id=id, kullanici=request.user)
    finans_turu = kategori.finans_turu
    hata = None

    if request.method == "POST":
        ad = request.POST.get("ad", "").strip()
        tur = request.POST.get("tur")
        finans_turu = _secilen_finans_turu(request.POST)

        if not ad or tur not in [Kategori.GELIR, Kategori.GIDER]:
            hata = "Lütfen kategori adı ve türünü doğru girin."
        elif Kategori.objects.filter(kullanici=request.user, finans_turu=finans_turu, ad=ad, tur=tur).exclude(id=kategori.id).exists():
            hata = "Bu kategori zaten mevcut."
        else:
            kategori.ad = ad
            kategori.tur = tur
            kategori.finans_turu = finans_turu
            kategori.save()
            return redirect(f"/kategoriler/?finans_turu={finans_turu}")

    return render(request, "kategori_duzenle.html", {
        "kategori": kategori,
        "turler": Kategori.TUR_SECENEKLERI,
        "hata": hata,
        **_finans_turu_context(finans_turu),
    })


@login_required
def kategori_sil(request, id):
    kategori = get_object_or_404(Kategori, id=id, kullanici=request.user)
    finans_turu = kategori.finans_turu
    kategori.delete()
    return redirect(f"/kategoriler/?finans_turu={finans_turu}")


@login_required
def tekrarlayan_odemeler(request):
    finans_turu = _secilen_finans_turu(request.POST if request.method == "POST" else request.GET)
    kategoriler = Kategori.objects.filter(
        kullanici=request.user,
        finans_turu=finans_turu,
        tur=Kategori.GIDER,
    ).order_by("ad")
    hata = None

    if request.method == "POST":
        kategori_id = request.POST.get("kategori")
        tekrar_turu = request.POST.get("tekrar_turu")
        kategori = None
        if kategori_id:
            kategori = kategoriler.filter(id=kategori_id).first()

        try:
            tutar = Decimal(request.POST.get("tutar"))
        except (InvalidOperation, TypeError):
            tutar = None

        try:
            tekrar_araligi = int(request.POST.get("tekrar_araligi"))
        except (TypeError, ValueError):
            tekrar_araligi = 0

        if not kategori:
            hata = "Tekrarlayan ödeme için seçili finans türüne ait gider kategorisi seçmelisin."
        elif tekrar_turu not in [deger for deger, _ in TekrarlayanOdeme.TEKRAR_TURU_SECENEKLERI]:
            hata = "Lütfen geçerli bir tekrar türü seçin."
        elif tekrar_araligi <= 0:
            hata = "Tekrar aralığı pozitif tam sayı olmalıdır."
        elif not request.POST.get("odeme_adi", "").strip():
            hata = "Ödeme adı zorunludur."
        elif tutar is None or tutar <= 0:
            hata = "Tutar sıfırdan büyük olmalıdır."
        else:
            aktif = bool(request.POST.get("aktif"))
            TekrarlayanOdeme.objects.create(
                kullanici=request.user,
                finans_turu=finans_turu,
                kategori=kategori,
                odeme_adi=request.POST["odeme_adi"].strip(),
                aciklama=request.POST.get("aciklama", "").strip(),
                tutar=tutar,
                baslangic_tarihi=request.POST["baslangic_tarihi"],
                tekrar_turu=tekrar_turu,
                tekrar_araligi=tekrar_araligi,
                aktif=aktif,
                odeme_durumu=TekrarlayanOdeme.BEKLIYOR if aktif else TekrarlayanOdeme.IPTAL,
            )
            return redirect(f"/tekrarlayan-odemeler/?finans_turu={finans_turu}")

    odemeler = TekrarlayanOdeme.objects.filter(
        kullanici=request.user,
        finans_turu=finans_turu,
    ).select_related("kategori").order_by("-aktif", "baslangic_tarihi", "odeme_adi")
    bugun = timezone.now().date()
    _odeme_donemlerini_olustur(request.user, finans_turu)
    odeme_kayitlari = []
    for odeme in odemeler:
        vade_tarihi = _bekleyen_odeme_tarihi(odeme)
        odeme_kayitlari.append({
            "odeme": odeme,
            "vade_tarihi": vade_tarihi,
            "durum": _odeme_durumu_verisi(odeme, vade_tarihi, bugun),
        })
    donem_kayitlari = []
    donemler = OdemeDonemi.objects.filter(
        tekrarlayan_odeme__kullanici=request.user,
        tekrarlayan_odeme__finans_turu=finans_turu,
    ).select_related("tekrarlayan_odeme", "tekrarlayan_odeme__kategori").order_by("-donem_yil", "-donem_ay", "vade_tarihi")
    for donem in donemler:
        donem_kayitlari.append({
            "donem": donem,
            "odeme": donem.tekrarlayan_odeme,
            "durum": _donem_durumu_guncelle(donem, bugun),
        })

    return render(request, "tekrarlayan_odemeler.html", {
        "odeme_kayitlari": odeme_kayitlari,
        "donem_kayitlari": donem_kayitlari,
        "kategoriler": kategoriler,
        "tekrar_turleri": TekrarlayanOdeme.TEKRAR_TURU_SECENEKLERI,
        "hata": hata,
        **_finans_turu_context(finans_turu),
    })


@login_required
def tekrarlayan_odeme_duzenle(request, id):
    odeme = get_object_or_404(TekrarlayanOdeme, id=id, kullanici=request.user)
    finans_turu = _secilen_finans_turu(request.POST) if request.method == "POST" else odeme.finans_turu
    kategoriler = Kategori.objects.filter(
        kullanici=request.user,
        finans_turu=finans_turu,
        tur=Kategori.GIDER,
    ).order_by("ad")
    hata = None

    if request.method == "POST":
        kategori_id = request.POST.get("kategori")
        tekrar_turu = request.POST.get("tekrar_turu")
        kategori = None
        if kategori_id:
            kategori = kategoriler.filter(id=kategori_id).first()

        try:
            tutar = Decimal(request.POST.get("tutar"))
        except (InvalidOperation, TypeError):
            tutar = None

        try:
            tekrar_araligi = int(request.POST.get("tekrar_araligi"))
        except (TypeError, ValueError):
            tekrar_araligi = 0

        if not kategori:
            hata = "Tekrarlayan ödeme için seçili finans türüne ait gider kategorisi seçmelisin."
        elif tekrar_turu not in [deger for deger, _ in TekrarlayanOdeme.TEKRAR_TURU_SECENEKLERI]:
            hata = "Lütfen geçerli bir tekrar türü seçin."
        elif tekrar_araligi <= 0:
            hata = "Tekrar aralığı pozitif tam sayı olmalıdır."
        elif not request.POST.get("odeme_adi", "").strip():
            hata = "Ödeme adı zorunludur."
        elif tutar is None or tutar <= 0:
            hata = "Tutar sıfırdan büyük olmalıdır."
        else:
            aktif = bool(request.POST.get("aktif"))
            odeme.finans_turu = finans_turu
            odeme.kategori = kategori
            odeme.odeme_adi = request.POST["odeme_adi"].strip()
            odeme.aciklama = request.POST.get("aciklama", "").strip()
            odeme.tutar = tutar
            odeme.baslangic_tarihi = request.POST["baslangic_tarihi"]
            odeme.tekrar_turu = tekrar_turu
            odeme.tekrar_araligi = tekrar_araligi
            odeme.aktif = aktif
            if not aktif:
                odeme.odeme_durumu = TekrarlayanOdeme.IPTAL
            elif odeme.odeme_durumu == TekrarlayanOdeme.IPTAL:
                odeme.odeme_durumu = TekrarlayanOdeme.BEKLIYOR
            odeme.save()
            return redirect(f"/tekrarlayan-odemeler/?finans_turu={finans_turu}")

    return render(request, "tekrarlayan_odeme_duzenle.html", {
        "odeme": odeme,
        "kategoriler": kategoriler,
        "tekrar_turleri": TekrarlayanOdeme.TEKRAR_TURU_SECENEKLERI,
        "hata": hata,
        **_finans_turu_context(finans_turu),
    })


@login_required
def tekrarlayan_odeme_sil(request, id):
    odeme = get_object_or_404(TekrarlayanOdeme, id=id, kullanici=request.user)
    finans_turu = odeme.finans_turu
    odeme.delete()
    return redirect(f"/tekrarlayan-odemeler/?finans_turu={finans_turu}")


@login_required
def tekrarlayan_odeme_odendi(request, id):
    odeme = get_object_or_404(TekrarlayanOdeme, id=id, kullanici=request.user, aktif=True)
    finans_turu = odeme.finans_turu
    vade_tarihi = _bekleyen_odeme_tarihi(odeme)
    _tekrarlayan_odeme_gideri_olustur(odeme, vade_tarihi)
    return redirect(f"/tekrarlayan-odemeler/?finans_turu={finans_turu}")


@login_required
def odeme_donemi_odendi(request, id):
    donem = get_object_or_404(
        OdemeDonemi,
        id=id,
        tekrarlayan_odeme__kullanici=request.user,
    )
    finans_turu = donem.tekrarlayan_odeme.finans_turu

    if donem.durum != OdemeDonemi.ODENDI:
        _odeme_donemi_gideri_olustur(donem)

    return redirect(f"/tekrarlayan-odemeler/?finans_turu={finans_turu}")

@login_required
def gelir_ekle(request):
    finans_turu = _secilen_finans_turu(request.POST if request.method == "POST" else request.GET)
    gelir_kategorileri = Kategori.objects.filter(
        kullanici=request.user,
        finans_turu=finans_turu,
        tur=Kategori.GELIR,
    ).order_by("ad")
    hata = None

    if request.method == "POST":
        kategori_id = request.POST.get("kategori")
        kategori = None
        if kategori_id:
            kategori = Kategori.objects.filter(
                id=kategori_id,
                kullanici=request.user,
                finans_turu=finans_turu,
                tur=Kategori.GELIR,
            ).first()

        if not kategori:
            hata = "Gelir kaydı için önce gelir kategorisi seçmelisin."
        else:
            Gelir.objects.create(
                kullanici=request.user,
                finans_turu=finans_turu,
                tarih=request.POST["tarih"],
                aciklama=request.POST["aciklama"],
                tutar=request.POST["tutar"],
                kategori=kategori.ad
            )
            return redirect(f"/gelir-ekle/?finans_turu={finans_turu}")

    gelirler = Gelir.objects.filter(kullanici=request.user, finans_turu=finans_turu).order_by("-tarih")

    baslangic = request.GET.get("baslangic")
    bitis = request.GET.get("bitis")
    kategori = request.GET.get("kategori")

    if baslangic:
        gelirler = gelirler.filter(tarih__gte=baslangic)

    if bitis:
        gelirler = gelirler.filter(tarih__lte=bitis)
    if kategori:
        gelirler = gelirler.filter(kategori=kategori)
    
    return render(request, "gelir_ekle.html", {
        "gelirler": gelirler,
        "gelir_kategorileri": gelir_kategorileri,
        "hata": hata,
        **_finans_turu_context(finans_turu),
    })


@login_required
def gider_ekle(request):
    finans_turu = _secilen_finans_turu(request.POST if request.method == "POST" else request.GET)
    gider_kategorileri = Kategori.objects.filter(
        kullanici=request.user,
        finans_turu=finans_turu,
        tur=Kategori.GIDER,
    ).order_by("ad")
    hata = None

    if request.method == "POST":
        kategori_id = request.POST.get("kategori")
        kategori = None
        if kategori_id:
            kategori = Kategori.objects.filter(
                id=kategori_id,
                kullanici=request.user,
                finans_turu=finans_turu,
                tur=Kategori.GIDER,
            ).first()

        if not kategori:
            hata = "Gider kaydı için önce gider kategorisi seçmelisin."
        else:
            Gider.objects.create(
                kullanici=request.user,
                finans_turu=finans_turu,
                tarih=request.POST["tarih"],
                aciklama=request.POST["aciklama"],
                tutar=request.POST["tutar"],
                kategori=kategori.ad
            )
            return redirect(f"/gider-ekle/?finans_turu={finans_turu}")

    giderler = Gider.objects.filter(kullanici=request.user, finans_turu=finans_turu).order_by("-tarih")

    baslangic = request.GET.get("baslangic")
    bitis = request.GET.get("bitis")
    kategori = request.GET.get("kategori")

    if baslangic:
        giderler = giderler.filter(tarih__gte=baslangic)

    if bitis:
        giderler = giderler.filter(tarih__lte=bitis)

    if kategori:
        giderler = giderler.filter(kategori=kategori)

    return render(request, "gider_ekle.html", {
        "giderler": giderler,
        "gider_kategorileri": gider_kategorileri,
        "hata": hata,
        **_finans_turu_context(finans_turu),
    })

@login_required
def raporlar(request):
    ay = request.GET.get("ay")
    finans_turu = _secilen_finans_turu(request.GET)
    return render(request, "raporlar.html", _rapor_verileri(request.user, finans_turu, ay))


@login_required
def rapor_pdf(request):
    ay = request.GET.get("ay")
    finans_turu = _secilen_finans_turu(request.GET)
    veriler = _rapor_verileri(request.user, finans_turu, ay)
    buffer = BytesIO()
    font_adi = _pdf_font_adi()

    dosya_adi = f"finans-raporu-{finans_turu}-{ay}.pdf" if ay else f"finans-raporu-{finans_turu}.pdf"
    belge = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Finans Raporu",
    )

    stiller = getSampleStyleSheet()
    baslik_stili = ParagraphStyle(
        "Baslik",
        parent=stiller["Title"],
        fontName=font_adi,
        fontSize=20,
        alignment=TA_CENTER,
        spaceAfter=18,
    )
    normal_stili = ParagraphStyle(
        "NormalTurkce",
        parent=stiller["Normal"],
        fontName=font_adi,
        fontSize=10,
        leading=14,
    )
    sag_stili = ParagraphStyle(
        "SagTurkce",
        parent=normal_stili,
        alignment=TA_RIGHT,
    )

    pdf_icerigi = [
        Paragraph("Finans Raporu", baslik_stili),
        Paragraph(f"Rapor dönemi: {ay or 'Tüm kayıtlar'}", normal_stili),
        Spacer(1, 12),
    ]

    ozet_tablosu = Table([
        ["Başlık", "Tutar"],
        ["Toplam Gelir", f"{veriler['toplam_gelir']} TL"],
        ["Toplam Gider", f"{veriler['toplam_gider']} TL"],
        ["Kalan Bakiye", f"{veriler['bakiye']} TL"],
        ["Aylık Gelir", f"{veriler['aylik_gelir']} TL"],
        ["Aylık Gider", f"{veriler['aylik_gider']} TL"],
        ["Aylık Bakiye", f"{veriler['aylik_bakiye']} TL"],
    ], colWidths=[8 * cm, 6 * cm])
    ozet_tablosu.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_adi),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#343a40")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    pdf_icerigi.append(ozet_tablosu)
    pdf_icerigi.append(Spacer(1, 18))
    pdf_icerigi.append(Paragraph("Kategori Bazlı Giderler", normal_stili))
    pdf_icerigi.append(Spacer(1, 8))

    kategori_satirlari = [["Kategori", "Tutar"]]
    for kategori in veriler["kategori_detaylari"]:
        kategori_satirlari.append([
            Paragraph(escape(str(kategori["ad"])), normal_stili),
            Paragraph(f"{kategori['tutar']} TL", sag_stili),
        ])

    if len(kategori_satirlari) == 1:
        kategori_satirlari.append(["Kayıt bulunamadı", "0 TL"])

    kategori_tablosu = Table(kategori_satirlari, colWidths=[8 * cm, 6 * cm])
    kategori_tablosu.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_adi),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    pdf_icerigi.append(kategori_tablosu)

    belge.build(pdf_icerigi)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dosya_adi}"'
    buffer.close()
    return response

@login_required
def gelir_sil(request, id):
    gelir = get_object_or_404(Gelir, id=id, kullanici=request.user)
    finans_turu = gelir.finans_turu
    gelir.delete()
    return redirect(f"/gelir-ekle/?finans_turu={finans_turu}")


@login_required
def gider_sil(request, id):
    gider = get_object_or_404(Gider, id=id, kullanici=request.user)
    finans_turu = gider.finans_turu
    gider.delete()
    return redirect(f"/gider-ekle/?finans_turu={finans_turu}")

@login_required
def gider_duzenle(request, id):
    gider = get_object_or_404(Gider, id=id, kullanici=request.user)
    finans_turu = _secilen_finans_turu(request.POST) if request.method == "POST" else gider.finans_turu
    gider_kategorileri = Kategori.objects.filter(
        kullanici=request.user,
        finans_turu=finans_turu,
        tur=Kategori.GIDER,
    ).order_by("ad")
    hata = None

    if request.method == "POST":
        kategori_id = request.POST.get("kategori")
        kategori = None
        if kategori_id:
            kategori = Kategori.objects.filter(
                id=kategori_id,
                kullanici=request.user,
                finans_turu=finans_turu,
                tur=Kategori.GIDER,
            ).first()

        if not kategori:
            hata = "Gider kaydı için gider kategorisi seçmelisin."
        else:
            gider.tarih = request.POST["tarih"]
            gider.aciklama = request.POST["aciklama"]
            gider.tutar = request.POST["tutar"]
            gider.finans_turu = finans_turu
            gider.kategori = kategori.ad
            gider.save()

            return redirect(f"/gider-ekle/?finans_turu={finans_turu}")

    return render(request, "gider_duzenle.html", {
        "gider": gider,
        "gider_kategorileri": gider_kategorileri,
        "hata": hata,
        **_finans_turu_context(finans_turu),
    })

@login_required
def gelir_duzenle(request, id):
    gelir = get_object_or_404(Gelir, id=id, kullanici=request.user)
    finans_turu = _secilen_finans_turu(request.POST) if request.method == "POST" else gelir.finans_turu
    gelir_kategorileri = Kategori.objects.filter(
        kullanici=request.user,
        finans_turu=finans_turu,
        tur=Kategori.GELIR,
    ).order_by("ad")
    hata = None

    if request.method == "POST":
        kategori_id = request.POST.get("kategori")
        kategori = None
        if kategori_id:
            kategori = Kategori.objects.filter(
                id=kategori_id,
                kullanici=request.user,
                finans_turu=finans_turu,
                tur=Kategori.GELIR,
            ).first()

        if not kategori:
            hata = "Gelir kaydı için gelir kategorisi seçmelisin."
        else:
            gelir.tarih = request.POST["tarih"]
            gelir.aciklama = request.POST["aciklama"]
            gelir.tutar = request.POST["tutar"]
            gelir.finans_turu = finans_turu
            gelir.kategori = kategori.ad
            gelir.save()

            return redirect(f"/gelir-ekle/?finans_turu={finans_turu}")

    return render(request, "gelir_duzenle.html", {
        "gelir": gelir,
        "gelir_kategorileri": gelir_kategorileri,
        "hata": hata,
        **_finans_turu_context(finans_turu),
    })
