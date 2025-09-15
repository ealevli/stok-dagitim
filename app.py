import re
import io
import pandas as pd
import streamlit as st

# ------------------------------------------------------------
# Yardımcılar
# ------------------------------------------------------------
def _normalize(s: str) -> str:
    return str(s).strip().lower().replace(' ', '').replace('_', '')

_MUHTEMEL_STOK_ISIMLER = {
    'ges.bestand', 'gesbestand', 'gesbes', 'gesbesand', 'ges',
    'bestand', 'stok', 'tan'
}

def _map_stok_kolon_adi(col):
    return 'Ges.bestand' if _normalize(col) in _MUHTEMEL_STOK_ISIMLER else col

def akilli_sayi_cevirici(value):
    """
    '1.250,75' ya da '1,250.75' gibi değerleri doğru float'a çevirir.
    Para sembolleri ve boşlukları temizler.
    """
    if pd.isna(value) or value == '':
        return 0.0
    s = str(value).strip()
    s = re.sub(r'[^\d,.\-]', '', s)  # sayı, virgül, nokta ve eksi dışını sil

    # hem virgül hem nokta varsa: en son görülen ayraç ondalıktır kabulü
    if ',' in s and '.' in s:
        last_comma = s.rfind(',')
        last_dot = s.rfind('.')
        decimal_sep = ',' if last_comma > last_dot else '.'
        thousand_sep = '.' if decimal_sep == ',' else ','
        s = s.replace(thousand_sep, '')
        s = s.replace(decimal_sep, '.')
        try:
            return float(s)
        except:
            return 0.0

    # sadece virgül varsa → ondalık kabul et
    if ',' in s and '.' not in s:
        s = s.replace('.', '')  # olası binlik noktaları
        s = s.replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0

# ------------------------------------------------------------
# Dağıtım Mantığı
# ------------------------------------------------------------
def stok_dagitimi(df: pd.DataFrame):
    """
    Stokları en yüksek birim fiyata göre dağıtır.
    Kolon adlarındaki küçük farklılıklara toleranslıdır.
    """
    # 1) Kolon adlarını string'e çevir ve buda
    df.columns = [str(c).strip() for c in df.columns]

    # 2) Bilinen yazım hatası/çeşitlemeleri düzelt
    sutun_duzeltmeleri = {
        'BirollarTeklifFiyat': 'Birollar TeklifFiyat',
        'MNGIST OZIS Tekliffiyat': 'MNGIST OZIS TeklifFiyat',
        'MNGIST OZIS ADET': 'MNGIST OZIS Adet',
        'KolIist1 Tekliffiyat': 'Kolist1 TeklifFiyat',  # I → l düzeltmesi
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

    # 4) Bayi isimlerini, "* Adet" kolonlarından çıkar (kolon adları str olarak okunur)
    bayiler = sorted(
        list(
            set(
                [
                    str(col).replace('Adet', '').strip()
                    for col in df.columns
                    if 'Adet' in str(col)
                ]
            )
        )
    )

    bayi_toplam_odemeleri = {bayi: 0.0 for bayi in bayiler}

    # 5) Çıkış kolonlarını hazırla (varsa üzerine yazar)
    df['Kalan Stok'] = 0.0
    df['Seçilen Bayiler'] = ""
    df['Toplam Satış Tutarı'] = 0.0

    # 6) Satır satır dağıtım
    for index, row in df.iterrows():
        # Durum filtresi (varsa)
        if 'Durum' in df.columns:
            durum = str(row.get('Durum', '')).strip().lower()
            izinli = {'satılabilir', 'satilabilir', 'satılabilinir', 'satilabilinir'}
            if durum and durum not in izinli:
                continue

        # Stok
        kalan_stok = akilli_sayi_cevirici(row.get('Ges.bestand'))
        if kalan_stok <= 0:
            continue

        # Teklifleri topla
        teklifler = []
        for bayi in bayiler:
            talep_adet_col = f'{bayi} Adet'
            teklif_fiyat_col = f'{bayi} TeklifFiyat'  # senin şeman
            if talep_adet_col in df.columns and teklif_fiyat_col in df.columns:
                talep_adet = akilli_sayi_cevirici(row.get(talep_adet_col, 0))
                teklif_fiyat = akilli_sayi_cevirici(row.get(teklif_fiyat_col, 0))
                if talep_adet > 0 and teklif_fiyat > 0:
                    teklifler.append(
                        {'bayi_adi': bayi, 'talep_adet': talep_adet, 'teklif_fiyat': teklif_fiyat}
                    )

        # Fiyata göre sırala (azalan)
        sirali_teklifler = sorted(teklifler, key=lambda x: x['teklif_fiyat'], reverse=True)

        # Dağıt
        secilenler = []
        toplam_gelir = 0.0
        for teklif in sirali_teklifler:
            if kalan_stok <= 0:
                break
            bayi_adi = teklif['bayi_adi']
            talep_edilen = teklif['talep_adet']
            birim_fiyat = teklif['teklif_fiyat']
            atanacak = min(talep_edilen, kalan_stok)
            if atanacak > 0:
                satis_tutari = atanacak * birim_fiyat
                bayi_toplam_odemeleri[bayi_adi] += satis_tutari
                kalan_stok -= atanacak
                secilenler.append(bayi_adi)
                toplam_gelir += satis_tutari

        df.loc[index, 'Toplam Satış Tutarı'] = toplam_gelir
        df.loc[index, 'Kalan Stok'] = kalan_stok
        df.loc[index, 'Seçilen Bayiler'] = ", ".join(secilenler)

    # 7) Özet tablo
    ozet_df = (
        pd.DataFrame(list(bayi_toplam_odemeleri.items()), columns=['Bayi Adı', 'Toplam Ödenecek Tutar'])
        .query('`Toplam Ödenecek Tutar` > 0')
        .sort_values(by='Toplam Ödenecek Tutar', ascending=False)
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

    header_row = st.number_input(
        "Excel'deki başlıklar kaçıncı satırda?",
        min_value=1,
        value=1,
        help="Sütun başlıklarının (Ges.bestand, Durum, ... ) bulunduğu satır numarası."
    )

    if st.button("Stok Dağıtımını Başlat", type="primary"):
        try:
            header_index = header_row - 1
            # Tüm hücreleri string olarak oku (karışık veri tipleri için güvenli)
            df_input = pd.read_excel(uploaded_file, header=header_index, dtype=str)
            # Kolon adlarını string'e çevir ve buda (INT kolon adları 'is not iterable' hatasını doğurmasın)
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
                sonuc_df, ozet_df = stok_dagitimi(df_input.copy())

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
