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

    # --- SECCIÓN 1 Y 2 (Tus favoritas del código anterior) ---
    st.title("📊 Mi Portafolio Real")
    
    if not df_actual.empty:
        tickers_api = [fix_ticker_api(t) for t in df_actual['Ticker_EEUU'].unique()]
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
            sel_port = st.dataframe(df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']], 
                                    use_container_width=True, on_select="rerun", selection_mode="single-row")
        with c2:
            fig_pie = px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, title="Distribución USD")
            st.plotly_chart(fig_pie, use_container_width=True)

        if len(sel_port.selection.rows) > 0:
            idx = sel_port.selection.rows[0]
            t_sel = df_actual.iloc[idx]['Ticker_EEUU']
            st.divider()
            st.subheader(f"🔍 Historial: {t_sel}")
            m_t = df_movs[df_movs['Ticker_EEUU'] == t_sel].sort_values('Fecha', ascending=False)
            st.table(m_t[['Fecha', 'Operacion', 'Cantidad', col_dinero]])

    # --- NUEVA SECCIÓN: EVOLUCIÓN HISTÓRICA DE CARTERA ACTIVA ---
    st.divider()
    st.subheader("📈 Evolución de Cartera Activa (USD)")

    with st.spinner('Reconstruyendo historial de precios...'):
        # 1. Definir rango de fechas (desde la primera compra hasta hoy)
        df_movs['Fecha'] = pd.to_datetime(df_movs['Fecha'])
        fecha_inicio = df_movs['Fecha'].min()
        fecha_fin = datetime.datetime.now()
        
        # 2. Obtener precios históricos de todos los tickers activos
        hist_precios = yf.download(tickers_api, start=fecha_inicio, end=fecha_fin, progress=False)['Close']
        if len(tickers_api) == 1:
            hist_precios = hist_precios.to_frame()
            hist_precios.columns = tickers_api

        # 3. Crear DataFrame diario de tenencia
        rango_dias = pd.date_range(start=fecha_inicio, end=fecha_fin)
        evolucion = pd.DataFrame(index=rango_dias)
        
        valor_diario_total = []
        for dia in rango_dias:
            total_dia = 0
            for _, row in df_actual.iterrows():
                # Cuántos nominales tenías a esa fecha según Movimientos
                movs_hasta_hoy = df_movs[(df_movs['Ticker_EEUU'] == row['Ticker_EEUU']) & (df_movs['Fecha'] <= dia)]
                cant_a_fecha = 0
                for _, m in movs_hasta_hoy.iterrows():
                    if m['Operacion'].upper() == 'COMPRA': cant_a_fecha += m['Cantidad']
                    else: cant_a_fecha -= m['Cantidad']
                
                # Buscar precio histórico más cercano
                t_api = fix_ticker_api(row['Ticker_EEUU'])
                if t_api in hist_precios.columns:
                    precio_h = hist_precios.loc[:dia, t_api].iloc[-1] if not hist_precios.loc[:dia, t_api].empty else 0
                    total_dia += (cant_a_fecha / row['Ratio']) * precio_h
            
            valor_diario_total.append(total_dia)
        
        evolucion['Valor Cartera USD'] = valor_diario_total
        
        # 4. Graficar
        fig_evol = px.line(evolucion, y='Valor Cartera USD', title="Valor Histórico del Portafolio en Dólares",
                           labels={'index': 'Fecha', 'Valor Cartera USD': 'USD Total'})
        fig_evol.update_traces(line_color='#00CC96')
        st.plotly_chart(fig_evol, use_container_width=True)

    # --- SECCIÓN 3: ACTIVOS LIQUIDADOS ---
    st.divider()
    st.subheader("🏁 Activos Liquidados")
    tickers_port = set(df_actual['Ticker_EEUU'].unique()) if not df_actual.empty else set()
    liquidados = list(set(df_movs['Ticker_EEUU'].unique()) - tickers_port)
    if liquidados:
        res_liq = []
        for t in liquidados:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            c = m_t[m_t['Operacion'].str.upper() == 'COMPRA'][col_dinero].sum()
            v = m_t[m_t['Operacion'].str.upper() == 'VENTA'][col_dinero].sum()
            rend = v - c
            res_liq.append({'Ticker': t, 'Monto Compra': c, 'Monto Venta': v, 'Rendimiento': rend, '% Retorno': (rend/c*100) if c > 0 else 0})
        st.dataframe(pd.DataFrame(res_liq).style.format({'Monto Compra': '${:,.2f}', 'Monto Venta': '${:,.2f}', 'Rendimiento': '${:,.2f}', '% Retorno': '{:.2f}%'}))

except Exception as e:
    st.error(f"Error: {e}")
