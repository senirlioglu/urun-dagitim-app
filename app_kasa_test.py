import streamlit as st
import pandas as pd
import io
from math import floor

st.set_page_config(page_title="Ürün Dağıtım Planı", layout="wide")
st.title("📦 Ürün Dağıtım Planı")

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

def normalize_column(df, column):
    if column not in df.columns or df[column].nunique() == 0:
        return pd.Series([0]*len(df), index=df.index)
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
    """Sütun isimlerini birleştirir"""
    column_mapping = {
        'ust_mal_g': 'ust_mal_grubu',
        'mal_grub': 'mal_grubu',
        'urun_kodi': 'urun_kodu',
        'dagitilacak': 'dagitilacak_koli',
        '4_haftalik_satis': 'satis_4hafta',
        '2_haftalik_satis': 'satis_2hafta',
        'kasa_aktivitesi_ciro': 'ks_ciro',
        '4_hafta_sonunda_stok': 'stok_4hafta_sonunda',
        'guncel_stok': 'stok',  # ÖNEMLİ: guncel_stok → stok
        'depolama': 'depolama_kosulu'
    }
    
    for old_name, new_name in column_mapping.items():
        if old_name in df.columns:
            df.rename(columns={old_name: new_name}, inplace=True)
    
    return df

# GRUP SPOT - Mevcut Kodunuz
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

    skor = pd.Series([0]*len(dagitim_verileri), index=dagitim_verileri.index)
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
        top_magazalar = dagitim_verileri.nlargest(int(fark), "kalan").index
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

