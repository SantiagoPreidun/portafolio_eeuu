import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuador Portafolio USD", layout="wide")

# --- 2. CARGA DE CREDENCIALES ---
try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    TABLE_NAME = st.secrets["TABLE_NAME"] # Asegurate que en Secrets diga "Portafolio"
    
    table = Table(AIRTABLE_KEY, BASE_ID, TABLE_NAME)
except Exception as e:
    st.error(f"⚠️ Error en las credenciales: {e}")
    st.stop()

# --- 3. PROCESAMIENTO DE DATOS ---
st.title("📈 Mi Portafolio: Nexo CEDEAR -> Wall Street")

try:
    # 1. Traer datos de Airtable
    records = table.all()
    
    if records:
        # Convertimos a DataFrame
        df = pd.DataFrame([r['fields'] for r in records])
        
        # 2. Descargar precios de Yahoo Finance
        tickers_eeuu = df['Ticker_EEUU'].unique().tolist()
        
        with st.spinner('Consultando cotizaciones en Wall Street...'):
            data = yf.download(tickers_eeuu, period="1d")['Close']
            
            # Ajuste por si es uno o varios tickers
            if len(tickers_eeuu) > 1:
                precios_dict = data.iloc[-1].to_dict()
            else:
                precios_dict = {tickers_eeuu[0]: data.iloc[-1]}

        # 3. Cálculos del "Nexo"
        df['Acciones_EEUU'] = df['Cantidad'] / df['Ratio']
        df['Precio_USD'] = df['Ticker_EEUU'].map(precios_dict)
        df['Total_USD'] = df['Acciones_EEUU'] * df['Precio_USD']
        
        # --- 4. DASHBOARD (ORDEN CORRECTO) ---
        total_cartera = df['Total_USD'].sum()
        
        # Definimos las columnas ANTES de usarlas
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.metric("Patrimonio Total", f"USD {total_cartera:,.2f}")
            
            # Gráfico de torta (Usando el nombre exacto 'Ticker Argy')
            fig_pie = px.pie(df, values='Total_USD', names='Ticker Argy', 
                             hole=0.4, title="Distribución por Activo")
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            st.subheader("📋 Desglose de Tenencia")
            # Mostramos la tabla con los nombres de tus columnas de Airtable
            columnas_finales = [
                'Ticker Argy', 'Descripción', 'Cantidad', 'Ratio', 
                'Acciones_EEUU', 'Ticker_EEUU', 'Precio_USD', 'Total_USD'
            ]
            
            st.dataframe(df[columnas_finales].style.format({
                'Acciones_EEUU': '{:.4f}',
                'Precio_USD': '${:.2f}',
                'Total_USD': '${:.2f}'
            }), use_container_width=True)

        # Gráfico de barras inferior
        st.divider()
        fig_bar = px.bar(df, x='Ticker Argy', y='Total_USD', color='Ticker Argy',
                         title="Valorización por Activo (USD)", text_auto='.2s')
        st.plotly_chart(fig_bar, use_container_width=True)

    else:
        st.info("No hay datos en la tabla de Airtable. Cargá tus activos para empezar.")

except Exception as e:
    st.error(f"Ocurrió un error al procesar los datos: {e}")
