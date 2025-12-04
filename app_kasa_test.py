import streamlit as st
import pandas as pd
import io
from math import floor

st.set_page_config(page_title="Ürün Dağıtım Planı", layout="wide")
st.title("📦 Gelişmiş Ürün Dağıtım Planı")

# Yardımcı Fonksiyonlar
def normalize_columns(df):
    turkish_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    df.columns = df.columns.str.strip().str.lower().str.translate(turkish_map).str.replace(" ", "_")
    return df

def load_local_excel(path):
    try:
        return normalize_columns(pd.read_excel(path))
    except:
        return None

def load_file(file_path_or_buffer):
    """Excel veya CSV dosyası yükler"""
    try:
        if isinstance(file_path_or_buffer, str):
            # Dosya yolu ise uzantıya bak
            if file_path_or_buffer.endswith('.csv'):
                return normalize_columns(pd.read_csv(file_path_or_buffer))
            else:
                return normalize_columns(pd.read_excel(file_path_or_buffer))
        else:
            # Uploaded file ise
            try:
                # Önce Excel dene
                return normalize_columns(pd.read_excel(file_path_or_buffer))
            except:
                # CSV dene
                file_path_or_buffer.seek(0)  # Dosya başına dön
                return normalize_columns(pd.read_csv(file_path_or_buffer))
    except Exception as e:
        st.error(f"❌ Dosya yükleme hatası: {str(e)}")
        return None

def normalize_column(df, column):
    if column not in df.columns or df[column].nunique() == 0:
        return pd.Series([0]*len(df))
    col_min = df[column].min()
    col_max = df[column].max()
    return (df[column] - col_min) / (col_max - col_min) if (col_max - col_min) != 0 else df[column].apply(lambda x: 1 if x != 0 else 0)

def map_hangi_ilce_score(ilce):
    ilce_str = str(ilce).lower().strip()
    ilce_weights = {"muratpasa": 1.0, "muratpa": 1.0, "kepez": 0.7}
    return ilce_weights.get(ilce_str, 0)

def map_magaza_tipi_score(tipi):
    tipi_weights = {"large": 0.6, "spot": 0.4, "standart": 0.3}
    return tipi_weights.get(str(tipi).lower(), 0.3)

def unify_column_names(df):
    """Sütun isimlerini birleştirir (üst_mal_grubu, mal_grubu vb.)"""
    column_mapping = {
        'ust_mal_g': 'ust_mal_grubu',
        'ust_mal_grubu': 'ust_mal_grubu',
        'mal_grub': 'mal_grubu',
        'mal_grubu': 'mal_grubu',
        'urun_kodi': 'urun_kodu',
        'dagitilacak': 'dagitilacak_koli',
        '4_haftalik_satis': 'satis_4hafta',
        '2_haftalik_satis': 'satis_2hafta',
        'kasa_aktivitesi_ciro': 'ks_ciro'
    }
    
    for old_name, new_name in column_mapping.items():
        if old_name in df.columns:
            df.rename(columns={old_name: new_name}, inplace=True)
    
    return df