# KASA AKTİVİTESİ
def calculate_kasa_aktivitesi(tables, urun):
    """Kasa Aktivitesi dağıtım planı"""
    
    dagitim_verileri = tables["KS Mağaza Bilgi"].copy()
    
    # Ürün bilgileri
    dagitim_verileri["urun_kodu"] = urun["urun_kodu"]
    dagitim_verileri["urun_adi"] = urun.get("urun_adi", "")
    dagitim_verileri["ust_mal_grubu"] = urun.get("ust_mal_grubu", "")
    dagitim_verileri["mal_grubu"] = urun.get("mal_grubu", "")
    
    # Stok-Satış birleştir
    if "KS Stok Satış" in tables and tables["KS Stok Satış"] is not None:
        required_cols = ["magaza_kodu", "urun_kodu", "stok", "satis_4hafta", "stok_4hafta_sonunda"]
        available_cols = [col for col in required_cols if col in tables["KS Stok Satış"].columns]
        
        if len(available_cols) < 3:
            st.error("❌ Stok-Satış tablosunda gerekli sütunlar eksik!")
            return pd.DataFrame()
        
        stok_satis = tables["KS Stok Satış"][available_cols].copy()
        
        dagitim_verileri = dagitim_verileri.merge(stok_satis, on=["magaza_kodu", "urun_kodu"], how="left")
        
        # Eşleşme yoksa prefix ile dene
        if "stok" not in dagitim_verileri.columns or dagitim_verileri["stok"].isna().all():
    
    # KS Ciro
    if "KS Ciro" in tables and tables["KS Ciro"] is not None:
        ciro_col = "ks_ciro" if "ks_ciro" in tables["KS Ciro"].columns else "kasa_aktivitesi_ciro"
        if ciro_col in tables["KS Ciro"].columns:
            ks_ciro = tables["KS Ciro"][["magaza_kodu", ciro_col]].copy()
            ks_ciro.rename(columns={ciro_col: "ks_ciro"}, inplace=True)
            dagitim_verileri = dagitim_verileri.merge(ks_ciro, on="magaza_kodu", how="left")
    
    # Yeni ürün için mal grubu ciroları
    if urun.get("yeni_mi", "eski") == "yeni":
        if "KS Mal Grubu" in tables and tables["KS Mal Grubu"] is not None:
            mal_ciro = tables["KS Mal Grubu"][["magaza_kodu", "mal_grubu", "mal_grubu_ciro"]].copy()
            dagitim_verileri = dagitim_verileri.merge(mal_ciro, on=["magaza_kodu", "mal_grubu"], how="left")
        
        if "KS Üst Mal Grubu" in tables and tables["KS Üst Mal Grubu"] is not None:
            ust_ciro = tables["KS Üst Mal Grubu"][["magaza_kodu", "ust_mal_grubu", "ust_mal_grubu_ciro"]].copy()
            dagitim_verileri = dagitim_verileri.merge(ust_ciro, on=["magaza_kodu", "ust_mal_grubu"], how="left")
    
    # Eksik değerler
    for col in ["stok", "satis_4hafta", "stok_4hafta_sonunda", "ks_ciro", "mal_grubu_ciro", "ust_mal_grubu_ciro"]:
        if col in dagitim_verileri.columns:
            dagitim_verileri[col] = dagitim_verileri[col].fillna(0)
    
    # Negatif stokları 0'a çevir
    dagitim_verileri["stok"] = dagitim_verileri["stok"].clip(lower=0)
    if "stok_4hafta_sonunda" in dagitim_verileri.columns:
        dagitim_verileri["stok_4hafta_sonunda"] = dagitim_verileri["stok_4hafta_sonunda"].clip(lower=0)
    
    # ARA SATIŞ HESAPLAMA
    if "stok_4hafta_sonunda" in dagitim_verileri.columns:
        dagitim_verileri["ara_satis"] = (dagitim_verileri["stok_4hafta_sonunda"] - dagitim_verileri["stok"]).clip(lower=0)
    else:
        dagitim_verileri["ara_satis"] = 0
    
    # TOPLAM SATIŞ GÜCÜ
    dagitim_verileri["toplam_satis_gucu"] = dagitim_verileri["satis_4hafta"] + (dagitim_verileri["ara_satis"] * 0.5)
    
    # Stok oranı
    dagitim_verileri["stok_orani"] = dagitim_verileri["stok"] / (dagitim_verileri["stok"] + dagitim_verileri["satis_4hafta"] + 1e-9)
    
    # İlçe skoru
    dagitim_verileri["hangi_ilce_score"] = dagitim_verileri["hangi_ilce"].apply(map_hangi_ilce_score)
    
    # SKOR
    if urun.get("yeni_mi", "eski") == "yeni":
        weights = {
            "toplam_satis_gucu": 0.50,
            "ks_ciro": 0.25,
            "ust_mal_grubu_ciro": 0.05,
            "mal_grubu_ciro": 0.10,
            "hangi_ilce_score": 0.05
        }
    else:
        weights = {
            "toplam_satis_gucu": 0.50,
            "ks_ciro": 0.25,
            "hangi_ilce_score": 0.05
        }
    
    total_weight = sum(weights.values())
    weights = {k: v / total_weight for k, v in weights.items()}
    
    skor = pd.Series([0.0]*len(dagitim_verileri), index=dagitim_verileri.index)
    for col, weight in weights.items():
        if col in dagitim_verileri.columns:
            skor += normalize_column(dagitim_verileri, col) * weight
    
    # Stok tükenme bonusu
    stok_tukendi = (dagitim_verileri["stok"] == 0) & (dagitim_verileri["ara_satis"] > 0)
    skor += stok_tukendi.astype(float) * 0.15
    
    # Durgunluk cezası
    durgun = (dagitim_verileri["ara_satis"] == 0) & (dagitim_verileri["stok"] > 0)
    if "stok_4hafta_sonunda" in dagitim_verileri.columns:
        birikim = dagitim_verileri.apply(
            lambda x: (x["stok"] / x["stok_4hafta_sonunda"]) if x["stok_4hafta_sonunda"] > 0 else 0, axis=1
        )
        skor -= durgun.astype(float) * birikim * 0.10
    
    # Stok oranı cezası
    skor -= dagitim_verileri["stok_orani"] * 0.30
    
    dagitim_verileri["skor"] = skor.clip(lower=0)
    
    # DAĞITIM - DİNAMİK MİNİMUM (HİBRİT)
    total_koli = urun["dagitilacak_koli"]
    magaza_sayisi = len(dagitim_verileri)
    
    # Ortalama koli/mağaza hesapla
    koli_per_magaza = total_koli / magaza_sayisi
    
    # Dinamik minimum belirleme (Hibrit: 2-3-4-5)
    if koli_per_magaza >= 15:
        base_minimum = 5
        st.info(f"ℹ️ Ortalama {koli_per_magaza:.1f} koli/mağaza → Base Minimum: 5 koli (Çok Bol)")
    elif koli_per_magaza >= 10:
        base_minimum = 4
        st.info(f"ℹ️ Ortalama {koli_per_magaza:.1f} koli/mağaza → Base Minimum: 4 koli (Bol)")
    elif koli_per_magaza >= 5:
        base_minimum = 3
        st.info(f"ℹ️ Ortalama {koli_per_magaza:.1f} koli/mağaza → Base Minimum: 3 koli (Orta)")
    else:
        base_minimum = 2
        st.info(f"ℹ️ Ortalama {koli_per_magaza:.1f} koli/mağaza → Base Minimum: 2 koli (Az)")
    
    # ESKİ ÜRÜNLERDE STOK KONTROLÜ (Aylık Stok Mantığı)
    if urun.get("yeni_mi", "eski") == "eski":
        st.info("🔍 Eski ürün - Stok kontrolü yapılıyor...")
        
        # Aylık stok hesapla (4 haftalık satış = 1 ay)
        dagitim_verileri["aylik_stok"] = dagitim_verileri["stok"] / (dagitim_verileri["satis_4hafta"] + 1)
        
        # Minimum'u stok durumuna göre ayarla
        dagitim_verileri["minimum_koli"] = base_minimum
        
        # Top 40 mağazalar: Minimum = 0 (öncelik!)
        dagitim_verileri.loc[top_40_magazalar, "minimum_koli"] = 0
        
        # Diğer mağazalarda stok kontrolü:
        diger_magazalar = ~dagitim_verileri["top_40"]
        
        # 2 aydan fazla stoğu olanlar: Minimum = 0
        cok_stoklu = diger_magazalar & (dagitim_verileri["aylik_stok"] >= 2.0)
        dagitim_verileri.loc[cok_stoklu, "minimum_koli"] = 0
        
        # 1-2 ay arası stoğu olanlar: Minimum = yarım
        orta_stoklu = diger_magazalar & (dagitim_verileri["aylik_stok"] >= 1.0) & (dagitim_verileri["aylik_stok"] < 2.0)
        dagitim_verileri.loc[orta_stoklu, "minimum_koli"] = int(base_minimum / 2)
        
        # 1 aydan az stoğu olanlar: Minimum = tam (zaten base_minimum)
        
        stok_kontrol_ozet = dagitim_verileri.groupby(["top_40", "minimum_koli"]).size().reset_index(name="count")
        st.write("📊 Stok Kontrolü Sonuçları:")
        for _, row in stok_kontrol_ozet.iterrows():
            tip = "Top 40" if row["top_40"] else "Diğer"
            st.write(f"  - {tip}: {row['count']} mağaza → {int(row['minimum_koli'])} koli minimum")
        
        minimum_total = dagitim_verileri["minimum_koli"].sum()
        
    else:
        # YENİ ÜRÜNLERDE: Top 40 → 0, Diğerleri → base_minimum
        st.info("🆕 Yeni ürün - Top 40 mağaza minimum almıyor")
        dagitim_verileri["minimum_koli"] = base_minimum
        dagitim_verileri.loc[top_40_magazalar, "minimum_koli"] = 0
        
        st.write("📊 Minimum Dağılımı:")
        st.write(f"  - Top 40: 40 mağaza → 0 koli minimum")
        st.write(f"  - Diğer: 164 mağaza → {base_minimum} koli minimum")
        
        minimum_total = 164 * base_minimum
    
    # Yetersiz koli kontrolü
    if total_koli < minimum_total:
        st.warning(f"⚠️ Toplam koli ({total_koli}) yetersiz. Minimum dağıtım için {minimum_total} koli gerekli.")
        st.info("💡 Minimum'lar oranla azaltılıyor...")
        
        # Oranla azalt
        azaltma_orani = total_koli / minimum_total
        dagitim_verileri["minimum_koli"] = (dagitim_verileri["minimum_koli"] * azaltma_orani).apply(floor)
        minimum_total = dagitim_verileri["minimum_koli"].sum()
    
    # Minimum dağıtımı yap
    dagitim_verileri["dagitilan_koli"] = dagitim_verileri["minimum_koli"]
    kalan_koli = total_koli - minimum_total
    
    if kalan_koli > 0:
        skor_toplam = dagitim_verileri["skor"].sum()
        if skor_toplam > 0:
            dagitim_verileri["ek_koli"] = (dagitim_verileri["skor"] / skor_toplam * kalan_koli).fillna(0).apply(floor)
            dagitim_verileri["dagitilan_koli"] += dagitim_verileri["ek_koli"]
            
            fark = kalan_koli - dagitim_verileri["ek_koli"].sum()
            if fark > 0:
                dagitim_verileri["kesir"] = (dagitim_verileri["skor"] / skor_toplam * kalan_koli) % 1
                top_mag = dagitim_verileri.nlargest(int(fark), "kesir").index
                dagitim_verileri.loc[top_mag, "dagitilan_koli"] += 1
    
    # Sütun sırası
    column_order = [
        "magaza_kodu", "magaza_adi", "urun_kodu", "urun_adi", "dagitilan_koli", "minimum_koli", "top_40", "skor",
        "stok", "satis_4hafta", "ara_satis", "toplam_satis_gucu", "ks_ciro",
        "hangi_ilce", "hangi_ilce_score", "stok_orani"
    ]
    
    if urun.get("yeni_mi", "eski") == "yeni":
        column_order.extend(["mal_grubu", "mal_grubu_ciro", "ust_mal_grubu", "ust_mal_grubu_ciro"])
    
    if "stok_4hafta_sonunda" in dagitim_verileri.columns:
        column_order.append("stok_4hafta_sonunda")
    
    if "aylik_stok" in dagitim_verileri.columns:
        column_order.append("aylik_stok")
    
    available_columns = [col for col in column_order if col in dagitim_verileri.columns]
    return dagitim_verileri[available_columns]

