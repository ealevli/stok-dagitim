import pandas as pd
import streamlit as st
import io

# -------------------------------------------------------------------
# KODUN NİHAİ VE EN KARARLI VERSİYONU
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
    Sütun adı farklılıklarına karşı esnek, akıllı bayi tanıma ve dağıtım mantığı.
    """
    # Adım 1: Tüm sütun adlarını standart bir formata (küçük harf) getirerek tutarlılık sağla.
    original_columns = df.columns
    df.columns = [str(col).lower().strip() for col in df.columns]
    
    # Adım 2: Ana stok sütununu 'adet' olarak standartlaştır.
    df.rename(columns={'ges.bestand': 'adet', 'ges.bes': 'adet', 'tan': 'adet'}, inplace=True)

    # Adım 3: Hem '... adet' hem de '... teklif...' sütunları olan bayileri akıllıca bul.
    bayiler = []
    potential_dealers = list(set([col.replace(' adet', '') for col in df.columns if col.endswith(' adet') and col != 'adet']))
    
    for bayi_name in potential_dealers:
        # Fiyat sütununu esnek bir şekilde ara ('tekliffiyat', 'teklifiyat', 'tek' vb.)
        for col in df.columns:
            if col.startswith(bayi_name) and any(col.endswith(suffix) for suffix in ['tekliffiyat', 'teklifiyat', 'tek']):
                bayiler.append(bayi_name)
                break # Eşleşen ilk fiyat sütununu bul ve sonraki bayiye geç
    
    bayiler = sorted(list(set(bayiler)))
    bayi_toplam_odemeleri = {bayi: 0.0 for bayi in bayiler}

    # Orijinal büyük/küçük harfli sütun adlarını kullanarak yeni bir DataFrame oluştur.
    # Bu, sonuçların orijinal dosya gibi görünmesini sağlar.
    sonuc_df = pd.DataFrame(columns=original_columns)
    sonuc_df['Kalan Stok'] = 0.0
    sonuc_df['Seçilen Bayiler'] = "" 
    sonuc_df['Toplam Satış Tutarı'] = 0.0

    for index, row in df.iterrows():
        # Orijinal satırı sonuç df'ine kopyala
        for i, col_name in enumerate(original_columns):
            sonuc_df.loc[index, col_name] = row.iloc[i]

        if str(row.get('durum', '')).strip() != 'satılabilinir':
            continue

        kalan_stok = akilli_sayi_cevirici(row.get('adet'))
        if kalan_stok <= 0:
            continue

        teklifler = []
        for bayi in bayiler:
            talep_adet_col = f'{bayi} adet'
            
            teklif_fiyat_col = None
            for col in df.columns:
                if col.startswith(bayi) and any(col.endswith(suffix) for suffix in ['tekliffiyat', 'teklifiyat', 'tek']):
                    teklif_fiyat_col = col
                    break
            
            if teklif_fiyat_col:
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
                bayi_toplam_odemeleri[bayi] += satis_tutari
                kalan_stok -= atanacak_adet
                secilenler.append(bayi.title())
                toplam_gelir_bu_urun_icin += satis_tutari
                
        sonuc_df.loc[index, 'Toplam Satış Tutarı'] = toplam_gelir_bu_urun_icin
        sonuc_df.loc[index, 'Kalan Stok'] = kalan_stok
        sonuc_df.loc[index, 'Seçilen Bayiler'] = ", ".join(secilenler)
    
    ozet_df = pd.DataFrame(list(bayi_toplam_odemeleri.items()), columns=['Bayi Adı', 'Toplam Ödenecek Tutar'])
    ozet_df['Bayi Adı'] = ozet_df['Bayi Adı'].str.title()
    ozet_df = ozet_df[ozet_df['Toplam Ödenecek Tutar'] > 0].sort_values(by='Toplam Ödenecek Tutar', ascending=False)
    
    return sonuc_df, ozet_df

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
        help="Lütfen sütun başlıklarınızın (Adet, Durum vb.) bulunduğu satır numarasını girin."
    )
    
    if st.button("Stok Dağıtımını Başlat", type="primary"):
        try:
            header_index = header_row - 1
            df_input = pd.read_excel(uploaded_file, header=header_index)
            
            # Stok sütununun varlığını esnek bir şekilde kontrol et
            temp_cols = [str(c).lower().strip() for c in df_input.columns]
            if not any(c in ['adet', 'ges.bestand', 'ges.bes', 'tan'] for c in temp_cols):
                 st.error(
                    f"HATA: Stok miktarını içeren 'Adet' (veya 'Ges.bestand', 'Ges.bes') sütunu bulunamadı. "
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