# GRUP SPOT - Mevcut Kodunuz (Değiştirilmedi)
def calculate_distribution_plan(tables, urun):
    grup_kodu_sutun = 'grup_' + str(urun["grup_kodu"])
    dagitim_verileri = tables["Mağaza Bilgi Tablosu"].copy()

    dagitim_verileri["urun_kodu"] = urun["urun_kodu"]
    dagitim_verileri["urun_adi"] = urun["urun_adi"]
    dagitim_verileri["urun_grubu"] = urun["urun_grubu"]
    dagitim_verileri["ust_mal_grubu"] = urun["ust_mal_grubu"]
    dagitim_verileri["depolama_kosulu"] = urun["depolama_kosulu"]

    merge_operations = [
        (tables["Ürün Grubu Ciro Tablosu"], ["magaza_kodu", "urun_grubu"], ["urun_grubu_ciro"]),
        (tables["Üss Mal Grubu Ciro Tablosu"], ["magaza_kodu", "ust_mal_grubu"], ["ust_mal_grubu_ciro"]),
        (tables["Stok Satış Tablosu"], ["magaza_kodu", "urun_kodu"], ["stok", "satis"])
    ]

    if urun["depolama_kosulu"] not in ["Soğuk(+4)", "Donuk(-18)"]:
        merge_operations.append(
            (tables["Raf Sepet Bilgi Tablosu"], ["magaza_kodu"], ["raf_sayisi", grup_kodu_sutun])
        )

    for table, on_columns, columns in merge_operations:
        dagitim_verileri = dagitim_verileri.merge(
            table[on_columns + columns],
            on=on_columns,
            how="left"
        )

    if urun["depolama_kosulu"] not in ["Soğuk(+4)", "Donuk(-18)"]:
        dagitim_verileri.rename(columns={grup_kodu_sutun: "raf_arasi_sayisi"}, inplace=True)
        dagitim_verileri["raf_arasi_sayisi"] = pd.to_numeric(dagitim_verileri["raf_arasi_sayisi"], errors='coerce')
    else:
        dagitim_verileri["raf_sayisi"] = 0
        dagitim_verileri["raf_arasi_sayisi"] = 0

    for col in ["stok", "satis", "urun_grubu_ciro", "ust_mal_grubu_ciro"]:
        dagitim_verileri[col] = dagitim_verileri[col].fillna(0)

    dagitim_verileri["stok"] = dagitim_verileri["stok"].clip(lower=0)
    dagitim_verileri["stok_orani"] = dagitim_verileri["stok"] / (dagitim_verileri["stok"] + dagitim_verileri["satis"] + 1e-9)
    dagitim_verileri["satis_hizi"] = dagitim_verileri["satis"] / max(dagitim_verileri["satis"].sum(), 1)

    dagitim_verileri["hangi_ilce_score"] = dagitim_verileri["hangi_ilce"].apply(map_hangi_ilce_score)
    dagitim_verileri["magaza_tipi_score"] = dagitim_verileri["magaza_tipi"].apply(map_magaza_tipi_score)

    if urun["yeni_mi"] == "yeni":
        normalized_columns = {
            "urun_grubu_ciro": 0.24,
            "ust_mal_grubu_ciro": 0.10,
            "raf_sayisi": 0.01,
            "raf_arasi_sayisi": 0.26,
            "gs_ciro": 0.21,
            "ortalama_ciro": 0.25,
            "hangi_ilce_score": 0.00,
            "magaza_tipi_score": 0.01
        }
    else:
        normalized_columns = {
            "urun_grubu_ciro": 0.16,
            "ust_mal_grubu_ciro": 0.14,
            "raf_sayisi": 0.01,
            "raf_arasi_sayisi": 0.20,
            "gs_ciro": 0.12,
            "ortalama_ciro": 0.18,
            "hangi_ilce_score": 0.00,
            "magaza_tipi_score": 0.01
        }

    total_weight = sum(normalized_columns.values())
    normalized_columns = {k: v / total_weight for k, v in normalized_columns.items()}

    skor = pd.Series([0]*len(dagitim_verileri))
    for col, weight in normalized_columns.items():
        skor += normalize_column(dagitim_verileri, col) * weight

    if urun["yeni_mi"] == "eski":
        skor += dagitim_verileri["satis_hizi"] * (0.90 / total_weight)
        skor -= dagitim_verileri["stok_orani"] * (0.45 / total_weight)

    dagitim_verileri["skor"] = skor.clip(lower=0)

    total = urun["dagitilacak_koli"]
    skor_toplam = dagitim_verileri["skor"].sum()

    if skor_toplam == 0 or pd.isna(skor_toplam):
        dagitim_verileri["dagitilan_koli"] = 0
    else:
        dagitim_verileri["dagitilan_koli"] = (dagitim_verileri["skor"] / skor_toplam * total).fillna(0).apply(floor)

    fark = total - dagitim_verileri["dagitilan_koli"].sum()
    if fark > 0:
        dagitim_verileri["kalan"] = (dagitim_verileri["skor"] / skor_toplam * total) % 1
        top_magazalar = dagitim_verileri.nlargest(fark, "kalan").index
        dagitim_verileri.loc[top_magazalar, "dagitilan_koli"] += 1

    if "kalan" not in dagitim_verileri.columns:
        dagitim_verileri["kalan"] = 0

    column_order = [
        "magaza_kodu", "magaza_adi", "urun_kodu", "urun_adi", "dagitilan_koli", "skor", "stok", "satis",
        "urun_grubu", "ust_mal_grubu", "urun_grubu_ciro", "ust_mal_grubu_ciro", "raf_sayisi", "raf_arasi_sayisi",
        "magaza_tipi", "hangi_ilce", "gs_ciro", "ortalama_ciro", "stok_orani", "satis_hizi", "hangi_ilce_score",
        "magaza_tipi_score", "kalan", "depolama_kosulu"
    ]
    return dagitim_verileri[column_order]

