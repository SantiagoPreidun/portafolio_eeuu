import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Inversiones 360", layout="wide")

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
    table_port = Table(AIRTABLE_KEY, BASE_ID, "Portafolio")
except Exception as e:
    st.error("Error en Secrets. Verificá tus credenciales.")
    st.stop()

# --- 2. CARGA DE DATOS ---
try:
    # Traemos datos de Airtable
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    
    # Limpieza de nombres de columnas (trim de espacios)
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]

    # --- FIX DE TICKERS (BRK.B -> BRK-B) ---
    def limpiar_ticker(t):
        return str(t).strip().replace('.', '-')

    tickers_port = df_actual['Ticker_EEUU'].unique().tolist()
    # Limpiamos los tickers para la API de Yahoo
    tickers_api = [limpiar_ticker(t) for t in tickers_port]
    
    with st.spinner('Consultando Wall Street...'):
        data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
        
        # Mapeo de precios (manejo de ticker único o múltiple)
        if len(tickers_api) > 1:
            precios_dict = data_now.iloc[-1].to_dict()
        else:
            precios_dict = {tickers_api[0]: float(data_now.iloc[-1])}

    # --- SECCIÓN 1: COMPOSICIÓN ACTUAL ---
    st.title("📊 Composición de mi Portafolio")
    
    # Mapeamos el precio usando el ticker limpio
    df_actual['Precio Hoy'] = df_actual['Ticker_EEUU'].apply(lambda x: precios_dict.get(limpiar_ticker(x)))
    df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Precio Hoy']
    
    st.metric("Patrimonio Total Actual", f"USD {df_actual['Valuación USD'].sum():,.2f}")

    # Tabla interactiva (Solo lo que tenés hoy)
    sel_port = st.dataframe(
        df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']],
        use_container_width=True, on_select="rerun", selection_mode="single-row"
    )

    # --- SECCIÓN 2: DETALLE INTERACTIVO ---
    st.divider()
    if len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        t_sel = df_actual.iloc[idx]['Ticker_EEUU']
        st.subheader(f"📑 Historial de Movimientos: {t_sel}")
        
        hist_filt = df_movs[df_movs['Ticker_EEUU'] == t_sel].sort_values('Fecha', ascending=False)
        st.table(hist_filt[['Fecha', 'Operacion', 'Cantidad', 'Ratio', 'Total Pesos']])
    else:
        st.info("💡 Hacé clic en una fila del portafolio para ver sus compras y ventas aquí.")

    # --- SECCIÓN 3: ACTIVOS LIQUIDADOS ---
    st.divider()
    st.subheader("🏁 Activos Liquidados (Posiciones Cerradas)")
    
    tickers_en_movs = set(df_movs['Ticker_EEUU'].unique())
    tickers_en_port = set(df_actual['Ticker_EEUU'].unique())
    # Activos que vendiste todo y ya no están en el portafolio
    liquidados = list(tickers_en_movs - tickers_en_port)

    if liquidados:
        res_liq = []
        for t in liquidados:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t]
            compras = m_t[m_t['Operacion'].str.upper() == 'COMPRA']['Total Pesos'].sum()
            ventas = m_t[m_t['Operacion'].str.upper() == 'VENTA']['Total Pesos'].sum()
            res_liq.append({
                'Ticker': t,
                'Inversión Total (ARS)': compras,
                'Retorno Total (ARS)': ventas,
                'P&L Final (ARS)': ventas - compras
            })
        
        st.dataframe(pd.DataFrame(res_liq).style.format({'P&L Final (ARS)': '${:,.2f}'}), use_container_width=True)
    else:
        st.write("No hay posiciones cerradas por el momento.")

except Exception as e:
    st.error(f"Error: {e}")
