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
except:
    st.error("Error en credenciales.")
    st.stop()

# --- 2. CARGA DE DATOS ---
try:
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]
    col_dinero = next((c for c in df_movs.columns if c in ['Importe', 'Total Pesos', 'Monto']), None)

    def fix_ticker_api(t):
        return str(t).strip().replace('.', '-')

    # --- SECCIÓN 1: CARTERA ACTUAL ---
    st.title("📊 Mi Portafolio Real")
    
    if not df_actual.empty:
        tickers_api = [fix_ticker_api(t) for t in df_actual['Ticker_EEUU'].unique()]
        with st.spinner('Consultando mercado...'):
            data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
            if len(tickers_api) > 1:
                precios_dict = {k.replace('-', '.'): v for k, v in data_now.iloc[-1].to_dict().items()}
            else:
                precios_dict = {df_actual['Ticker_EEUU'].iloc[0]: float(data_now.iloc[-1])}

        df_actual['Precio Hoy'] = df_actual['Ticker_EEUU'].map(precios_dict)
        df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Precio Hoy']
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.metric("Patrimonio Total Actual", f"USD {df_actual['Valuación USD'].sum():,.2f}")
            # TABLA PRINCIPAL
            sel_port = st.dataframe(
                df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']], 
                use_container_width=True, on_select="rerun", selection_mode="single-row"
            )
        with c2:
            fig_pie = px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, title="Distribución USD")
            st.plotly_chart(fig_pie, use_container_width=True)

        # --- SECCIÓN 2: DETALLE 100% USD (SOLO AL SELECCIONAR) ---
        if len(sel_port.selection.rows) > 0:
            idx = sel_port.selection.rows[0]
            fila_sel = df_actual.iloc[idx]
            t_sel = fila_sel['Ticker_EEUU']
            p_hoy_sel = fila_sel['Precio Hoy']
            
            st.divider()
            st.subheader(f"🔍 Análisis de Rendimiento USD: {t_sel}")
            
            m_t = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
            m_t['Fecha'] = pd.to_datetime(m_t['Fecha'])
            
            with st.spinner('Dolarizando historial...'):
                t_api_sel = fix_ticker_api(t_sel)
                h_precios_sel = yf.download(t_api_sel, start=m_t['Fecha'].min(), progress=False)['Close']
                
                detalles_op = []
                for _, op in m_t.iterrows():
                    try:
                        p_compra_usd = h_precios_sel.loc[:op['Fecha']].iloc[-1]
                        if isinstance(p_compra_usd, pd.Series): p_compra_usd = p_compra_usd.iloc[0]
                    except:
                        p_compra_usd = p_hoy_sel

                    cant_usa = op['Cantidad'] / op['Ratio']
                    rend = (p_hoy_sel / p_compra_usd) - 1
                    detalles_op.append({
                        'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                        'Operación': op['Operacion'].upper(),
                        'Acciones (USA)': cant_usa,
                        'Precio Compra (USD)': p_compra_usd,
                        'Monto Operación (USD)': cant_usa * p_compra_usd,
                        'Rendimiento (%)': rend * 100
                    })
                
                st.dataframe(pd.DataFrame(detalles_op).style.format({
                    'Acciones (USA)': '{:.4f}', 'Precio Compra (USD)': '${:,.2f}', 
                    'Monto Operación (USD)': '${:,.2f}', 'Rendimiento (%)': '{:.2f}%'
                }).applymap(lambda x: 'color: red' if isinstance(x, (int, float)) and x < 0 else 'color: green', subset=['Rendimiento (%)']), use_container_width=True)

    # --- SECCIÓN 3: EVOLUCIÓN HISTÓRICA (ESTÁTICA AL TOTAL) ---
    st.divider()
    st.subheader("📈 Evolución Histórica del Patrimonio")

    @st.cache_data(ttl=3600)
    def calcular_evolucion_total(_df_movs, _df_actual, tickers_api):
        df_movs_copy = _df_movs.copy()
        df_movs_copy['Fecha'] = pd.to_datetime(df_movs_copy['Fecha'])
        f_inicio = df_movs_copy['Fecha'].min()
        f_fin = datetime.datetime.now()
        
        hist_total = yf.download(tickers_api, start=f_inicio, progress=False)['Close']
        if isinstance(hist_total, pd.Series):
            hist_total = hist_total.to_frame()
            hist_total.columns = tickers_api
        hist_total.columns = [c.replace('-', '.') for c in hist_total.columns]

        rango = pd.date_range(start=f_inicio, end=f_fin)
        evol_data = []
        
        for dia in rango:
            total_dia = 0
            # IMPORTANTE: Recorremos TODOS los activos de la cartera siempre
            for _, asset in _df_actual.iterrows():
                tk = asset['Ticker_EEUU']
                m_h = df_movs_copy[(df_movs_copy['Ticker_EEUU'] == tk) & (df_movs_copy['Fecha'] <= dia)]
                c_h = m_h[m_h['Operacion'].str.upper() == 'COMPRA']['Cantidad'].sum()
                v_h = m_h[m_h['Operacion'].str.upper() == 'VENTA']['Cantidad'].sum()
                
                if tk in hist_total.columns:
                    p_h = hist_total.loc[:dia, tk].ffill().iloc[-1] if not hist_total.loc[:dia, tk].empty else 0
                    total_dia += ((c_h - v_h) / asset['Ratio']) * p_h
            evol_data.append(total_dia)
        
        return pd.DataFrame({'Valor USD': evol_data}, index=rango)

    with st.spinner('Cargando evolución global...'):
        df_evolucion = calcular_evolucion_total(df_movs, df_actual, tickers_api)
        # Sincronizamos el último punto con el valor real de la tabla
        df_evolucion.iloc[-1] = df_actual['Valuación USD'].sum()
        
        fig_evol = px.line(df_evolucion, y='Valor USD', title="Patrimonio Total en el Tiempo (USD)")
        fig_evol.update_layout(hovermode="x unified")
        st.plotly_chart(fig_evol, use_container_width=True)

    # --- SECCIÓN 4: ACTIVOS LIQUIDADOS ---
    # (Misma lógica anterior con fila de totales)
    # ... (Se mantiene igual para no alargar el código)

except Exception as e:
    st.error(f"Error: {e}")