# KASA AKTİVİTESİ - Yeni Fonksiyon
def calculate_kasa_aktivitesi(tables, urun):
    """Kasa Aktivitesi dağıtım planı hesaplama"""
    
    # Mağaza bilgilerini al
    dagitim_verileri = tables["KS Mağaza Bilgi"].copy()
    
    # Ürün bilgilerini ekle
    dagitim_verileri["urun_kodu"] = urun["urun_kodu"]
    dagitim_verileri["urun_adi"] = urun.get("urun_adi", "")
    dagitim_verileri["ust_mal_grubu"] = urun.get("ust_mal_grubu", "")
    dagitim_verileri["mal_grubu"] = urun.get("mal_grubu", urun.get("urun_grubu", ""))
    
    # Stok-Satış tablosunu birleştir
    if "KS Stok Satış" in tables and tables["KS Stok Satış"] is not None:
        # İhtiyacımız olan sütunlar
        required_cols = ["magaza_kodu", "urun_kodu", "stok", "satis_4hafta"]
        
        # 4 hafta sonunda stok sütunu var mı kontrol et
        stok_cols = [col for col in tables["KS Stok Satış"].columns if "4_hafta" in col and "stok" in col]
        if stok_cols:
            required_cols.append(stok_cols[0])  # İlk eşleşeni al
            stok_4hafta_col = stok_cols[0]
        else:
            # Yoksa sütun ismine göre tahmin et
            possible_names = ["4_hafta_sonunda_stok", "stok_4hafta_sonunda", "stok_4_hafta"]
            for name in possible_names:
                if name in tables["KS Stok Satış"].columns:
                    required_cols.append(name)
                    stok_4hafta_col = name
                    break
            else:
                stok_4hafta_col = None
        
        available_cols = [col for col in required_cols if col in tables["KS Stok Satış"].columns]
        stok_satis = tables["KS Stok Satış"][available_cols].copy()
        
        # Ürün kodu eşleştirme - tam eşleşme dene
        dagitim_verileri = dagitim_verileri.merge(
            stok_satis,
            on=["magaza_kodu", "urun_kodu"],
            how="left"
        )
        
        # Eğer hiç eşleşme yoksa, ürün kodunun ilk 8 hanesine göre eşleştir
        if dagitim_verileri["stok"].isna().all():
            st.warning("⚠️ Ürün kodu tam eşleşmedi, alternatif eşleştirme deneniyor...")
            cols_to_drop = ["stok", "satis_4hafta"]
            if stok_4hafta_col:
                cols_to_drop.append(stok_4hafta_col)
            dagitim_verileri = dagitim_verileri.drop(columns=cols_to_drop, errors='ignore')
            
            # Ürün kodunu string'e çevir ve ilk 8 haneyi al
            dagitim_verileri["urun_prefix"] = dagitim_verileri["urun_kodu"].astype(str).str[:8]
            stok_satis["urun_prefix"] = stok_satis["urun_kodu"].astype(str).str[:8]
            
            # Prefix'e göre grup oluştur ve topla
            agg_dict = {"stok": "sum", "satis_4hafta": "sum"}
            if stok_4hafta_col and stok_4hafta_col in stok_satis.columns:
                agg_dict[stok_4hafta_col] = "sum"
            
            stok_grouped = stok_satis.groupby(["magaza_kodu", "urun_prefix"]).agg(agg_dict).reset_index()
            
            dagitim_verileri = dagitim_verileri.merge(
                stok_grouped,
                on=["magaza_kodu", "urun_prefix"],
                how="left"
            )
            
            dagitim_verileri.drop(columns=["urun_prefix"], inplace=True)
        
        # 4 hafta sonunda stok sütununu standart isme çevir
        if stok_4hafta_col and stok_4hafta_col in dagitim_verileri.columns:
            dagitim_verileri.rename(columns={stok_4hafta_col: "stok_4hafta_sonunda"}, inplace=True)
    
    # KS Ciro tablosunu birleştir
    if "KS Ciro" in tables and tables["KS Ciro"] is not None:
        # ks_ciro sütunu var mı kontrol et
        ciro_col = None
        if "ks_ciro" in tables["KS Ciro"].columns:
            ciro_col = "ks_ciro"
        elif "kasa_aktivitesi_ciro" in tables["KS Ciro"].columns:
            ciro_col = "kasa_aktivitesi_ciro"
        
        if ciro_col:
            ks_ciro = tables["KS Ciro"][["magaza_kodu", ciro_col]].copy()
            ks_ciro.rename(columns={ciro_col: "ks_ciro"}, inplace=True)
            dagitim_verileri = dagitim_verileri.merge(
                ks_ciro,
                on="magaza_kodu",
                how="left"
            )
    
    # Yeni ürün ise mal grubu cirolarını ekle
    if urun.get("yeni_mi", "eski") == "yeni":
        # Mal Grubu Ciro
        if "KS Mal Grubu" in tables and tables["KS Mal Grubu"] is not None:
            mal_grubu_ciro = tables["KS Mal Grubu"][["magaza_kodu", "mal_grubu", "mal_grubu_ciro"]].copy()
            dagitim_verileri = dagitim_verileri.merge(
                mal_grubu_ciro,
                on=["magaza_kodu", "mal_grubu"],
                how="left"
            )
        
        # Üst Mal Grubu Ciro
        if "KS Üst Mal Grubu" in tables and tables["KS Üst Mal Grubu"] is not None:
            ust_mal_ciro = tables["KS Üst Mal Grubu"][["magaza_kodu", "ust_mal_grubu", "ust_mal_grubu_ciro"]].copy()
            dagitim_verileri = dagitim_verileri.merge(
                ust_mal_ciro,
                on=["magaza_kodu", "ust_mal_grubu"],
                how="left"
            )
    
    # Eksik değerleri doldur
    for col in ["stok", "satis_4hafta", "stok_4hafta_sonunda", "ks_ciro", "mal_grubu_ciro", "ust_mal_grubu_ciro"]:
        if col in dagitim_verileri.columns:
            dagitim_verileri[col] = dagitim_verileri[col].fillna(0)
    
    # Negatif stokları 0'a çevir
    dagitim_verileri["stok"] = dagitim_verileri["stok"].clip(lower=0)
    if "stok_4hafta_sonunda" in dagitim_verileri.columns:
        dagitim_verileri["stok_4hafta_sonunda"] = dagitim_verileri["stok_4hafta_sonunda"].clip(lower=0)
    
    # ARA DÖNEM SATIŞ HESAPLAMA (YENİ!)
    if "stok_4hafta_sonunda" in dagitim_verileri.columns:
        dagitim_verileri["ara_satis"] = (
            dagitim_verileri["stok_4hafta_sonunda"] - dagitim_verileri["stok"]
        ).clip(lower=0)
    else:
        dagitim_verileri["ara_satis"] = 0
    
    # TOPLAM SATIŞ GÜCÜ (4 haftalık + ara satış × 0.5)
    dagitim_verileri["toplam_satis_gucu"] = (
        dagitim_verileri["satis_4hafta"] + (dagitim_verileri["ara_satis"] * 0.5)
    )
    
    # Stok oranı hesapla (mevcut formül)
    dagitim_verileri["stok_orani"] = dagitim_verileri["stok"] / (
        dagitim_verileri["stok"] + dagitim_verileri["satis_4hafta"] + 1e-9
    )
    
    # İlçe skoru
    dagitim_verileri["hangi_ilce_score"] = dagitim_verileri["hangi_ilce"].apply(map_hangi_ilce_score)
    
    # SKOR HESAPLAMA
    if urun.get("yeni_mi", "eski") == "yeni":
        # Yeni ürün
        weights = {
            "toplam_satis_gucu": 0.50,  # Toplam satış gücü (4 hafta + ara)
            "ks_ciro": 0.25,
            "ust_mal_grubu_ciro": 0.05,
            "mal_grubu_ciro": 0.10,
            "hangi_ilce_score": 0.05
        }
    else:
        # Eski ürün
        weights = {
            "toplam_satis_gucu": 0.50,  # Toplam satış gücü (4 hafta + ara)
            "ks_ciro": 0.25,
            "hangi_ilce_score": 0.05
        }
    
    # Ağırlıkları normalize et
    total_weight = sum(weights.values())
    weights = {k: v / total_weight for k, v in weights.items()}
    
    # Skor hesapla
    skor = pd.Series([0.0]*len(dagitim_verileri), index=dagitim_verileri.index)
    for col, weight in weights.items():
        if col in dagitim_verileri.columns:
            skor += normalize_column(dagitim_verileri, col) * weight
    
    # STOK TÜKENME BONUSU (+%15)
    stok_tukendi = (dagitim_verileri["stok"] == 0) & (dagitim_verileri["ara_satis"] > 0)
    dagitim_verileri["stok_tukendi_bonus"] = stok_tukendi.astype(float) * 0.15
    skor += dagitim_verileri["stok_tukendi_bonus"]
    
    # DURGUNLUK CEZASI (-%10)
    durgun = (dagitim_verileri["ara_satis"] == 0) & (dagitim_verileri["stok"] > 0)
    if "stok_4hafta_sonunda" in dagitim_verileri.columns:
        dagitim_verileri["birikim_orani"] = dagitim_verileri.apply(
            lambda x: (x["stok"] / x["stok_4hafta_sonunda"]) if x["stok_4hafta_sonunda"] > 0 else 0,
            axis=1
        )
    else:
        dagitim_verileri["birikim_orani"] = 0
    
    dagitim_verileri["durgunluk_cezasi"] = (
        durgun.astype(float) * dagitim_verileri["birikim_orani"] * 0.10
    )
    skor -= dagitim_verileri["durgunluk_cezasi"]
    
    # Stok oranı cezası (mevcut - %30)
    skor -= dagitim_verileri["stok_orani"] * 0.30
    
    dagitim_verileri["skor"] = skor.clip(lower=0)
    
    # DAĞITIM HESAPLAMA
    total_koli = urun["dagitilacak_koli"]
    magaza_sayisi = len(dagitim_verileri)
    minimum_koli = 2
    
    # Minimum dağıtım
    minimum_total = magaza_sayisi * minimum_koli
    
    if total_koli < minimum_total:
        st.warning(f"⚠️ Uyarı: Toplam koli ({total_koli}) tüm mağazalara minimum {minimum_koli} koli dağıtmak için yetersiz!")
        dagitim_verileri["dagitilan_koli"] = 0
        return dagitim_verileri
    
    # Her mağazaya minimum 2 koli
    dagitim_verileri["dagitilan_koli"] = minimum_koli
    
    # Kalan kolileri skora göre dağıt
    kalan_koli = total_koli - minimum_total
    
    if kalan_koli > 0:
        skor_toplam = dagitim_verileri["skor"].sum()
        
        if skor_toplam > 0:
            dagitim_verileri["ek_koli"] = (dagitim_verileri["skor"] / skor_toplam * kalan_koli).fillna(0).apply(floor)
            dagitim_verileri["dagitilan_koli"] += dagitim_verileri["ek_koli"]
            
            # Kalan kesirli kolileri dağıt
            fark = kalan_koli - dagitim_verileri["ek_koli"].sum()
            if fark > 0:
                dagitim_verileri["kesir"] = (dagitim_verileri["skor"] / skor_toplam * kalan_koli) % 1
                top_magazalar = dagitim_verileri.nlargest(int(fark), "kesir").index
                dagitim_verileri.loc[top_magazalar, "dagitilan_koli"] += 1
    
    # Sütun sıralaması
    column_order = [
        "magaza_kodu", "magaza_adi", "urun_kodu", "urun_adi", "dagitilan_koli", "skor",
        "stok", "satis_4hafta", "ara_satis", "toplam_satis_gucu", "ks_ciro", 
        "hangi_ilce", "hangi_ilce_score", "stok_orani", "stok_tukendi_bonus", 
        "durgunluk_cezasi", "birikim_orani"
    ]
    
    if urun.get("yeni_mi", "eski") == "yeni":
        column_order.extend(["mal_grubu", "mal_grubu_ciro", "ust_mal_grubu", "ust_mal_grubu_ciro"])
    
    if "stok_4hafta_sonunda" in dagitim_verileri.columns:
        column_order.append("stok_4hafta_sonunda")
    
    available_columns = [col for col in column_order if col in dagitim_verileri.columns]
    
    return dagitim_verileri[available_columns]

