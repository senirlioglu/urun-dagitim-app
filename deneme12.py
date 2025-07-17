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
    return normalize_columns(pd.read_excel(path))

def normalize_column(df, column):
    if df[column].nunique() == 0:
        return pd.Series([0]*len(df))
    col_min = df[column].min()
    col_max = df[column].max()
    return (df[column] - col_min) / (col_max - col_min) if (col_max - col_min) != 0 else df[column].apply(lambda x: 1 if x != 0 else 0)

def map_hangi_ilce_score(ilce):
    ilce_weights = {"muratpaşa": 1.0, "kepez": 0.7}
    return ilce_weights.get(str(ilce).lower(), 0)

def map_magaza_tipi_score(tipi):
    tipi_weights = {"large": 0.6, "spot": 0.4, "standart": 0.3}
    return tipi_weights.get(str(tipi).lower(), 0.3)

# Ana Dağıtım Hesaplama Fonksiyonu
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
urun_bilgisi_dosyasi = st.file_uploader("📥 Ürün Bilgisi Dosyası", type=["xlsx"])
stok_satis_file = st.file_uploader("📥 Güncel Stok-Satış Tablosu (opsiyonel)", type=["xlsx"])

tables = {
    "Ürün Grubu Ciro Tablosu": load_local_excel("urun_grubu_ciro_tablosu.xlsx"),
    "Üss Mal Grubu Ciro Tablosu": load_local_excel("ust_mal_grubu_ciro_tablosu.xlsx"),
    "Raf Sepet Bilgi Tablosu": load_local_excel("raf_sepet_bilgi_tablosu.xlsx"),
    "Mağaza Bilgi Tablosu": load_local_excel("magaza_bilgi_tablosu.xlsx"),
    "Stok Satış Tablosu": normalize_columns(pd.read_excel(stok_satis_file)) if stok_satis_file else load_local_excel("stok_satis_tablosu.xlsx")
}
st.info("📤 Dosya yükleniyor...")
if urun_bilgisi_dosyasi:
    urun_bilgisi = normalize_columns(pd.read_excel(urun_bilgisi_dosyasi))

    with st.spinner("🔄 Dağıtım planı hesaplanıyor..."):
        dagitim_planlari = [calculate_distribution_plan(tables, urun) for _, urun in urun_bilgisi.iterrows()]
        birlesmis = pd.concat(dagitim_planlari)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            birlesmis.to_excel(writer, index=False)

        st.success("✅ Dağıtım planı hazır!")
        st.download_button("📥 Excel İndir", output.getvalue(), "dagitim_plani.xlsx")
