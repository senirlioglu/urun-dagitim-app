# Arşiv — bu repo artık kullanılmıyor

Bu repo, Grup Spot dağıtımının **ilk prototipiydi** (`deneme12.py`, tek dosya).
Mantığı `senirlioglu/Spot` repo'suna taşındı ve orada geliştirilmeye devam etti;
buradaki kopya Mart 2026'dan beri güncellenmiyordu. Karışıklığa yol açmaması için
kod ve veri dosyaları kaldırıldı.

## Nereye taşındı

| Buradaki | Gittiği yer |
|----------|-------------|
| `deneme12.py` (ağırlıklı skor + floor/largest-remainder dağıtım) | `Spot/grup_spot.py` → `run_grup_spot_pipeline()` |
| `raf_sepet_bilgi_tablosu.xlsx`, `magaza_bilgi_tablosu.xlsx`, `urun_grubu_ciro_tablosu.xlsx`, `ust_mal_grubu_ciro_tablosu.xlsx`, `stok_satis_tablosu.xlsx` | `Spot/data/` |
| `urun_bilgisi1.xlsx` (örnek girdi) | Karşılığı yok — yalnızca git geçmişinde |

`Spot`'taki sürüm prototipten farklı olarak: satış verisini Google Drive'daki
parquet'ten okur, toplam satış yerine **aylık velocity** kullanır (stok bitince
satış durduğu için erken tükenen mağaza cezalanmasın diye) ve mağaza bazlı
minimum koli garantisi (`GRUP_SPOT_MIN_KOLI`) uygular.

## Dikkat: veri dosyaları birebir aynı değildi

Silinen 5 referans tablosundan 3'ü `Spot/data/` içindekilerle birebir aynıydı
(`stok_satis_tablosu`, `urun_grubu_ciro_tablosu`, `ust_mal_grubu_ciro_tablosu`).
`raf_sepet_bilgi_tablosu.xlsx` ve `magaza_bilgi_tablosu.xlsx` ise farklıydı —
buradakiler daha eski anlık görüntülerdi. Güncel olanlar `Spot/data/` altındakiler.

## Eski hâline erişim

Hiçbir şey kaybolmadı, tamamı git geçmişinde:

```
git log --all -- deneme12.py
git show <commit>^:deneme12.py
git checkout <commit>^ -- urun_bilgisi1.xlsx   # tek dosyayı geri almak için
```
