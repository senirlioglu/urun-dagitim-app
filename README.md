# Urun Dagitim Plani (Urun Dagitim Uygulamasi)

Perakende magazalara urun dagitimini optimize eden, Streamlit tabanli bir web uygulamasidir. Coklu faktor analizi ve agirlikli puanlama algoritmasi kullanarak her magazaya ne kadar urun gonderilecegini hesaplar.

## Teknoloji Yigini

- **Python 3.11**
- **Streamlit** - Web arayuzu
- **Pandas** - Veri isleme ve analiz
- **openpyxl / xlsxwriter** - Excel dosyasi okuma/yazma

## Kurulum

```bash
pip install -r requirements.txt
```

## Calistirma

```bash
streamlit run deneme12.py
```

Uygulama varsayilan olarak `http://localhost:8501` adresinde acilir.

## Uygulama Nasil Calisir

### Genel Akis

```
Kullanici urun bilgisi yukler (Excel)
         |
         v
5 referans tablo diskten okunur
         |
         v
Her urun icin dagitim hesaplanir
         |
         v
Sonuclar birlestirilerek Excel ciktisi olusturulur
         |
         v
Kullanici sonucu indirir
```

### Veri Tablolari

Uygulama 6 Excel dosyasindan veri okur:

| Dosya | Aciklama | Kayit Sayisi |
|-------|----------|--------------|
| `magaza_bilgi_tablosu.xlsx` | Magaza bilgileri (kod, ad, tip, ilce, ciro) | ~204 magaza |
| `raf_sepet_bilgi_tablosu.xlsx` | Raf ve sepet bilgileri (raf sayisi, grup bazli alanlar) | ~24.500 kayit |
| `stok_satis_tablosu.xlsx` | Urun bazli stok ve satis verileri | ~5.200 kayit |
| `urun_bilgisi1.xlsx` | Dagitilacak urun listesi (kullanici yukler) | Degisken |
| `urun_grubu_ciro_tablosu.xlsx` | Urun grubu bazinda magaza cirolari | ~51.300 kayit |
| `ust_mal_grubu_ciro_tablosu.xlsx` | Ust mal grubu bazinda magaza cirolari | ~24.600 kayit |

### Urun Bilgisi Dosyasi (Girdi)

Kullanicinin yukledigi Excel dosyasi su sutunlari icermelidir:

| Sutun | Aciklama | Ornek Deger |
|-------|----------|-------------|
| `urun_kodu` | Urun kodu | 1001 |
| `grup_kodu` | Urun grup kodu | 15 |
| `urun_adi` | Urun adi | "Helva 500g" |
| `urun_grubu` | Urun grubu | "Helva" |
| `ust_mal_grubu` | Ust mal grubu | "Gida" |
| `yeni_mi` | Yeni urun mu? | "yeni" veya "eski" |
| `depolama_kosulu` | Depolama kosulu | "Gida", "Gida Disi", "Soguk(+4)", "Donuk(-18)" |
| `dagitilacak_koli` | Dagitilacak toplam koli sayisi | 150 |
| `fiyat` | Urun fiyati | 45.90 |

## Dagitim Algoritmasi

### 1. Veri Hazirlama

Her urun icin:
1. 204 magazanin temel bilgileri alinir
2. Urun bilgileri tum satirlara eklenir
3. Urun grubu ciro tablosuyla birlestirilir (`magaza_kodu` + `urun_grubu`)
4. Ust mal grubu ciro tablosuyla birlestirilir (`magaza_kodu` + `ust_mal_grubu`)
5. Stok-satis tablosuyla birlestirilir (`magaza_kodu` + `urun_kodu`)
6. Soguk/donuk urunler haricinde raf/sepet bilgisi eklenir

### 2. Ara Metrikler

- **Stok Orani**: `stok / (stok + satis)` - Mevcut stok yogunlugu
- **Satis Hizi**: `satis / toplam_satis` - Magazanin satis performansi
- **Ilce Puani**: Muratpasa = 1.0, Kepez = 0.7, Diger = 0
- **Magaza Tipi Puani**: Large = 0.6, Spot = 0.4, Standart = 0.3

### 3. Agirlikli Puanlama

Urunun yeni veya mevcut olmasina gore farkli agirliklar uygulanir:

| Faktor | Yeni Urun | Mevcut Urun |
|--------|-----------|-------------|
| Urun Grubu Ciro | %24 | %16 |
| Ust Mal Grubu Ciro | %10 | %14 |
| Raf Sayisi | %1 | %1 |
| Raf Arasi Sayisi | %26 | %20 |
| Genel Magaza Ciro | %21 | %12 |
| Ortalama Ciro | %25 | %18 |
| Ilce Puani | %0 | %0 |
| Magaza Tipi Puani | %1 | %1 |

Mevcut urunler icin ek olarak:
- **Satis Hizi**: +%90 bonus (yuksek satisli magazalar odulendirilir)
- **Stok Orani**: -%45 ceza (cok stoklu magazalar cezalandirilir)

### 4. Normalizasyon

Her faktor min-max normalizasyonu ile 0-1 araligina olceklenir:

```
normalize(x) = (x - min) / (max - min)
```

Tum degerler ayni ise ve sifir degilse 1, sifirse 0 olarak ayarlanir.

### 5. Koli Dagitimi

1. Her magazanin skoru toplam skora oranlanarak pay hesaplanir
2. `dagitilan_koli = floor(skor / toplam_skor * toplam_koli)`
3. Kalan koliler, en yuksek ondalik kisma sahip magazalara birer birer dagitilir

**Ornek**: 100 koli dagitilacaksa ve A magazasi %15.7 puan alirsa:
- Ilk dagitim: 15 koli (floor)
- 0.7 kismi, kalan dagitim siralamasinda degerlendirilir

## Ozel Durumlar

- **Soguk (+4) ve Donuk (-18) Urunler**: Raf/sepet verileri kullanilmaz, bu degerler 0 olarak ayarlanir
- **Stok Orani**: Negatif stok degerleri 0'a cekilir (`clip(lower=0)`)
- **Eksik Veri**: Birlestime (merge) sonrasi eksik degerler 0 ile doldurulur
- **Sifir Skor**: Toplam skor 0 ise hicbir magazaya dagitim yapilmaz

## Cikti

Uygulama asagidaki sutunlari iceren bir Excel dosyasi uretir:

| Sutun | Aciklama |
|-------|----------|
| `magaza_kodu` | Magaza kodu |
| `magaza_adi` | Magaza adi |
| `urun_kodu` | Urun kodu |
| `urun_adi` | Urun adi |
| `dagitilan_koli` | Dagitilan koli sayisi |
| `skor` | Hesaplanan dagitim skoru |
| `stok` | Mevcut stok |
| `satis` | Satis miktari |
| `urun_grubu` | Urun grubu |
| `ust_mal_grubu` | Ust mal grubu |
| `urun_grubu_ciro` | Urun grubu cirosu |
| `ust_mal_grubu_ciro` | Ust mal grubu cirosu |
| `raf_sayisi` | Raf sayisi |
| `raf_arasi_sayisi` | Raf arasi sayisi |
| `magaza_tipi` | Magaza tipi |
| `hangi_ilce` | Ilce bilgisi |
| `gs_ciro` | Genel magaza cirosu |
| `ortalama_ciro` | Ortalama ciro |
| `stok_orani` | Hesaplanan stok orani |
| `satis_hizi` | Hesaplanan satis hizi |
| `hangi_ilce_score` | Ilce puani |
| `magaza_tipi_score` | Magaza tipi puani |
| `kalan` | Ondalik kalan deger |
| `depolama_kosulu` | Depolama kosulu |

## Proje Yapisi

```
urun-dagitim-app/
├── deneme12.py                        # Ana uygulama dosyasi
├── requirements.txt                   # Python bagimliliklari
├── README.md                          # Bu dosya
├── .devcontainer/
│   └── devcontainer.json              # VS Code Dev Container ayarlari
├── magaza_bilgi_tablosu.xlsx          # Magaza bilgileri
├── raf_sepet_bilgi_tablosu.xlsx       # Raf/sepet bilgileri
├── stok_satis_tablosu.xlsx            # Stok-satis verileri
├── urun_bilgisi1.xlsx                 # Ornek urun bilgisi
├── urun_grubu_ciro_tablosu.xlsx       # Urun grubu cirolari
└── ust_mal_grubu_ciro_tablosu.xlsx    # Ust mal grubu cirolari
```
