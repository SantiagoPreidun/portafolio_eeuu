import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px
import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Dashboard Inversiones 360", layout="wide")

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
    table_port = Table(AIRTABLE_KEY, BASE_ID, "Portafolio")
except Exception as e:
    st.error("Error en las credenciales de Airtable. Revisá tus Secrets.")
    st.stop()

# --- 2. CARGA DE DATOS ---
try:
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    
    # Limpieza de nombres de columnas
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]
    
    # Buscador de columna de dinero (Importe es el prioritario según tus capturas)
    col_dinero = next((c for c in df_movs.columns if c in ['Importe', 'Total Pesos', 'Monto']), None)

    def fix_ticker_api(t):
        return str(t).strip().replace('.', '-')

    # --- SECCIÓN 1: COMPOSICIÓN ACTUAL (USD) ---
    st.title("📊 Mi Portafolio Real")
    
    if not df_actual.empty:
        tickers_api = [fix_ticker_api(t) for t in df_actual['Ticker_EEUU'].unique()]
        
        with st.spinner('Actualizando precios de mercado...'):
            data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
            if len(tickers_api) > 1:
                precios_dict = {k.replace('-', '.'): v for k, v in data_now.iloc[-1].to_dict().items()}
            else:
                precios_dict = {df_actual['Ticker_EEUU'].iloc[0]: float(data_now.iloc[-1])}

        df_actual['Precio Hoy'] = df_actual['Ticker_EEUU'].map(precios_dict)
        df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Precio Hoy']
        
        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            st.metric("Patrimonio Total Actual", f"USD {df_actual['Valuación USD'].sum():,.2f}")
            sel_port = st.dataframe(
                df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']],
                use_container_width=True, on_select="rerun", selection_mode="single-row"
            )
        with col_t2:
            fig_pie = px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, title="Distribución por Activo")
            st.plotly_chart(fig_pie, use_container_width=True)

        # --- SECCIÓN 2: DETALLE DE OPERACIONES (DRILL-DOWN) ---
        if len(sel_port.selection.rows) > 0:
            idx = sel_port.selection.rows[0]
            t_sel = df_actual.iloc[idx]['Ticker_EEUU']
            st.divider()
            st.subheader(f"🔍 Historial Detallado: {t_sel}")
            m_t = df_movs[df_movs['Ticker_EEUU'] == t_sel].sort_values('Fecha', ascending=False)
            st.table(m_t[['Fecha', 'Operacion', 'Cantidad', col_dinero]])

    # --- SECCIÓN 3: EVOLUCIÓN HISTÓRICA ---
    st.divider()
    st.subheader("📈 Evolución de la Cartera Activa")
    
    with st.spinner('Calculando línea de tiempo...'):
        df_movs['Fecha'] = pd.to_datetime(df_movs['Fecha'])
        f_inicio = df_movs['Fecha'].min()
        hist_prices = yf.download(tickers_api, start=f_inicio, progress=False)['Close']
        if isinstance(hist_prices, pd.Series):
            hist_prices = hist_prices.to_frame()
            hist_prices.columns = [tickers_api[0]]
        hist_prices.columns = [c.replace('-', '.') for c in hist_prices.columns]

        rango = pd.date_range(start=f_inicio, end=datetime.datetime.now())
        vals_diarios = []
        for dia in rango:
            suma_dia = 0
            for _, row in df_actual.iterrows():
                tick = row['Ticker_EEUU']
                m_h = df_movs[(df_movs['Ticker_EEUU'] == tick) & (df_movs['Fecha'] <= dia)]
                c_h = m_h[m_h['Operacion'].str.upper() == 'COMPRA']['Cantidad'].sum()
                v_h = m_h[m_h['Operacion'].str.upper() == 'VENTA']['Cantidad'].sum()
                if tick in hist_prices.columns:
                    p_h = hist_prices.loc[:dia, tick].ffill().iloc[-1] if not hist_prices.loc[:dia, tick].empty else 0
                    suma_dia += ((c_h - v_h) / row['Ratio']) * p_h
            vals_diarios.append(suma_dia)
        
        df_evol = pd.DataFrame({'USD': vals_diarios}, index=rango)
        df_evol.iloc[-1] = df_actual['Valuación USD'].sum() # Sincronización final
        st.plotly_chart(px.line(df_evol, y='USD', title="Crecimiento del Patrimonio"), use_container_width=True)

    # --- SECCIÓN 4: ACTIVOS LIQUIDADOS CON TOTALES ---
    st.divider()
    st.subheader("🏁 Activos Liquidados (Ganancias Realizadas)")
    
    t_port = set(df_actual['Ticker_EEUU'].unique()) if not df_actual.empty else set()
    t_liq = list(set(df_movs['Ticker_EEUU'].unique()) - t_port)

    if t_liq:
        res_liq = []
        for t in t_liq:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            m_t['Operacion'] = m_t['Operacion'].str.strip().str.upper()
            c = m_t[m_t['Operacion'] == 'COMPRA'][col_dinero].sum()
            v = m_t[m_t['Operacion'] == 'VENTA'][col_dinero].sum()
            rend = v - c
            res_liq.append({'Ticker': t, 'Monto Compra': c, 'Monto Venta': v, 'Rendimiento': rend, '% Retorno': (rend/c*100) if c > 0 else 0})
        
        df_l = pd.DataFrame(res_liq)
        # Fila de Totales
        tot_c = df_l['Monto Compra'].sum()
        tot_v = df_l['Monto Venta'].sum()
        tot_r = tot_v - tot_c
        df_total = pd.DataFrame([{'Ticker': 'TOTAL GLOBAL', 'Monto Compra': tot_c, 'Monto Venta': tot_v, 'Rendimiento': tot_r, '% Retorno': (tot_r/tot_c*100) if tot_c > 0 else 0}])
        df_l_final = pd.concat([df_l, df_total], ignore_index=True)

        st.dataframe(
            df_l_final.style.format({'Monto Compra': '${:,.2f}', 'Monto Venta': '${:,.2f}', 'Rendimiento': '${:,.2f}', '% Retorno': '{:.2f}%'})
            .apply(lambda x: ['font-weight: bold; background-color: #333' if x['Ticker'] == 'TOTAL GLOBAL' else '' for _ in x], axis=1)
            .applymap(lambda x: 'color: red' if isinstance(x, (int, float)) and x < 0 else ('color: green' if isinstance(x, (int, float)) and x > 0 else ''), subset=['Rendimiento', '% Retorno']),
            use_container_width=True
        )
    else:
        st.info("No hay posiciones cerradas.")

except Exception as e:
    st.error(f"Se produjo un error en la ejecución: {e}")
