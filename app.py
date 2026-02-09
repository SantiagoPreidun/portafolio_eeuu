import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Portafolio 360", layout="wide")

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
    table_port = Table(AIRTABLE_KEY, BASE_ID, "Portafolio")
except Exception as e:
    st.error("Error en Secrets. Verificá tus credenciales.")
    st.stop()

# --- 2. CARGA Y LIMPIEZA DE DATOS ---
try:
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]

    # Precios Hoy
    tickers_activos = df_actual['Ticker_EEUU'].unique().tolist()
    data_now = yf.download([t.replace('.', '-') for t in tickers_activos], period="1d", progress=False)['Close']
    
    if len(tickers_activos) > 1:
        dict_precios = data_now.iloc[-1].to_dict()
        dict_precios = {k.replace('-', '.'): v for k, v in dict_precios.items()}
    else:
        dict_precios = {tickers_activos[0]: float(data_now.iloc[-1])}

    # --- SECCIÓN 1: COMPOSICIÓN ACTUAL ---
    st.title("📊 Mi Portafolio Actual")
    df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Ticker_EEUU'].map(dict_precios)
    
    st.metric("Patrimonio Total", f"USD {df_actual['Valuación USD'].sum():,.2f}")
    
    sel_port = st.dataframe(
        df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD']],
        use_container_width=True, on_select="rerun", selection_mode="single-row"
    )

    # --- SECCIÓN 2: DETALLE INTERACTIVO ---
    st.divider()
    if len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        t_sel = df_actual.iloc[idx]['Ticker_EEUU']
        st.subheader(f"📑 Historial de Movimientos: {t_sel}")
        hist_filt = df_movs[df_movs['Ticker_EEUU'] == t_sel].sort_values('Fecha', ascending=False)
        st.table(hist_filt[['Fecha', 'Operacion', 'Cantidad', 'Total Pesos']])
    else:
        st.info("Seleccioná un activo arriba para ver su historial.")

    # --- SECCIÓN 3: ACTIVOS LIQUIDADOS (POSICIONES CERRADAS) ---
    st.divider()
    st.subheader("🏁 Activos Liquidados (Ganancias Realizadas)")
    
    # Buscamos activos que están en Movimientos pero NO en Portafolio
    tickers_en_movs = set(df_movs['Ticker_EEUU'].unique())
    tickers_en_port = set(df_actual['Ticker_EEUU'].unique())
    liquidados = list(tickers_en_movs - tickers_en_port)

    if liquidados:
        res_liq = []
        for t in liquidados:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t]
            # Calculamos balance final de la operación
            compras = m_t[m_t['Operacion'].str.upper() == 'COMPRA']['Total Pesos'].sum()
            ventas = m_t[m_t['Operacion'].str.upper() == 'VENTA']['Total Pesos'].sum()
            balance_pesos = ventas - compras
            
            res_liq.append({
                'Ticker': t,
                'Total Invertido (ARS)': compras,
                'Total Recuperado (ARS)': ventas,
                'Resultado Final (ARS)': balance_pesos
            })
        
        df_liq = pd.DataFrame(res_liq)
        st.dataframe(df_liq.style.format({
            'Total Invertido (ARS)': '${:,.2f}',
            'Total Recuperado (ARS)': '${:,.2f}',
            'Resultado Final (ARS)': '${:,.2f}'
        }), use_container_width=True)
    else:
        st.write("No tenés posiciones totalmente cerradas aún.")

except Exception as e:
    st.error(f"Error: {e}")
