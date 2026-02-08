import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Valuador de Portafolio USD", layout="wide")

# --- 2. CARGA DE CREDENCIALES ---
try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    TABLE_NAME = "Portafolio" # Nombre de la tabla que creaste
    
    table = Table(AIRTABLE_KEY, BASE_ID, TABLE_NAME)
except Exception as e:
    st.error(f"⚠️ Error en los Secrets de Streamlit: {e}")
    st.stop()

# --- 3. PROCESAMIENTO Y DASHBOARD ---
st.title("📈 Mi Portafolio: Nexo CEDEAR -> Wall Street")
st.markdown("Valuación en tiempo real basada en activos subyacentes de EEUU.")

try:
    # Obtenemos los datos de Airtable
    records = table.all()
    
    if records:
        # Creamos el DataFrame
        df = pd.DataFrame([r['fields'] for r in records])
        
        # 1. Obtener los precios actuales de Yahoo Finance
        tickers_eeuu = df['Ticker_EEUU'].unique().tolist()
        
        with st.spinner('Consultando cotizaciones en NYSE/Nasdaq...'):
            # Descargamos solo el último precio de cierre
            precios = yf.download(tickers_eeuu, period="1d")['Close'].iloc[-1]
            
            # Si es un solo ticker, yfinance devuelve un float, si son varios devuelve una Serie
            if len(tickers_eeuu) > 1:
                mapa_precios = precios.to_dict()
            else:
                mapa_precios = {tickers_eeuu[0]: precios}

        # 2. Realizar el NEXO financiero
        # Cantidad de acciones reales en EEUU
        df['Acciones_EEUU'] = df['Cantidad'] / df['Ratio']
        
        # Precio actual en USD
        df['Precio_USD'] = df['Ticker_EEUU'].map(mapa_precios)
        
        # Valuación total de la posición
        df['Total_USD'] = df['Acciones_EEUU'] * df['Precio_USD']

        # --- 4. VISUALIZACIÓN ---
        total_cartera = df['Total_USD'].sum()
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.metric("Patrimonio Total", f"USD {total_cartera:,.2f}")
            
            # Gráfico de distribución
            fig_pie = px.pie(df, values='Total_USD', names='Ticker', 
                             hole=0.4, title="Distribución por Activo")
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            st.subheader("📋 Desglose de Tenencia")
            # Tabla limpia para el usuario
            df_mostrar = df[[
                'Ticker', 'Descripcion', 'Cantidad', 'Ratio', 
                'Acciones_EEUU', 'Ticker_EEUU', 'Precio_USD', 'Total_USD'
            ]]
            
            st.dataframe(df_mostrar.style.format({
                'Acciones_EEUU': '{:.4f}',
                'Precio_USD': '${:.2f}',
                'Total_USD': '${:.2f}'
            }), use_container_width=True)

        # Gráfico de barras de valorización
        st.divider()
        fig_bar = px.bar(df, x='Ticker', y='Total_USD', color='Ticker',
                         title="Valorización por Ticket (USD)", text_auto='.2s')
        st.plotly_chart(fig_bar, use_container_width=True)

    else:
        st.info("La tabla está conectada pero no tiene datos. Cargá tus activos en Airtable.")

except Exception as e:
    st.error(f"Ocurrió un error al procesar los datos: {e}")
