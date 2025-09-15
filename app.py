# app.py
import re
import io
import pandas as pd
import streamlit as st

# ------------------------------------------------------------
# Yardımcılar
# ------------------------------------------------------------
def _normalize(s: str) -> str:
    """Kolon adı karşılaştırmaları için sadeleştirilmiş form."""
    return str(s).strip().lower().replace(' ', '').replace('_', '')

# Stok kolonu için olası isimler
_MUHTEMEL_STOK_ISIMLER = {
    'ges.bestand', 'gesbestand', 'gesbes', 'gesbesand', 'ges',
    'bestand', 'stok', 'tan'
}

def _map_stok_kolon_adi(col):
    """Kolon adını stok kolonuna eşlerse 'Ges.bestand' döndürür."""
    return 'Ges.bestand' if _normalize(col) in _MUHTEMEL_STOK_ISIMLER else col

def akilli_sayi_cevirici(value):
    """
    '1.250,75' ya da '1,250.75' gibi değerleri doğru float'a çevirir.
    Para sembolleri ve boşlukları temizler.
    """
    if pd.isna(value) or value == '':
        return 0.0
    s = str(value).strip()
    # rakam, virgül, nokta, eksi dışını temizle
    s = re.sub(r'[^\d,.\-]', '', s)

    # hem virgül hem nokta varsa: son görülen ayraç ondalıktır kabulü
    if ',' in s and '.' in s:
        last_comma = s.rfind(',')
        last_dot = s.rfind('.')
        dec = ',' if last_comma > last_dot else '.'
        thou = '.' if dec == ',' else ','
        s = s.replace(thou, '').replace(dec, '.')
        try:
            return float(s)
        except:
            return 0.0

    # sadece virgül varsa → ondalık kabul et
    if ',' in s and '.' not in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0

# ---- Bayi kolonlarını akıllıca eşleyecek yardımcılar ------------------------

# Fiyat kolonlarında en çok rastlanan token'lar (öncelik sırasıyla)
_FIYAT_TOKENS_PRIORITIZED = [
    'tekliffiyat', 'teklif_fiyat', 'tekliffiyati', 'teklif',
    'birimfiyat', 'birim_fiyat', 'birimfiyati',
    'bfiyat', 'fiyat'
]
# Fiyat kolonunda istemediğimiz anahtarlar
_EXCLUDE_TOKENS = {'toplam', 'adet'}

def _find_price_col_for_base(base_name: str, all_columns: list[str]) -> str | None:
    """
    base_name: 'Birollar' gibi bayi kökü.
    all_columns: df.columns (stringleştirilmiş).
    Dönüş: eşleşen fiyat kolon adı ya da None.
    """
    base_norm = _normalize(base_name)
    candidates = []
    for c in all_columns:
        cn = _normalize(c)
        # aynı bayi köküyle başlamalı (örn 'birollar...')
        if not cn.startswith(base_norm):
            continue
        # 'adet' ve 'toplam' gibi kolonlar fiyat değildir
        if any(tok in cn for tok in _EXCLUDE_TOKENS):
            continue
        # token önceliğine göre skorla
        matched = False
        for prio, tok in enumerate(_FIYAT_TOKENS_PRIORITIZED):
            if tok in cn:
                candidates.append((prio, c))
                matched = True
                break
        if not matched and 'fiyat' in cn:
            # yalnız 'fiyat' geçen, ama listede olmayan varyasyonlar için
            candidates.append((len(_FIYAT_TOKENS_PRIORITIZED) + 1, c))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]

def _extract_dealers(df: pd.DataFrame) -> list[str]:
    """'* Adet' kolonlarından bayi isim köklerini çıkarır."""
    bases = []
    for col in df.columns:
        s = str(col)
        if 'Adet' in s:
            bases.append(s.replace('Adet', '').strip())
    return sorted(list(set(bases)))