# ANA UYGULAMA
st.markdown("---")

kategori = st.selectbox("📂 Kategori", ["Grup Spot", "Kasa Aktivitesi"])

st.markdown("---")

if kategori == "Kasa Aktivitesi":
    st.subheader("📥 Dosya Yükleme")
    col1, col2 = st.columns(2)
    
    with col1:
        urun_bilgisi_dosyasi = st.file_uploader("1️⃣ Ürün Bilgisi", type=["xlsx"], key="urun_bilgi")
    with col2:
        stok_satis_file = st.file_uploader("2️⃣ Stok-Satış Tablosu", type=["xlsx"], key="stok_satis", help="ZORUNLU")
else:
    st.subheader("📥 Dosya Yükleme")
    col1, col2 = st.columns(2)
    
    with col1:
        urun_bilgisi_dosyasi = st.file_uploader("1️⃣ Ürün Bilgisi", type=["xlsx"], key="urun_bilgi")
    with col2:
        stok_satis_file = st.file_uploader("2️⃣ Güncel Stok-Satış (Opsiyonel)", type=["xlsx"], key="stok_satis")

# Tablo yükleme
if kategori == "Grup Spot":
    tables = {
        "Ürün Grubu Ciro Tablosu": load_local_excel("urun_grubu_ciro_tablosu.xlsx"),
        "Üss Mal Grubu Ciro Tablosu": load_local_excel("ust_mal_grubu_ciro_tablosu.xlsx"),
        "Raf Sepet Bilgi Tablosu": load_local_excel("raf_sepet_bilgi_tablosu.xlsx"),
        "Mağaza Bilgi Tablosu": load_local_excel("magaza_bilgi_tablosu.xlsx"),
        "Stok Satış Tablosu": normalize_columns(pd.read_excel(stok_satis_file)) if stok_satis_file else load_local_excel("stok_satis_tablosu.xlsx")
    }
