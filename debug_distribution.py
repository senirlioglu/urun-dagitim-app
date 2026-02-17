import pandas as pd
from math import floor

def normalize_columns(df):
    turkish_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    df.columns = df.columns.str.strip().str.lower().str.translate(turkish_map).str.replace(" ", "_")
    return df

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

# Load tables
tables = {
    "Ürün Grubu Ciro Tablosu": normalize_columns(pd.read_excel("urun_grubu_ciro_tablosu.xlsx")),
    "Üss Mal Grubu Ciro Tablosu": normalize_columns(pd.read_excel("ust_mal_grubu_ciro_tablosu.xlsx")),
    "Raf Sepet Bilgi Tablosu": normalize_columns(pd.read_excel("raf_sepet_bilgi_tablosu.xlsx")),
    "Mağaza Bilgi Tablosu": normalize_columns(pd.read_excel("magaza_bilgi_tablosu.xlsx")),
    "Stok Satış Tablosu": normalize_columns(pd.read_excel("stok_satis_tablosu.xlsx"))
}

magaza_bilgi = tables["Mağaza Bilgi Tablosu"]

# Check spot stores
spot_stores = magaza_bilgi[magaza_bilgi['magaza_tipi'].str.lower() == 'spot']
print(f"Total stores: {len(magaza_bilgi)}")
print(f"Spot stores: {len(spot_stores)}")
print(f"Large stores: {len(magaza_bilgi[magaza_bilgi['magaza_tipi'].str.lower() == 'large'])}")
print(f"Standart stores: {len(magaza_bilgi[magaza_bilgi['magaza_tipi'].str.lower() == 'standart'])}")

# Let's pick a known urun_grubu from the ciro table and simulate
urun_grubu_ciro_df = tables["Ürün Grubu Ciro Tablosu"]
test_urun_grubu = urun_grubu_ciro_df['urun_grubu'].value_counts().index[0]
print(f"\nTesting with urun_grubu: '{test_urun_grubu}'")

# Pick an actual existing urun_kodu from the stok table for valid merge
stok_df = tables["Stok Satış Tablosu"]
test_urun_kodu = stok_df['urun_kodu'].value_counts().index[0]
print(f"Using real urun_kodu: {test_urun_kodu} (type: {type(test_urun_kodu).__name__})")

# Pick a valid grup_kodu that exists in raf table
raf_df = tables["Raf Sepet Bilgi Tablosu"]
available_grup_cols = [c for c in raf_df.columns if c.startswith('grup_')]
print(f"Available grup columns in raf table: {sorted(available_grup_cols)}")
# Use first available grup
test_grup_kodu = int(available_grup_cols[0].replace('grup_', '')) if available_grup_cols else 1
print(f"Using grup_kodu: {test_grup_kodu}")

# Simulate the full distribution for a test product
urun = {
    "urun_kodu": test_urun_kodu,
    "urun_adi": "Test Product",
    "urun_grubu": test_urun_grubu,
    "ust_mal_grubu": tables["Üss Mal Grubu Ciro Tablosu"]['ust_mal_grubu'].value_counts().index[0],
    "depolama_kosulu": "Normal",
    "yeni_mi": "yeni",
    "dagitilacak_koli": 138,
    "grup_kodu": test_grup_kodu
}

dagitim_verileri = magaza_bilgi.copy()
dagitim_verileri["urun_kodu"] = urun["urun_kodu"]
dagitim_verileri["urun_adi"] = urun["urun_adi"]
dagitim_verileri["urun_grubu"] = urun["urun_grubu"]
dagitim_verileri["ust_mal_grubu"] = urun["ust_mal_grubu"]
dagitim_verileri["depolama_kosulu"] = urun["depolama_kosulu"]

grup_kodu_sutun = 'grup_' + str(urun["grup_kodu"])

merge_operations = [
    (tables["Ürün Grubu Ciro Tablosu"], ["magaza_kodu", "urun_grubu"], ["urun_grubu_ciro"]),
    (tables["Üss Mal Grubu Ciro Tablosu"], ["magaza_kodu", "ust_mal_grubu"], ["ust_mal_grubu_ciro"]),
    (tables["Stok Satış Tablosu"], ["magaza_kodu", "urun_kodu"], ["stok", "satis"])
]

if urun["depolama_kosulu"] not in ["Soğuk(+4)", "Donuk(-18)"]:
    raf_cols = ["magaza_kodu", "raf_sayisi"]
    if grup_kodu_sutun in tables["Raf Sepet Bilgi Tablosu"].columns:
        raf_cols.append(grup_kodu_sutun)
        merge_operations.append(
            (tables["Raf Sepet Bilgi Tablosu"], ["magaza_kodu"], ["raf_sayisi", grup_kodu_sutun])
        )
    else:
        print(f"WARNING: {grup_kodu_sutun} not found in raf table!")
        print(f"Available columns: {[c for c in tables['Raf Sepet Bilgi Tablosu'].columns if c.startswith('grup_')][:10]}")