# ------------------------------------------------------------
# Dağıtım Mantığı
# ------------------------------------------------------------
def stok_dagitimi(df: pd.DataFrame, debug: bool = False):
    """
    Stokları en yüksek birim fiyata göre dağıtır.
    'Durum' sütunu dikkate ALINMAZ.
    """
    # 1) Kolon adlarını string'e çevir ve kırp
    df.columns = [str(c).strip() for c in df.columns]

    # 2) Bilinen yazım düzeltmeleri (varsa)
    sutun_duzeltmeleri = {
        'BirollarTeklifFiyat': 'Birollar TeklifFiyat',
        'MNGIST OZIS Tekliffiyat': 'MNGIST OZIS TeklifFiyat',
        'MNGIST OZIS ADET': 'MNGIST OZIS Adet',
        'KolIist1 Tekliffiyat': 'Kolist1 TeklifFiyat',  # I → l
        'Kolist1 adet': 'Kolist1 Adet',
        'KolIist2 Tekliffiyat': 'Kolist2 TeklifFiyat',
        'Kolist2 adet': 'Kolist2 Adet',
        'Dogmer Tekliffiyat': 'Doğmer TeklifFiyat',
        'Doğmer Tekliffiyat': 'Doğmer TeklifFiyat',
        'KolistG adet': 'KolistG Adet',
        'KolistG Tekliffiyat': 'KolistG TeklifFiyat',
    }
    df.rename(columns=sutun_duzeltmeleri, inplace=True)

    # 3) Stok kolonunu normalize et
    df.rename(columns=_map_stok_kolon_adi, inplace=True)

    # 4) Bayi köklerini bul
    bayiler = _extract_dealers(df)

    # 5) Her bayi için fiyat kolonunu dinamik bul
    fiyat_kolon_haritasi = {}
    for bayi in bayiler:
        adet_col = f"{bayi} Adet"
        fiyat_col = _find_price_col_for_base(bayi, list(df.columns))
        if adet_col in df.columns and fiyat_col:
            fiyat_kolon_haritasi[bayi] = (adet_col, fiyat_col)

    if debug:
        st.write("🔎 Bulunan bayi kökleri:", bayiler)
        st.write("🔎 Fiyat kolon eşleşmeleri:", fiyat_kolon_haritasi)

    bayi_toplam_odemeleri = {bayi: 0.0 for bayi in fiyat_kolon_haritasi.keys()}

    # 6) Çıkış kolonları
    df['Kalan Stok'] = 0.0
    df['Seçilen Bayiler'] = ""
    df['Toplam Satış Tutarı'] = 0.0

    # 7) Satır satır dağıtım (DURUM KONTROLÜ YOK)
    for index, row in df.iterrows():
        # Stok
        kalan_stok = akilli_sayi_cevirici(row.get('Ges.bestand'))
        if kalan_stok <= 0:
            continue

        # Teklifleri topla
        teklifler = []
        for bayi, (adet_col, fiyat_col) in fiyat_kolon_haritasi.items():
            talep_adet = akilli_sayi_cevirici(row.get(adet_col, 0))
            teklif_fiyat = akilli_sayi_cevirici(row.get(fiyat_col, 0))
            if talep_adet > 0 and teklif_fiyat > 0:
                teklifler.append({
                    'bayi_adi': bayi,
                    'talep_adet': talep_adet,
                    'teklif_fiyat': teklif_fiyat
                })

        if not teklifler:
            # bu üründe geçerli teklif yoksa olduğu gibi geç
            df.loc[index, 'Kalan Stok'] = kalan_stok
            continue

        # En yüksek birim fiyata göre sırala
        sirali = sorted(teklifler, key=lambda x: x['teklif_fiyat'], reverse=True)

        secilenler = []
        toplam_gelir = 0.0
        for t in sirali:
            if kalan_stok <= 0:
                break
            atanacak = min(t['talep_adet'], kalan_stok)
            if atanacak > 0:
                satis = atanacak * t['teklif_fiyat']
                bayi_toplam_odemeleri[t['bayi_adi']] += satis
                kalan_stok -= atanacak
                toplam_gelir += satis
                secilenler.append(t['bayi_adi'])

        df.loc[index, 'Toplam Satış Tutarı'] = toplam_gelir
        df.loc[index, 'Kalan Stok'] = kalan_stok
        df.loc[index, 'Seçilen Bayiler'] = ", ".join(secilenler)

    # 8) Özet tablo
    ozet_df = (
        pd.DataFrame(list(bayi_toplam_odemeleri.items()),
                     columns=['Bayi Adı', 'Toplam Ödenecek Tutar'])
         .query('`Toplam Ödenecek Tutar` > 0')
         .sort_values('Toplam Ödenecek Tutar', ascending=False)
         .reset_index(drop=True)
    )

    return df, ozet_df


