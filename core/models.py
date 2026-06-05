from django.db import models

class Gelir(models.Model):
    tarih = models.DateField()
    aciklama = models.CharField(max_length=200)
    tutar = models.DecimalField(max_digits=10, decimal_places=2)
    kategori = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.aciklama} - {self.tutar} TL"

class Gider(models.Model):
    tarih = models.DateField()
    aciklama = models.CharField(max_length=200)
    tutar = models.DecimalField(max_digits=10, decimal_places=2)
    kategori = models.CharField(max_length=100)

    def __str__(self):
        return self.aciklama