# ANA UYGULAMA
st.markdown("---")

# Kategori Seçimi
kategori = st.selectbox(
    "📂 Kategori",
    ["Grup Spot", "Kasa Aktivitesi"],
    help="Hangi kategori için dağıtım planı oluşturacaksınız?"
)

st.markdown("---")

# Dosya Yükleme Alanları
if kategori == "Kasa Aktivitesi":
    st.subheader("📥 Dosya Yükleme")
    
    col1, col2 = st.columns(2)
    
    with col1:
        urun_bilgisi_dosyasi = st.file_uploader(
            "1️⃣ Ürün Bilgisi",
            type=["xlsx"],
            key="urun_bilgi",
            help="Dağıtılacak ürünlerin listesi"
        )
    
    with col2:
        stok_satis_file = st.file_uploader(
            "2️⃣ Stok-Satış Tablosu",
            type=["xlsx"],
            key="stok_satis",
            help="Güncel stok ve satış verileri (ZORUNLU)"
        )
else:  # Grup Spot
    st.subheader("📥 Dosya Yükleme")
    
    col1, col2 = st.columns(2)
    
    with col1:
        urun_bilgisi_dosyasi = st.file_uploader(
            "1️⃣ Ürün Bilgisi",
            type=["xlsx"],
            key="urun_bilgi",
            help="Dağıtılacak ürünlerin listesi"
        )
    
    with col2:
        stok_satis_file = st.file_uploader(
            "2️⃣ Güncel Stok-Satış (Opsiyonel)",
            type=["xlsx"],
            key="stok_satis",
            help="Varsa güncel stok-satış verilerini yükleyin"
        )

