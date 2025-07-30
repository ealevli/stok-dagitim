import pandas as pd
import streamlit as st
import io

# -------------------------------------------------------------------
# AKILLI SAYI DÖNÜŞTÜRÜCÜ VE ANA DAĞITIM FONKSİYONU
# -------------------------------------------------------------------

def akilli_sayi_cevirici(value):
    """
    Excel'deki farklı sayı formatlarını ('1.250,75' veya '1250.75' gibi)
    akıllıca anlayan ve doğru şekilde sayıya (float) çeviren nihai fonksiyon.
    """
    if pd.isna(value) or value == '':
        return 0.0
    try:
        s_val = str(value)
        if ',' in s_val and '.' in s_val:
            if s_val.find('.') < s_val.find(','):
                s_val = s_val.replace('.', '').replace(',', '.')
            else:
                s_val = s_val.replace(',', '')
        elif ',' in s_val:
            s_val = s_val.replace(',', '.')
        return float(s_val)
    except (ValueError, TypeError):
        return 0.0

def stok_dagitimi(df):
    """
    İstekleriniz doğrultusunda güncellenmiş dağıtım mantığını içeren fonksiyon.
    'Adet' sütununu ana stok olarak kullanır ve fiyat sütunlarında 'Teklif' arar.
    """
    df.columns = [str(c) for c in df.columns]

    # Sütun adlarındaki yaygın yazım hatalarını ve kısaltmaları standart formata çevirir.
    sutun_duzeltmeleri = {
        'DogmerTeklif': 'Doğmer Teklif',
        'HasmerTeki': 'Hasmer Teklif',
        'KolG Adı': 'KolG Adet',
        'KolG Tek': 'KolG Teklif',
        'Kolist1 adet': 'Kolist1 Adet',
        'Kolist1 Tekliffiyat': 'Kolist1 Teklif',
        'Kolist2 adet': 'Kolist2 Adet',
        'Kolist2 Tekliffiyat': 'Kolist2 Teklif',
    }
    df.rename(columns=sutun_duzeltmeleri, inplace=True)

    # Bayi listesini 'Adet' içeren sütunlardan otomatik olarak bulur.
    bayiler = sorted(list(set([col.replace('Adet', '').strip() for col in df.columns if 'Adet' in col])))
    
    bayi_toplam_odemeleri = {bayi: 0.0 for bayi in bayiler}

    # --- HATA DÜZELTME (Duplicate column names found) ---
    # Program tarafından eklenen sonuç sütunları (Kalan Stok vb.), eğer yüklenen
    # dosyada zaten mevcutsa, yinelenen sütun hatasına neden olur.
    # Bu blok, bu sütunları işlemeye başlamadan önce kaldırarak sorunu çözer.
    output_columns = ['Kalan Stok', 'Seçilen Bayiler', 'Toplam Satış Tutarı']
    for col_name in output_columns:
        if col_name in df.columns:
            df.drop(col_name, axis=1, inplace=True)
    # --- DÜZELTME SONU ---

    df['Kalan Stok'] = 0.0
    df['Seçilen Bayiler'] = "" 
    df['Toplam Satış Tutarı'] = 0.0

    for index, row in df.iterrows():
        if 'Durum' in df.columns and pd.notna(row.get('Durum')) and str(row.get('Durum')).strip().lower() != 'satılabilinir':
            continue

        kalan_stok = akilli_sayi_cevirici(row.get('Adet'))
        if kalan_stok <= 0:
            continue

        teklifler = []
        for bayi in bayiler:
            talep_adet_col = f'{bayi} Adet'.strip()
            teklif_fiyat_col = f'{bayi} Teklif'.strip()
            
            if talep_adet_col in df.columns and teklif_fiyat_col in df.columns:
                talep_adet = akilli_sayi_cevirici(row.get(talep_adet_col))
                teklif_fiyat = akilli_sayi_cevirici(row.get(teklif_fiyat_col))
                
                if talep_adet > 0 and teklif_fiyat > 0:
                    teklifler.append({'bayi_adi': bayi, 'talep_adet': talep_adet, 'teklif_fiyat': teklif_fiyat})

        sirali_teklifler = sorted(teklifler, key=lambda x: x['teklif_fiyat'], reverse=True)
        
        secilenler = []
        toplam_gelir_bu_urun_icin = 0.0
        for teklif in sirali_teklifler:
            if kalan_stok <= 0: break
            bayi_adi = teklif['bayi_adi']
            talep_edilen = teklif['talep_adet']
            birim_fiyat = teklif['teklif_fiyat']
            atanacak_adet = min(talep_edilen, kalan_stok)
            if atanacak_adet > 0:
                satis_tutari = atanacak_adet * birim_fiyat
                bayi_toplam_odemeleri[bayi_adi] += satis_tutari
                kalan_stok -= atanacak_adet
                secilenler.append(bayi_adi)
                toplam_gelir_bu_urun_icin += satis_tutari
                
        df.loc[index, 'Toplam Satış Tutarı'] = toplam_gelir_bu_urun_icin
        df.loc[index, 'Kalan Stok'] = kalan_stok
        df.loc[index, 'Seçilen Bayiler'] = ", ".join(secilenler)
    
    ozet_df = pd.DataFrame(list(bayi_toplam_odemeleri.items()), columns=['Bayi Adı', 'Toplam Ödenecek Tutar'])
    ozet_df = ozet_df[ozet_df['Toplam Ödenecek Tutar'] > 0].sort_values(by='Toplam Ödenecek Tutar', ascending=False)
    
    return df, ozet_df

