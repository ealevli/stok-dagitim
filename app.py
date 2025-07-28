import pandas as pd
import streamlit as st
import io

# -------------------------------------------------------------------
# SİZİN EN SON VERDİĞİNİZ KODUN TAMAMI BURADA
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
        # Eğer hem virgül hem nokta varsa, noktayı binlik, virgülü ondalık kabul et
        if ',' in s_val and '.' in s_val:
            s_val = s_val.replace('.', '').replace(',', '.')
        # Sadece virgül varsa, onu ondalık kabul et
        elif ',' in s_val:
            s_val = s_val.replace(',', '.')
        # Diğer durumlarda (sadece nokta var veya hiçbiri yok) Python doğru anlar
        return float(s_val)
    except (ValueError, TypeError):
        return 0.0

def stok_dagitimi(df): # Fonksiyon artık dosya yolu yerine DataFrame alıyor
    """
    Sizin en son sağladığınız dağıtım mantığı.
    """
    sutun_duzeltmeleri = {
        'BirollarTeklifFiyat': 'Birollar TeklifFiyat', 'MNGIST OZIS Tekliffiyat': 'MNGIST OZIS TeklifFiyat',
        'MNGIST OZIS ADET': 'MNGIST OZIS Adet', 'KolIist1 Tekliffiyat': 'Kolist1 TeklifFiyat',
        'Kolist1 adet': 'Kolist1 Adet', 'KolIist2 Tekliffiyat': 'Kolist2 TeklifFiyat',
        'Kolist2 adet': 'Kolist2 Adet', 'Dogmer Tekliffiyat': 'Doğmer TeklifFiyat'
    }
    df.rename(columns=sutun_duzeltmeleri, inplace=True)

    bayiler = sorted(list(set([col.replace('Adet', '').strip() for col in df.columns if 'Adet' in col])))
    
    bayi_toplam_odemeleri = {bayi: 0.0 for bayi in bayiler}

    # Her bayi için 'Atanan Adet' sütunları tekrar ekleniyor
    for bayi in bayiler:
        if f'{bayi} Atanan Adet' not in df.columns:
            df[f'{bayi} Atanan Adet'] = 0.0

    df['Kalan Stok'] = 0.0
    df['Seçilen Bayiler'] = "" 
    df['Toplam Satış Tutarı'] = 0.0

    for index, row in df.iterrows():
        if str(row.get('Durum', '')).strip() != 'satılabilinir':
            continue

        kalan_stok = akilli_sayi_cevirici(row.get('Ges.bestand'))
        if kalan_stok <= 0: continue

        teklifler = []
        for bayi in bayiler:
            talep_adet_col = f'{bayi} Adet'.strip()
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
                # Atanan Adet sütununu doldur
                df.loc[index, f'{bayi_adi} Atanan Adet'] = atanacak_adet
                
        df.loc[index, 'Toplam Satış Tutarı'] = toplam_gelir_bu_urun_icin
        df.loc[index, 'Kalan Stok'] = kalan_stok
        df.loc[index, 'Seçilen Bayiler'] = ", ".join(list(dict.fromkeys(secilenler)))

    ozet_df = pd.DataFrame(list(bayi_toplam_odemeleri.items()), columns=['Bayi Adı', 'Toplam Ödenecek Tutar'])
    ozet_df = ozet_df[ozet_df['Toplam Ödenecek Tutar'] > 0].sort_values(by='Toplam Ödenecek Tutar', ascending=False)
    
    return df, ozet_df

# -------------------------------------------------------------------
# STREAMLIT WEB UYGULAMASI KODU
# -------------------------------------------------------------------

st.set_page_config(page_title="Stok Dağıtım Otomasyonu", layout="wide")

st.title("📦 Stok Dağıtım Otomasyon Aracı")
st.write("Bu araç, Excel dosyanızdaki teklifleri analiz ederek stokları en yüksek birim fiyata göre dağıtır ve sonuçları raporlar.")

uploaded_file = st.file_uploader("Lütfen Excel dosyanızı buraya sürükleyin veya seçin", type=["xlsx"])

if uploaded_file is not None:
    st.success(f"'{uploaded_file.name}' başarıyla yüklendi!")
    
    try:
        # Excel dosyasını direkt olarak DataFrame'e oku
        # dtype=str ile okumak, sayı formatlarının korunmasına yardımcı olur.
        df_input = pd.read_excel(uploaded_file, dtype=str)
        
        if st.button("Stok Dağıtımını Başlat", type="primary"):
            with st.spinner('Hesaplamalar yapılıyor, lütfen bekleyin...'):
                sonuc_df, ozet_df = stok_dagitimi(df_input)

            st.success("✅ Hesaplama başarıyla tamamlandı!")
            
            st.subheader("Bayi Özet Tablosu")
            st.dataframe(ozet_df.style.format({"Toplam Ödenecek Tutar": "{:,.2f}"}))
            
            st.subheader("Detaylı Dağıtım Sonucu")
            st.dataframe(sonuc_df)
            
            # Excel dosyasını hafızada oluşturma
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                sonuc_df.to_excel(writer, sheet_name='Detaylı Dağıtım Sonucu', index=False)
                ozet_df.to_excel(writer, sheet_name='Bayi Özet Tablosu', index=False)
                
                # Excel'de sayı formatını ayarlama
                workbook = writer.book
                ws1 = writer.sheets['Detaylı Dağıtım Sonucu']
                ws2 = writer.sheets['Bayi Özet Tablosu']
                number_format = '#,##0.00'

                for col_name in ['Toplam Satış Tutarı', 'Kalan Stok']:
                    if col_name in sonuc_df.columns:
                        col_idx = list(sonuc_df.columns).index(col_name) + 1
                        for row in ws1.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
                            if row[0].value is not None: row[0].number_format = number_format
                
                col_idx_2 = list(ozet_df.columns).index('Toplam Ödenecek Tutar') + 1
                for row in ws2.iter_rows(min_row=2, min_col=col_idx_2, max_col=col_idx_2):
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