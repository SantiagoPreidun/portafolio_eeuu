import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Inversiones 360", layout="wide")

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
    table_port = Table(AIRTABLE_KEY, BASE_ID, "Portafolio")
except:
    st.error("Error en credenciales.")
    st.stop()

# --- 2. CARGA DE DATOS ---
try:
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]

    # Buscador de columna de dinero
    col_dinero = next((c for c in df_movs.columns if c in ['Importe', 'Total Pesos', 'Monto']), None)

    def limpiar_ticker(t):
        return str(t).strip().replace('.', '-')

    # --- 3. SECCIÓN 1: CARTERA EN USD ---
    st.title("📊 Composición de mi Portafolio")
    
    if not df_actual.empty:
        tickers_api = [limpiar_ticker(t) for t in df_actual['Ticker_EEUU'].unique()]
        data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
        
        if len(tickers_api) > 1:
            precios_dict = {k.replace('-', '.'): v for k, v in data_now.iloc[-1].to_dict().items()}
        else:
            precios_dict = {df_actual['Ticker_EEUU'].iloc[0]: float(data_now.iloc[-1])}

        df_actual['Precio Hoy'] = df_actual['Ticker_EEUU'].apply(lambda x: precios_dict.get(limpiar_ticker(x)))
        df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Precio Hoy']
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.metric("Patrimonio Total Actual", f"USD {df_actual['Valuación USD'].sum():,.2f}")
            sel_port = st.dataframe(
                df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']],
                use_container_width=True, on_select="rerun", selection_mode="single-row"
            )
        with c2:
            fig = px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, title="Distribución USD")
            st.plotly_chart(fig, use_container_width=True)

        # --- SECCIÓN 2: ANÁLISIS DE OPERACIONES (DETALLE) ---
        if len(sel_port.selection.rows) > 0:
            idx = sel_port.selection.rows[0]
            t_sel = df_actual.iloc[idx]['Ticker_EEUU']
            v_usd_sel = df_actual.iloc[idx]['Valuación USD']
            
            st.divider()
            st.subheader(f"🔍 Análisis de Posición: {t_sel}")
            
            # Cálculo de rendimiento similar a sección 3
            m_t = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
            m_t['Operacion'] = m_t['Operacion'].str.strip().str.upper()
            
            m_compra = m_t[m_t['Operacion'] == 'COMPRA'][col_dinero].sum()
            m_venta = m_t[m_t['Operacion'] == 'VENTA'][col_dinero].sum()
            costo_neto = m_compra - m_venta # Lo que realmente "quedó" invertido
            
            # Mostramos cuadro de rentabilidad
            st.write(f"Historial de movimientos para {t_sel}:")
            st.table(m_t[['Fecha', 'Operacion', 'Cantidad', col_dinero]].sort_values('Fecha', ascending=False))
            
    # --- SECCIÓN 3: ACTIVOS LIQUIDADOS ---
    st.divider()
    st.subheader("🏁 Activos Liquidados (Ganancias Realizadas)")
    
    tickers_port = set(df_actual['Ticker_EEUU'].unique()) if not df_actual.empty else set()
    liquidados = list(set(df_movs['Ticker_EEUU'].unique()) - tickers_port)

    if liquidados:
        res_liq = []
        for t in liquidados:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            m_t['Operacion'] = m_t['Operacion'].str.strip().str.upper()
            compra = m_t[m_t['Operacion'] == 'COMPRA'][col_dinero].sum()
            venta = m_t[m_t['Operacion'] == 'VENTA'][col_dinero].sum()
            rend = venta - compra
            res_liq.append({
                'Ticker': t, 'Monto Compra': compra, 'Monto Venta': venta,
                'Rendimiento': rend, '% Retorno': (rend/compra*100) if compra > 0 else 0
            })
        
        st.dataframe(
            pd.DataFrame(res_liq).style.format({'Monto Compra': '${:,.2f}', 'Monto Venta': '${:,.2f}', 'Rendimiento': '${:,.2f}', '% Retorno': '{:.2f}%'})
            .applymap(lambda x: 'color: red' if x < 0 else 'color: green', subset=['Rendimiento', '% Retorno']),
            use_container_width=True
        )

except Exception as e:
    st.error(f"Error: {e}")