for table, on_columns, columns in merge_operations:
    available_cols = [c for c in columns if c in table.columns]
    if len(available_cols) != len(columns):
        print(f"WARNING: Missing columns in merge: {set(columns) - set(available_cols)}")
    dagitim_verileri = dagitim_verileri.merge(
        table[on_columns + available_cols],
        on=on_columns,
        how="left"
    )

if grup_kodu_sutun in dagitim_verileri.columns:
    dagitim_verileri.rename(columns={grup_kodu_sutun: "raf_arasi_sayisi"}, inplace=True)
    dagitim_verileri["raf_arasi_sayisi"] = pd.to_numeric(dagitim_verileri["raf_arasi_sayisi"], errors='coerce')
elif "raf_arasi_sayisi" not in dagitim_verileri.columns:
    dagitim_verileri["raf_arasi_sayisi"] = 0

if "raf_sayisi" not in dagitim_verileri.columns:
    dagitim_verileri["raf_sayisi"] = 0

for col in ["stok", "satis", "urun_grubu_ciro", "ust_mal_grubu_ciro"]:
    dagitim_verileri[col] = dagitim_verileri[col].fillna(0)

dagitim_verileri["stok"] = dagitim_verileri["stok"].clip(lower=0)
dagitim_verileri["stok_orani"] = dagitim_verileri["stok"] / (dagitim_verileri["stok"] + dagitim_verileri["satis"] + 1e-9)
dagitim_verileri["satis_hizi"] = dagitim_verileri["satis"] / max(dagitim_verileri["satis"].sum(), 1)
dagitim_verileri["hangi_ilce_score"] = dagitim_verileri["hangi_ilce"].apply(map_hangi_ilce_score)
dagitim_verileri["magaza_tipi_score"] = dagitim_verileri["magaza_tipi"].apply(map_magaza_tipi_score)

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

total_weight = sum(normalized_columns.values())
normalized_columns = {k: v / total_weight for k, v in normalized_columns.items()}

print("\n=== Column statistics before normalization ===")
for col in normalized_columns:
    vals = dagitim_verileri[col]
    print(f"  {col}: min={vals.min():.4f}, max={vals.max():.4f}, mean={vals.mean():.4f}, zeros={int((vals==0).sum())}/{len(vals)}")

skor = pd.Series([0.0]*len(dagitim_verileri))
for col, weight in normalized_columns.items():
    norm_val = normalize_column(dagitim_verileri, col)
    contribution = norm_val * weight
    skor += contribution
    print(f"  {col} (w={weight:.3f}): norm range [{norm_val.min():.4f}, {norm_val.max():.4f}], contribution range [{contribution.min():.4f}, {contribution.max():.4f}]")

dagitim_verileri["skor"] = skor.clip(lower=0)

print(f"\n=== Score statistics ===")
print(f"  Total score sum: {dagitim_verileri['skor'].sum():.4f}")
print(f"  Scores > 0: {(dagitim_verileri['skor'] > 0).sum()}")
print(f"  Scores == 0: {(dagitim_verileri['skor'] == 0).sum()}")

# Calculate distribution
total = urun["dagitilacak_koli"]
skor_toplam = dagitim_verileri["skor"].sum()

if skor_toplam == 0 or pd.isna(skor_toplam):
    dagitim_verileri["dagitilan_koli"] = 0
    print("\n!!! ALL SCORES ARE ZERO - NO DISTRIBUTION POSSIBLE !!!")
else:
    dagitim_verileri["dagitilan_koli"] = (dagitim_verileri["skor"] / skor_toplam * total).fillna(0).apply(floor)

fark = total - dagitim_verileri["dagitilan_koli"].sum()
if fark > 0:
    dagitim_verileri["kalan"] = (dagitim_verileri["skor"] / skor_toplam * total) % 1
    top_magazalar = dagitim_verileri.nlargest(fark, "kalan").index
    dagitim_verileri.loc[top_magazalar, "dagitilan_koli"] += 1

total_distributed = dagitim_verileri["dagitilan_koli"].sum()
print(f"\n=== Distribution results ===")
print(f"  dagitilacak_koli: {total}")
print(f"  total distributed: {total_distributed}")
print(f"  difference: {total - total_distributed}")