else:
    if not stok_satis_file:
        st.warning("⚠️ Kasa Aktivitesi için Stok-Satış Tablosu zorunludur.")
        st.stop()
    
    tables = {
        "KS Mağaza Bilgi": load_local_excel("magaza_bilgi_tablosu.xlsx"),
        "KS Ciro": load_local_excel("ks_ciro.xlsx"),
        "KS Mal Grubu": load_local_excel("ks_mal.xlsx"),
        "KS Üst Mal Grubu": load_local_excel("ks_ust_mal.xlsx"),
        "KS Stok Satış": unify_column_names(normalize_columns(pd.read_excel(stok_satis_file)))
    }
    
    for key in ["KS Mağaza Bilgi", "KS Ciro", "KS Mal Grubu", "KS Üst Mal Grubu"]:
        if tables[key] is not None:
            tables[key] = unify_column_names(tables[key])

missing_tables = [name for name, table in tables.items() if table is None]
if missing_tables:
    st.error(f"❌ Sunucuda eksik: {', '.join(missing_tables)}")
else:
    st.success("✅ Sistem hazır")

if urun_bilgisi_dosyasi and not missing_tables:
    urun_bilgisi = unify_column_names(normalize_columns(pd.read_excel(urun_bilgisi_dosyasi)))
    
    st.success(f"✅ {len(urun_bilgisi)} ürün yüklendi")
    
    with st.expander("👁️ Ürün Listesi"):
        st.dataframe(urun_bilgisi.head(10), use_container_width=True)
    
    st.markdown("---")
    
    if st.button("🚀 Dağıtımı Hesapla", type="primary", use_container_width=True):
        with st.spinner("Hesaplanıyor..."):
            dagitim_planlari = []
            progress_bar = st.progress(0)
            
            for idx, (_, urun) in enumerate(urun_bilgisi.iterrows()):
                try:
                    if kategori == "Grup Spot":
                        plan = calculate_distribution_plan(tables, urun)
                    else:
                        plan = calculate_kasa_aktivitesi(tables, urun)
                    
                    if plan is not None and not plan.empty:
                        dagitim_planlari.append(plan)
                except Exception as e:
                    st.error(f"❌ Hata (Ürün {idx+1}): {str(e)}")
                
                progress_bar.progress((idx + 1) / len(urun_bilgisi))
            
            progress_bar.empty()
            
            if not dagitim_planlari:
                st.error("❌ Dağıtım oluşturulamadı.")
                st.stop()
            
            birlesmis = pd.concat(dagitim_planlari, ignore_index=True)
            
            st.markdown("### 📊 Özet")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Mağaza", birlesmis["magaza_kodu"].nunique())
            with col2:
                st.metric("Ürün", birlesmis["urun_kodu"].nunique())
            with col3:
                st.metric("Toplam Koli", int(birlesmis["dagitilan_koli"].sum()))
            
            with st.expander("📋 Detaylar (İlk 50)", expanded=True):
                st.dataframe(birlesmis.head(50), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                birlesmis.to_excel(writer, index=False, sheet_name='Dağıtım')
            
            output.seek(0)
            
            st.download_button(
                label="📥 Excel İndir (.xlsx)",
                data=output.getvalue(),
                file_name=f"dagitim_{kategori.lower().replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
            st.success("✅ Hazır!")
elif urun_bilgisi_dosyasi:
    st.info("⏳ Kontrol ediliyor...")
else:
    st.info("👆 Dosyaları yükleyin")
