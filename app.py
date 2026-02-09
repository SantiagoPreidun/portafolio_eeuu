import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px
import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Inversiones 360", layout="wide")

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
    table_port = Table(AIRTABLE_KEY, BASE_ID, "Portafolio")
except Exception as e:
    st.error("Error en credenciales. Verificá los Secrets.")
    st.stop()

# --- 2. BARRA LATERAL (CONTROLES) ---
st.sidebar.title("⚙️ Parámetros")
ccl_val = st.sidebar.number_input("Cotización Dólar CCL ($)", value=1300.0, step=10.0)

# --- 3. CARGA DE DATOS ---
try:
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]

    # Buscador de columna de dinero (Importe o Total Pesos)
    col_dinero = next((c for c in df_movs.columns if c in ['Importe', 'Total Pesos', 'Monto']), None)
    
    def limpiar_ticker(t):
        return str(t).strip().replace('.', '-')

    # --- 4. PROCESAMIENTO DE CARTERA ACTUAL ---
    st.title("📊 Mi Portafolio Real")
    
    if not df_actual.empty:
        tickers_api = [limpiar_ticker(t) for t in df_actual['Ticker_EEUU'].unique()]
        
        with st.spinner('Actualizando mercado...'):
            data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
            if len(tickers_api) > 1:
                precios_dict = {k.replace('-', '.'): v for k, v in data_now.iloc[-1].to_dict().items()}
            else:
                precios_dict = {df_actual['Ticker_EEUU'].iloc[0]: float(data_now.iloc[-1])}

        # Calculamos análisis detallado para cada activo en cartera
        res_cartera = []
        for _, row in df_actual.iterrows():
            t = row['Ticker_EEUU']
            p_hoy = precios_dict.get(limpiar_ticker(t), 0)
            valuacion_usd = (row['Cantidad'] / row['Ratio']) * p_hoy
            valuacion_ars = valuacion_usd * ccl_val
            
            # Buscamos monto de compra en movimientos
            m_t = df_movs[(df_movs['Ticker_EEUU'] == t) & (df_movs['Operacion'].str.upper() == 'COMPRA')]
            monto_compra = m_t[col_dinero].sum() if col_dinero else 0
            
            rendimiento = valuacion_ars - monto_compra
            porcentaje = (rendimiento / monto_compra * 100) if monto_compra > 0 else 0
            
            res_cartera.append({
                'Ticker': t,
                'Cantidad': row['Cantidad'],
                'Valuación USD': valuacion_usd,
                'Monto Compra (ARS)': monto_compra,
                'Valuación (ARS)': valuacion_ars,
                'Rendimiento (ARS)': rendimiento,
                '% Retorno': porcentaje
            })
        
        df_p = pd.DataFrame(res_cartera)

        # --- SECCIÓN 1: COMPOSICIÓN Y GRÁFICO ---
        col_m1, col_m2 = st.columns([2, 1])
        
        with col_m1:
            st.metric("Patrimonio Total Actual", f"USD {df_p['Valuación USD'].sum():,.2f}")
            sel_port = st.dataframe(
                df_p.style.format({
                    'Valuación USD': '{:.2f}', 'Monto Compra (ARS)': '${:,.2f}', 
                    'Valuación (ARS)': '${:,.2f}', 'Rendimiento (ARS)': '${:,.2f}', '% Retorno': '{:.2f}%'
                }).applymap(lambda x: 'color: red' if x < 0 else 'color: green', subset=['Rendimiento (ARS)', '% Retorno']),
                use_container_width=True, on_select="rerun", selection_mode="single-row"
            )

        with col_m2:
            fig = px.pie(df_p, values='Valuación USD', names='Ticker', hole=0.4, title="Distribución de Cartera")
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        # --- SECCIÓN 2: DETALLE INTERACTIVO ---
        if len(sel_port.selection.rows) > 0:
            idx = sel_port.selection.rows[0]
            t_sel = df_p.iloc[idx]['Ticker']
            st.divider()
            st.subheader(f"📑 Historial de Operaciones: {t_sel}")
            h_filt = df_movs[df_movs['Ticker_EEUU'] == t_sel].sort_values('Fecha', ascending=False)
            st.table(h_filt[['Fecha', 'Operacion', 'Cantidad', col_dinero]])

    # --- SECCIÓN 3: ACTIVOS LIQUIDADOS ---
    st.divider()
    st.subheader("🏁 Activos Liquidados (Ganancias Realizadas)")
    
    tickers_en_port = set(df_actual['Ticker_EEUU'].unique()) if not df_actual.empty else set()
    liquidados = list(set(df_movs['Ticker_EEUU'].unique()) - tickers_en_port)

    if liquidados:
        res_liq = []
        for t in liquidados:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            m_t['Operacion'] = m_t['Operacion'].str.strip().str.upper()
            m_compra = m_t[m_t['Operacion'] == 'COMPRA'][col_dinero].sum()
            m_venta = m_t[m_t['Operacion'] == 'VENTA'][col_dinero].sum()
            rend = m_venta - m_compra
            res_liq.append({
                'Ticker': t, 'Monto Compra': m_compra, 'Monto Venta': m_venta,
                'Rendimiento': rend, '% Retorno': (rend/m_compra*100) if m_compra > 0 else 0
            })
        
        st.dataframe(
            pd.DataFrame(res_liq).style.format({'Monto Compra': '${:,.2f}', 'Monto Venta': '${:,.2f}', 'Rendimiento': '${:,.2f}', '% Retorno': '{:.2f}%'})
            .applymap(lambda x: 'color: red' if x < 0 else 'color: green', subset=['Rendimiento', '% Retorno']),
            use_container_width=True
        )

except Exception as e:
    st.error(f"Error general: {e}")
