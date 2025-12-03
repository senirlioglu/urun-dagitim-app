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

def normalize_column(df, column):
    if column not in df.columns or df[column].nunique() == 0:
        return pd.Series([0]*len(df))
    col_min = df[column].min()
    col_max = df[column].max()
    return (df[column] - col_min) / (col_max - col_min) if (col_max - col_min) != 0 else df[column].apply(lambda x: 1 if x != 0 else 0)

def map_hangi_ilce_score(ilce):
    ilce_weights = {"muratpasa": 1.0, "kepez": 0.7}
    return ilce_weights.get(str(ilce).lower(), 0)

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
    dagitim_verileri["urun_adi"] = urun["urun_adi"]
    dagitim_verileri["ust_mal_grubu"] = urun.get("ust_mal_grubu", "")
    dagitim_verileri["mal_grubu"] = urun.get("mal_grubu", "")
    
    # Stok-Satış tablosunu birleştir
    if "KS Stok Satış" in tables and tables["KS Stok Satış"] is not None:
        stok_satis = tables["KS Stok Satış"][["magaza_kodu", "urun_kodu", "stok", "satis_4hafta"]].copy()
        dagitim_verileri = dagitim_verileri.merge(
            stok_satis,
            on=["magaza_kodu", "urun_kodu"],
            how="left"
        )
    
    # KS Ciro tablosunu birleştir
    if "KS Ciro" in tables and tables["KS Ciro"] is not None:
        ks_ciro = tables["KS Ciro"][["magaza_kodu", "ks_ciro"]].copy()
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
    for col in ["stok", "satis_4hafta", "ks_ciro", "mal_grubu_ciro", "ust_mal_grubu_ciro"]:
        if col in dagitim_verileri.columns:
            dagitim_verileri[col] = dagitim_verileri[col].fillna(0)
    
    # Stok oranı hesapla
    dagitim_verileri["stok"] = dagitim_verileri["stok"].clip(lower=0)
    dagitim_verileri["stok_orani"] = dagitim_verileri["stok"] / (dagitim_verileri["stok"] + dagitim_verileri["satis_4hafta"] + 1e-9)
    
    # İlçe skoru
    dagitim_verileri["hangi_ilce_score"] = dagitim_verileri["hangi_ilce"].apply(map_hangi_ilce_score)
    
    # SKOR HESAPLAMA
    if urun.get("yeni_mi", "eski") == "yeni":
        # Yeni ürün: Satış %50 + KS Ciro %25 + Üst Mal %5 + Mal %10 + İlçe %5 - Stok %30
        weights = {
            "satis_4hafta": 0.50,
            "ks_ciro": 0.25,
            "ust_mal_grubu_ciro": 0.05,
            "mal_grubu_ciro": 0.10,
            "hangi_ilce_score": 0.05
        }
    else:
        # Eski ürün: Satış %50 + KS Ciro %25 + İlçe %5 - Stok %30
        weights = {
            "satis_4hafta": 0.50,
            "ks_ciro": 0.25,
            "hangi_ilce_score": 0.05
        }
    
    # Ağırlıkları normalize et
    total_weight = sum(weights.values())
    weights = {k: v / total_weight for k, v in weights.items()}
    
    # Skor hesapla
    skor = pd.Series([0.0]*len(dagitim_verileri))
    for col, weight in weights.items():
        if col in dagitim_verileri.columns:
            skor += normalize_column(dagitim_verileri, col) * weight
    
    # Stok cezası (-%30)
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
        "stok", "satis_4hafta", "ks_ciro", "hangi_ilce", "hangi_ilce_score", "stok_orani"
    ]
    
    if urun.get("yeni_mi", "eski") == "yeni":
        column_order.extend(["mal_grubu", "mal_grubu_ciro", "ust_mal_grubu", "ust_mal_grubu_ciro"])
    
    available_columns = [col for col in column_order if col in dagitim_verileri.columns]
    
    return dagitim_verileri[available_columns]

# ANA UYGULAMA
st.markdown("---")

# Kategori Seçimi
kategori = st.selectbox(
    "📂 Dağıtım Kategorisi Seçin",
    ["Grup Spot", "Kasa Aktivitesi"],
    help="Hangi kategori için dağıtım planı oluşturacaksınız?"
)

st.markdown("---")

# Dosya Yükleme Alanları
col1, col2 = st.columns(2)

with col1:
    st.subheader("📥 Gerekli Dosyalar")
    urun_bilgisi_dosyasi = st.file_uploader(
        f"{'GS' if kategori == 'Grup Spot' else 'KS'} Ürün Bilgisi Dosyası",
        type=["xlsx"],
        key="urun_bilgi"
    )

with col2:
    st.subheader("📥 Opsiyonel Dosyalar")
    stok_satis_file = st.file_uploader(
        f"Güncel {'GS' if kategori == 'Grup Spot' else 'KS'} Stok-Satış Tablosu",
        type=["xlsx"],
        key="stok_satis"
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
    tables = {
        "KS Mağaza Bilgi": load_local_excel("magaza_bilgi_tablosu.xlsx"),
        "KS Ciro": load_local_excel("ks_ciro_tablosu.xlsx"),
        "KS Mal Grubu": load_local_excel("ks_mal_grubu_tablosu.xlsx"),
        "KS Üst Mal Grubu": load_local_excel("ks_ust_mal_grubu_tablosu.xlsx"),
        "KS Stok Satış": normalize_columns(pd.read_excel(stok_satis_file)) if stok_satis_file else load_local_excel("ks_stok_satis_tablosu.xlsx")
    }
    
    # Sütun isimlerini birleştir
    for key in tables:
        if tables[key] is not None:
            tables[key] = unify_column_names(tables[key])

# Eksik tabloları kontrol et
missing_tables = [name for name, table in tables.items() if table is None]
if missing_tables:
    st.error(f"❌ Eksik tablolar: {', '.join(missing_tables)}")
    st.info("💡 Lütfen tüm gerekli Excel dosyalarını aynı klasöre yerleştirin.")
else:
    st.success(f"✅ Tüm tablolar yüklendi ({kategori})")

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
                if kategori == "Grup Spot":
                    plan = calculate_distribution_plan(tables, urun)
                else:  # Kasa Aktivitesi
                    plan = calculate_kasa_aktivitesi(tables, urun)
                
                dagitim_planlari.append(plan)
                progress_bar.progress((idx + 1) / len(urun_bilgisi))
            
            progress_bar.empty()
            
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
            
            st.download_button(
                "📥 Excel Dosyasını İndir",
                output.getvalue(),
                f"dagitim_plani_{kategori.lower().replace(' ', '_')}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            st.success("✅ Dağıtım planı başarıyla oluşturuldu!")
else:
    st.info("👆 Başlamak için lütfen Ürün Bilgisi dosyasını yükleyin.")