# Break down by store type
for store_type in ["Large", "Spot", "Standart"]:
    mask = dagitim_verileri['magaza_tipi'].str.lower() == store_type.lower()
    subset = dagitim_verileri[mask]
    if len(subset) > 0:
        print(f"\n  {store_type} stores ({len(subset)} stores):")
        print(f"    Total distributed: {subset['dagitilan_koli'].sum()}")
        print(f"    Mean score: {subset['skor'].mean():.6f}")
        print(f"    Stores with 0 distribution: {(subset['dagitilan_koli'] == 0).sum()}")
        print(f"    Mean urun_grubu_ciro: {subset['urun_grubu_ciro'].mean():.2f}")
        print(f"    Mean ust_mal_grubu_ciro: {subset['ust_mal_grubu_ciro'].mean():.2f}")

# Now simulate with an urun_grubu that does NOT match (like "Grup Spot" scenario)
print("\n\n============================")
print("=== SCENARIO 2: Non-matching urun_grubu (simulating Grup Spot issue) ===")
print("============================")

dagitim2 = magaza_bilgi.copy()
dagitim2["urun_grubu"] = "NONEXISTENT_GROUP"
dagitim2["ust_mal_grubu"] = "NONEXISTENT_MAL_GROUP"
dagitim2["urun_kodu"] = "TEST002"

# Convert urun_kodu to string in stok table for this merge
stok_table_str = tables["Stok Satış Tablosu"].copy()
stok_table_str["urun_kodu"] = stok_table_str["urun_kodu"].astype(str)

dagitim2 = dagitim2.merge(
    tables["Ürün Grubu Ciro Tablosu"][['magaza_kodu', 'urun_grubu', 'urun_grubu_ciro']],
    on=['magaza_kodu', 'urun_grubu'], how='left'
)
dagitim2 = dagitim2.merge(
    tables["Üss Mal Grubu Ciro Tablosu"][['magaza_kodu', 'ust_mal_grubu', 'ust_mal_grubu_ciro']],
    on=['magaza_kodu', 'ust_mal_grubu'], how='left'
)
dagitim2 = dagitim2.merge(
    stok_table_str[['magaza_kodu', 'urun_kodu', 'stok', 'satis']],
    on=['magaza_kodu', 'urun_kodu'], how='left'
)

for col in ["stok", "satis", "urun_grubu_ciro", "ust_mal_grubu_ciro"]:
    dagitim2[col] = dagitim2[col].fillna(0)

print(f"  urun_grubu_ciro all zero: {(dagitim2['urun_grubu_ciro'] == 0).all()}")
print(f"  ust_mal_grubu_ciro all zero: {(dagitim2['ust_mal_grubu_ciro'] == 0).all()}")
print(f"  stok all zero: {(dagitim2['stok'] == 0).all()}")
print(f"  satis all zero: {(dagitim2['satis'] == 0).all()}")

# With ciro=0, stok=0, satis=0 - the only scoring columns are gs_ciro, ortalama_ciro, raf, magaza_tipi
dagitim2["stok_orani"] = 0
dagitim2["satis_hizi"] = 0
dagitim2["hangi_ilce_score"] = dagitim2["hangi_ilce"].apply(map_hangi_ilce_score)
dagitim2["magaza_tipi_score"] = dagitim2["magaza_tipi"].apply(map_magaza_tipi_score)

# Check if raf columns would also be 0
if 'raf_sayisi' not in dagitim2.columns:
    dagitim2['raf_sayisi'] = 0
if 'raf_arasi_sayisi' not in dagitim2.columns:
    dagitim2['raf_arasi_sayisi'] = 0

skor2 = pd.Series([0.0]*len(dagitim2))
for col, weight in normalized_columns.items():
    if col in dagitim2.columns:
        norm_val = normalize_column(dagitim2, col)
        skor2 += norm_val * weight
        print(f"  {col}: all_zero={dagitim2[col].eq(0).all()}, norm_max={norm_val.max():.4f}")

dagitim2["skor"] = skor2.clip(lower=0)
print(f"\n  Total score: {dagitim2['skor'].sum():.6f}")
print(f"  Scores > 0: {(dagitim2['skor'] > 0).sum()}")

if dagitim2['skor'].sum() > 0:
    dagitim2["dagitilan_koli"] = (dagitim2["skor"] / dagitim2["skor"].sum() * 138).fillna(0).apply(floor)
    print(f"  Total distributed (138 koli): {dagitim2['dagitilan_koli'].sum()}")
    fark = 138 - dagitim2['dagitilan_koli'].sum()
    print(f"  Floor loss (fark): {fark}")
else:
    print("  ALL SCORES ZERO - NOTHING DISTRIBUTED!")
