import pandas as pd
import streamlit as st
import io

# -------------------------------------------------------------------
# ORİJİNAL KODUN TEMEL ALINDIĞI, SADECE GEREKLİ EKLEMELERİN YAPILDIĞI VERSİYON
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
            s_val = s_val.replace('.', '').replace(',', '.')
        elif ',' in s_val:
            s_val = s_val.replace(',', '.')
        return float(s_val)
    except (ValueError, TypeError):
        return 0.0

def stok_dagitimi(df):
    """
    Orijinal dağıtım mantığını kullanarak, sütun adı farklılıklarına karşı
    daha esnek hale getirilmiş fonksiyon.
    """
    # Adım 1: Ana stok sütununu standart bir isme ('Ges.bestand') çevir.
    # Bu, 'Ges.bes' veya 'tan' gibi farklı isimleri de kabul eder.
    df.rename(columns=lambda col: 'Ges.bestand' if str(col).strip() in ['Ges.bes', 'tan'] else col, inplace=True)

    # Adım 2: Bayi sütun adlarındaki yaygın hataları düzelt.
    sutun_duzeltmeleri = {
        'BirollarTeklifFiyat': 'Birollar TeklifFiyat',
        'MNGIST OZIS Tekliffiyat': 'MNGIST OZIS TeklifFiyat',
        'MNGIST OZIS ADET': 'MNGIST OZIS Adet',
        'KolIist1 Tekliffiyat': 'Kolist1 TeklifFiyat', # Büyük 'I' harfi düzeltmesi
        'Kolist1 adet': 'Kolist1 Adet',
        'KolIist2 Tekliffiyat': 'Kolist2 TeklifFiyat', # Büyük 'I' harfi düzeltmesi
        'Kolist2 adet': 'Kolist2 Adet',
        'Dogmer Tekliffiyat': 'Doğmer TeklifFiyat',
        'Doğmer Tekliffiyat': 'Doğmer TeklifFiyat',
        # Yeni eklenen bayi
        'KolistG adet': 'KolistG Adet',
        'KolistG Tekliffiyat': 'KolistG TeklifFiyat'
    }
    df.rename(columns=sutun_duzeltmeleri, inplace=True)

    # Orijinal bayi bulma mantığı
    bayiler = sorted(list(set([col.replace('Adet', '').strip() for col in df.columns if 'Adet' in col])))
    
    bayi_toplam_odemeleri = {bayi: 0.0 for bayi in bayiler}

    df['Kalan Stok'] = 0.0
    df['Seçilen Bayiler'] = "" 
    df['Toplam Satış Tutarı'] = 0.0

    for index, row in df.iterrows():
        # 'satılabilinir' yazmayanları atla
        if 'Durum' in df.columns and str(row.get('Durum', '')).strip() != 'satılabilinir':
            continue

        # Orijinal stok sütunu adını kullan
        kalan_stok = akilli_sayi_cevirici(row.get('Ges.bestand'))
        if kalan_stok <= 0:
            continue

        teklifler = []
        for bayi in bayiler:
            talep_adet_col = f'{bayi} Adet'.strip()
            # Orijinal teklif sütunu adı formatını kullan
            teklif_fiyat_col = f'{bayi} TeklifFiyat'.strip()
            
            if talep_adet_col in df.columns and teklif_fiyat_col in df.columns:
                talep_adet = akilli_sayi_cevirici(row[talep_adet_col])
                teklif_fiyat = akilli_sayi_cevirici(row[teklif_fiyat_col])
                
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
    
    # GÜNCELLEME: Başlık satırını seçme özelliği eklendi.
    header_row = st.number_input(
        "Excel'deki başlıklar kaçıncı satırda?", 
        min_value=1, 
        value=1, 
        help="Lütfen sütun başlıklarınızın (Ges.bestand, Durum vb.) bulunduğu satır numarasını girin."
    )
    
    if st.button("Stok Dağıtımını Başlat", type="primary"):
        try:
            # GÜNCELLEME: Excel dosyası, seçilen başlık satırına göre okunuyor.
            header_index = header_row - 1
            # Orijinal dtype=str kullanımı korunuyor.
            df_input = pd.read_excel(uploaded_file, header=header_index, dtype=str)
            
            # Ana stok sütununun varlığını esnek bir şekilde kontrol et
            temp_df = df_input.copy()
            temp_df.rename(columns=lambda col: 'Ges.bestand' if str(col).strip() in ['Ges.bes', 'tan'] else col, inplace=True)
            if 'Ges.bestand' not in temp_df.columns:
                 st.error(
                    f"HATA: Ana stok sütunu ('Ges.bestand', 'Ges.bes' veya 'tan') bulunamadı. "
                    f"Lütfen doğru başlık satırını ({header_row}) seçtiğinizden emin olun."
                )
            else:
                with st.spinner('Hesaplamalar yapılıyor, lütfen bekleyin...'):
                    sonuc_df, ozet_df = stok_dagitimi(df_input.copy())

                st.success("✅ Hesaplama başarıyla tamamlandı!")
                
                st.subheader("Bayi Özet Tablosu")
                if ozet_df.empty:
                    st.warning("Hesaplama sonucunda herhangi bir bayiye satış yapılamadı.")
                else:
                    st.dataframe(ozet_df.style.format({"Toplam Ödenecek Tutar": "{:,.2f}"}))
                
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
