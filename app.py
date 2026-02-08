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

# --- 2. BARRA LATERAL (CONTROLES INTERACTIVOS) ---
st.sidebar.title("⚙️ Panel de Control")
st.sidebar.markdown("Configurá la comparativa histórica")

periodo = st.sidebar.selectbox(
    "Seleccioná el periodo:", 
    ["1mo", "3mo", "6mo", "1y", "2y", "5y"], 
    index=2
)

benchmarks_dict = {
    "S&P 500 (SPY)": "SPY",
    "Nasdaq 100 (QQQ)": "QQQ",
    "Oro (GLD)": "GLD"
}

seleccionados = st.sidebar.multiselect(
    "Comparar mi cartera contra:", 
    options=list(benchmarks_dict.keys()),
    default=["S&P 500 (SPY)"]
)

# --- 3. PROCESAMIENTO DE DATOS ACTUALES ---
st.title("📈 Mi Portafolio: Nexo CEDEAR -> Wall Street")

try:
    records = table.all()
    if records:
        df = pd.DataFrame([r['fields'] for r in records])
        
        # Descarga de precios actuales
        tickers_eeuu = df['Ticker_EEUU'].unique().tolist()
        with st.spinner('Consultando Wall Street...'):
            data_now = yf.download(tickers_eeuu, period="1d", auto_adjust=True)
            if len(tickers_eeuu) > 1:
                precios_hoy = data_now['Close'].iloc[-1].to_dict()
            else:
                precios_hoy = {tickers_eeuu[0]: float(data_now['Close'].iloc[-1])}

        # Cálculos del Nexo
        df['Acciones_EEUU'] = df['Cantidad'] / df['Ratio']
        df['Precio_USD'] = df['Ticker_EEUU'].map(precios_hoy)
        df['Total_USD'] = df['Acciones_EEUU'] * df['Precio_USD']
        
        # Dashboard Principal
        total_cartera = df['Total_USD'].sum()
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.metric("Patrimonio Total", f"USD {total_cartera:,.2f}")
            fig_pie = px.pie(df, values='Total_USD', names='Ticker Argy', 
                             hole=0.4, title="Distribución de Capital")
            st.plotly_chart(fig_pie, use_container_width=True)

        with c2:
            st.subheader("📋 Desglose de Activos")
            cols_ver = ['Ticker Argy', 'Descripción', 'Cantidad', 'Ratio', 'Acciones_EEUU', 'Ticker_EEUU', 'Precio_USD', 'Total_USD']
            st.dataframe(df[cols_ver].style.format({
                'Acciones_EEUU': '{:.4f}', 'Precio_USD': '${:.2f}', 'Total_USD': '${:.2f}'
            }), use_container_width=True)

        st.divider()

        # --- 4. SECCIÓN INTERACTIVA: COMPARATIVA HISTÓRICA ---
        st.subheader(f"📊 Rendimiento Histórico ({periodo})")
        
        with st.spinner('Calculando evolución comparativa...'):
            # Lista de tickers: Mis activos + Benchmarks elegidos
            tickers_bench = [benchmarks_dict[s] for s in seleccionados]
            lista_full = list(set(tickers_eeuu + tickers_bench))
            
            historial = yf.download(lista_full, period=periodo)['Close'].ffill()

            # Calcular valor diario de la cartera del usuario
            valor_diario = 0
            for _, row in df.iterrows():
                t = row['Ticker_EEUU']
                cant = row['Cantidad'] / row['Ratio']
                valor_diario += historial[t] * cant
            
            # DataFrame para el gráfico (Base 100)
            df_comp = pd.DataFrame(index=historial.index)
            df_comp['Mi Cartera'] = (valor_diario / valor_diario.iloc[0]) * 100
            
            for s in seleccionados:
                ticker_b = benchmarks_dict[s]
                df_comp[s] = (historial[ticker_b] / historial[ticker_b].iloc[0]) * 100

            # Gráfico interactivo
            fig_hist = px.line(
                df_comp, 
                y=df_comp.columns,
                labels={'value': 'Evolución (Base 100)', 'Date': 'Fecha'},
                title="¿Quién ganó? (Evolución de $100 invertidos)"
            )
            fig_hist.update_layout(hovermode="x unified")
            st.plotly_chart(fig_hist, use_container_width=True)

    else:
        st.info("Cargá datos en Airtable para ver el análisis.")

except Exception as e:
    st.error(f"Error técnico: {e}")