# -------------------------------------------------------------------
# STREAMLIT WEB UYGULAMASI ARAYÜZÜ
# -------------------------------------------------------------------

st.set_page_config(page_title="Stok Dağıtım Otomasyonu", layout="wide")

st.title("📦 Stok Dağıtım Otomasyon Aracı")
st.write("Bu araç, Excel dosyanızdaki teklifleri analiz ederek stokları en yüksek birim fiyata göre dağıtır ve sonuçları raporlar.")

uploaded_file = st.file_uploader("Lütfen Excel dosyanızı buraya sürükleyin veya seçin", type=["xlsx"])

if uploaded_file is not None:
    st.info(f"'{uploaded_file.name}' dosyası yüklendi.")
    
    header_row = st.number_input(
        "Excel'deki başlıklar kaçıncı satırda?", 
        min_value=1, 
        value=1, 
        help="Lütfen sütun başlıklarınızın (Parça Numarası, Adet vb.) bulunduğu satır numarasını girin."
    )
    
    if st.button("Stok Dağıtımını Başlat", type="primary"):
        try:
            header_index = header_row - 1
            df_input = pd.read_excel(uploaded_file, engine='openpyxl', header=header_index)
            
            if 'Adet' not in df_input.columns:
                st.error(
                    f"HATA: 'Adet' sütunu bulunamadı. "
                    f"Lütfen doğru başlık satırını ({header_row}) seçtiğinizden ve "
                    f"Excel dosyanızda bu isimde bir sütun olduğundan emin olun."
                )
            else:
                with st.spinner('Hesaplamalar yapılıyor, lütfen bekleyin...'):
                    sonuc_df, ozet_df = stok_dagitimi(df_input.copy())

                st.success("✅ Hesaplama başarıyla tamamlandı!")
                
                st.subheader("Bayi Özet Tablosu")
                if ozet_df.empty:
                    st.warning("Hesaplama sonucunda herhangi bir bayiye satış yapılamadı.")
                else:
                    st.dataframe(ozet_df.style.format({"Toplam Ödenecek Tutar": "{:,.2f} TL"}))
                
                st.subheader("Detaylı Dağıtım Sonucu")
                st.dataframe(sonuc_df)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    sonuc_df.to_excel(writer, sheet_name='Detaylı Dağıtım Sonucu', index=False)
                    ozet_df.to_excel(writer, sheet_name='Bayi Özet Tablosu', index=False)
                    
                    workbook = writer.book
                    ws1 = writer.sheets['Detaylı Dağıtım Sonucu']
                    ws2 = writer.sheets['Bayi Özet Tablosu']
                    number_format = '#,##0.00'

                    for col_name in ['Toplam Satış Tutarı', 'Kalan Stok']:
                        if col_name in sonuc_df.columns:
                            col_idx = list(sonuc_df.columns).index(col_name) + 1
                            for row in ws1.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx, max_row=ws1.max_row):
                                if row[0].value is not None: row[0].number_format = number_format
                    
                    if not ozet_df.empty:
                        col_idx_2 = list(ozet_df.columns).index('Toplam Ödenecek Tutar') + 1
                        for row in ws2.iter_rows(min_row=2, min_col=col_idx_2, max_col=col_idx_2, max_row=ws2.max_row):
                            if row[0].value is not None: row[0].number_format = number_format

                processed_data = output.getvalue()
                
                st.download_button(
                    label="📁 Sonuçları Excel Olarak İndir",
                    data=processed_data,
                    file_name='stok_dagitim_sonucu.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )

        except Exception as e:
            st.error(f"Bir hata oluştu: {e}")
            st.info("Lütfen başlık satırı numarasını doğru girdiğinizden ve Excel dosyanızın formatının bozuk olmadığından emin olun.")