# ------------------------------------------------------------
# STREAMLIT ARAYÜZ
# ------------------------------------------------------------
st.set_page_config(page_title="Stok Dağıtım Otomasyonu", layout="wide")
st.title("📦 Stok Dağıtım Otomasyon Aracı")
st.write("Excel’deki tekliflere göre stokları en yüksek birim fiyata atar ve raporlar.")

uploaded_file = st.file_uploader("Excel dosyasını yükle (.xlsx)", type=["xlsx"])

if uploaded_file is not None:
    st.info(f"'{uploaded_file.name}' dosyası yüklendi.")

    col1, col2 = st.columns([1,1])
    with col1:
        header_row = st.number_input(
            "Excel'deki başlıklar kaçıncı satırda?",
            min_value=1,
            value=1,
            help="Sütun başlıklarının (Ges.bestand, Durum, ... ) bulunduğu satır numarası."
        )
    with col2:
        debug = st.checkbox("Eşleşmeleri göster (debug)", value=False)

    if st.button("Stok Dağıtımını Başlat", type="primary"):
        try:
            header_index = header_row - 1
            # Tüm hücreleri string olarak oku (karışık veri tipleri için güvenli)
            df_input = pd.read_excel(uploaded_file, header=header_index, dtype=str)
            # Kolon adlarını string'e çevir ve buda (INT kolon adları 'is not iterable' hatasını engeller)
            df_input.columns = [str(c).strip() for c in df_input.columns]

            # Stok kolonunu normalize et (erken kontrol için)
            temp_df = df_input.copy()
            temp_df.rename(columns=_map_stok_kolon_adi, inplace=True)

            if 'Ges.bestand' not in temp_df.columns:
                st.error(
                    "HATA: Ana stok sütunu bulunamadı. Muhtemel adlar: "
                    "'Ges.bestand' / 'Bestand' / 'Stok' / 'Ges bes' / 'Ges.bes' / 'tan'. "
                    f"Başlık satırını ({header_row}) ve kolon adlarını kontrol edin."
                )
                st.stop()

            with st.spinner("Hesaplanıyor..."):
                sonuc_df, ozet_df = stok_dagitimi(df_input.copy(), debug=debug)

            st.success("✅ Hesaplama tamamlandı!")

            st.subheader("Bayi Özet Tablosu")
            if ozet_df.empty:
                st.warning("Herhangi bir bayiye satış atanmadı.")
            else:
                st.dataframe(
                    ozet_df,
                    use_container_width=True,
                    column_config={
                        "Toplam Ödenecek Tutar": st.column_config.NumberColumn(format="%,.2f")
                    },
                )

            st.subheader("Detaylı Dağıtım Sonucu")
            st.dataframe(sonuc_df, use_container_width=True)

            # Excel çıktısı
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                sonuc_df.to_excel(writer, sheet_name='Detaylı Dağıtım Sonucu', index=False)
                ozet_df.to_excel(writer, sheet_name='Bayi Özet Tablosu', index=False)

                ws1 = writer.sheets['Detaylı Dağıtım Sonucu']
                ws2 = writer.sheets['Bayi Özet Tablosu']
                number_format = '#,##0.00'

                # Sayı biçimleme
                for col_name in ['Toplam Satış Tutarı', 'Kalan Stok']:
                    if col_name in sonuc_df.columns:
                        col_idx = list(sonuc_df.columns).index(col_name) + 1
                        for row in ws1.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx, max_row=ws1.max_row):
                            if row[0].value is not None:
                                row[0].number_format = number_format

                if not ozet_df.empty and 'Toplam Ödenecek Tutar' in ozet_df.columns:
                    col_idx_2 = list(ozet_df.columns).index('Toplam Ödenecek Tutar') + 1
                    for row in ws2.iter_rows(min_row=2, min_col=col_idx_2, max_col=col_idx_2, max_row=ws2.max_row):
                        if row[0].value is not None:
                            row[0].number_format = number_format

            output.seek(0)
            st.download_button(
                label="📁 Sonuçları Excel Olarak İndir",
                data=output.getvalue(),
                file_name='stok_dagitim_sonucu.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

        except Exception as e:
            st.error(f"Bir hata oluştu: {e}")
            st.info("Başlık satırını doğru seçtiğinizden ve Excel dosyasının bozuk olmadığından emin olun.")