# Tablo yükleme
if kategori == "Grup Spot":
    tables = {
        "Ürün Grubu Ciro Tablosu": load_local_excel("urun_grubu_ciro_tablosu.xlsx"),
        "Üss Mal Grubu Ciro Tablosu": load_local_excel("ust_mal_grubu_ciro_tablosu.xlsx"),
        "Raf Sepet Bilgi Tablosu": load_local_excel("raf_sepet_bilgi_tablosu.xlsx"),
        "Mağaza Bilgi Tablosu": load_local_excel("magaza_bilgi_tablosu.xlsx"),
        "Stok Satış Tablosu": normalize_columns(pd.read_excel(stok_satis_file)) if stok_satis_file else load_local_excel("stok_satis_tablosu.xlsx")
    }
else:  # Kasa Aktivitesi
    # Kasa Aktivitesi için stok-satış dosyası ZORUNLU
    if not stok_satis_file:
        st.warning("⚠️ Kasa Aktivitesi için **Stok-Satış Tablosu** zorunludur. Lütfen dosyayı yükleyin.")
        st.stop()
    
    tables = {
        "KS Mağaza Bilgi": load_local_excel("magaza_bilgi_tablosu.xlsx"),
        "KS Ciro": load_local_excel("ks_ciro.xlsx"),
        "KS Mal Grubu": load_local_excel("ks_mal.xlsx"),
        "KS Üst Mal Grubu": load_local_excel("ks_ust_mal.xlsx"),
        "KS Stok Satış": normalize_columns(pd.read_excel(stok_satis_file))
    }
    
    # Sütun isimlerini birleştir
    for key in tables:
        if tables[key] is not None:
            tables[key] = unify_column_names(tables[key])

