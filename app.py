import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Valuador Portafolio USD", layout="wide")

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    TABLE_NAME = st.secrets["TABLE_NAME"]
    table = Table(AIRTABLE_KEY, BASE_ID, TABLE_NAME)
except Exception as e:
    st.error(f"⚠️ Error en Secrets: {e}")
    st.stop()

# --- 2. PROCESAMIENTO ---
st.title("📈 Mi Portafolio: Nexo CEDEAR -> Wall Street")

try:
    records = table.all()
    if records:
        df = pd.DataFrame([r['fields'] for r in records])
        
        # --- DESCARGA DE PRECIOS SEGURA ---
        tickers_eeuu = df['Ticker_EEUU'].unique().tolist()
        
        with st.spinner('Consultando Wall Street...'):
            # Usamos auto_adjust=True y forzamos a que sea un DataFrame simple
            data = yf.download(tickers_eeuu, period="1d", interval="1d", auto_adjust=True)
            
            # Si solo hay un ticker, data['Close'] es una Serie. Si hay varios, es un DataFrame.
            if len(tickers_eeuu) > 1:
                precios_hoy = data['Close'].iloc[-1].to_dict()
            else:
                # Caso especial para un solo ticker
                ultimo_precio = data['Close'].iloc[-1]
                precios_hoy = {tickers_eeuu[0]: float(ultimo_precio)}

        # --- CÁLCULOS ---
        df['Acciones_EEUU'] = df['Cantidad'] / df['Ratio']
        # Mapeamos los precios asegurándonos de que no haya errores de Ticker
        df['Precio_USD'] = df['Ticker_EEUU'].map(precios_hoy)
        df['Total_USD'] = df['Acciones_EEUU'] * df['Precio_USD']
        
        # --- DASHBOARD ---
        total_cartera = df['Total_USD'].sum()
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.metric("Patrimonio Total", f"USD {total_cartera:,.2f}")
            fig_pie = px.pie(df, values='Total_USD', names='Ticker Argy', 
                             hole=0.4, title="Distribución por Activo")
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            st.subheader("📋 Desglose de Tenencia")
            columnas_finales = [
                'Ticker Argy', 'Descripción', 'Cantidad', 'Ratio', 
                'Acciones_EEUU', 'Ticker_EEUU', 'Precio_USD', 'Total_USD'
            ]
            st.dataframe(df[columnas_finales].style.format({
                'Acciones_EEUU': '{:.4f}',
                'Precio_USD': '${:.2f}',
                'Total_USD': '${:.2f}'
            }), use_container_width=True)

        st.divider()
        fig_bar = px.bar(df, x='Ticker Argy', y='Total_USD', color='Ticker Argy',
                         title="Valorización por Activo (USD)", text_auto='.2s')
        st.plotly_chart(fig_bar, use_container_width=True)

    else:
        st.info("Cargá datos en Airtable para visualizar el portafolio.")

except Exception as e:
    st.error(f"Error técnico en el cálculo: {e}")
    st.info("Revisá que los nombres de las columnas en Airtable coincidan exactamente con el código.")