# Eksik tabloları kontrol et (sadece None olanları say)
missing_tables = [name for name, table in tables.items() if table is None]
if missing_tables:
    st.error(f"❌ Sunucuda eksik tablolar: {', '.join(missing_tables)}")
    st.info("💡 Bu tablolar sunucuda olmalı. Yöneticinizle iletişime geçin.")
else:
    st.success(f"✅ Sistem tabloları hazır")
    
    # Debug: Tablo bilgilerini göster
    with st.expander("🔍 Yüklenen Tablo Detayları (Debug)"):
        for name, table in tables.items():
            if table is not None:
                st.write(f"**{name}:** {len(table)} satır, Sütunlar: {', '.join(table.columns.tolist()[:10])}")
            else:
                st.write(f"**{name}:** ❌ Yüklenemedi")

if urun_bilgisi_dosyasi and not missing_tables:
    urun_bilgisi = normalize_columns(pd.read_excel(urun_bilgisi_dosyasi))
    urun_bilgisi = unify_column_names(urun_bilgisi)
    
    st.info(f"📊 {len(urun_bilgisi)} ürün yüklendi")
    
    with st.expander("👁️ Ürün Bilgisi Önizleme"):
        st.dataframe(urun_bilgisi.head(10))
    
    if st.button("🚀 Dağıtım Planını Hesapla", type="primary"):
        with st.spinner("🔄 Dağıtım planı hesaplanıyor..."):
            dagitim_planlari = []
            
            progress_bar = st.progress(0)
            
            for idx, (_, urun) in enumerate(urun_bilgisi.iterrows()):
                try:
                    if kategori == "Grup Spot":
                        plan = calculate_distribution_plan(tables, urun)
                    else:  # Kasa Aktivitesi
                        plan = calculate_kasa_aktivitesi(tables, urun)
                    
                    if plan is not None and not plan.empty:
                        dagitim_planlari.append(plan)
                    else:
                        st.warning(f"⚠️ Ürün {urun.get('urun_kodu', 'bilinmeyen')} için plan oluşturulamadı")
                        
                except Exception as e:
                    st.error(f"❌ Hata (Ürün {idx+1}): {str(e)}")
                    st.write("**Ürün Bilgisi:**", urun.to_dict())
                
                progress_bar.progress((idx + 1) / len(urun_bilgisi))
            
            progress_bar.empty()
            
            if not dagitim_planlari:
                st.error("❌ Hiçbir dağıtım planı oluşturulamadı! Lütfen yukarıdaki hataları kontrol edin.")
                st.stop()
            
            birlesmis = pd.concat(dagitim_planlari, ignore_index=True)
            
            # İstatistikler
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📍 Toplam Mağaza", birlesmis["magaza_kodu"].nunique())
            with col2:
                st.metric("📦 Toplam Ürün", birlesmis["urun_kodu"].nunique())
            with col3:
                st.metric("🎁 Toplam Koli", int(birlesmis["dagitilan_koli"].sum()))
            
            # Önizleme
            with st.expander("📊 Sonuç Önizleme", expanded=True):
                st.dataframe(birlesmis.head(50))
            
            # Excel indirme
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                birlesmis.to_excel(writer, index=False, sheet_name='Dağıtım Planı')
            
            output.seek(0)  # Dosya başına dön
            
            st.download_button(
                label="📥 Excel Dosyasını İndir (.xlsx)",
                data=output.getvalue(),
                file_name=f"dagitim_plani_{kategori.lower().replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
            st.success("✅ Dağıtım planı başarıyla oluşturuldu!")
else:
    st.info("👆 Başlamak için lütfen Ürün Bilgisi dosyasını yükleyin.")
