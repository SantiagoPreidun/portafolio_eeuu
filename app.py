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

    # --- SECCIÓN: EVOLUCIÓN HISTÓRICA SINCRONIZADA ---
    st.divider()
    st.subheader("📈 Evolución de Cartera Activa (USD)")

    with st.spinner('Sincronizando historial con valor actual...'):
        df_movs['Fecha'] = pd.to_datetime(df_movs['Fecha'])
        fecha_inicio = df_movs['Fecha'].min()
        fecha_fin = datetime.datetime.now()
        
        # Descarga masiva
        hist_precios = yf.download(tickers_api, start=fecha_inicio, end=fecha_fin, progress=False)['Close']
        
        # Si es un solo ticker, yfinance devuelve una Serie, la pasamos a DataFrame
        if isinstance(hist_precios, pd.Series):
            hist_precios = hist_precios.to_frame()
            hist_precios.columns = [tickers_api[0]]
        
        # Limpiamos los nombres de las columnas del historial (de BRK-B a BRK.B)
        hist_precios.columns = [c.replace('-', '.') for c in hist_precios.columns]

        rango_dias = pd.date_range(start=fecha_inicio, end=fecha_fin)
        valor_diario_total = []
        
        for dia in rango_dias:
            total_dia = 0
            for _, row in df_actual.iterrows():
                t = row['Ticker_EEUU']
                # Cantidad neta a esa fecha
                m_h = df_movs[(df_movs['Ticker_EEUU'] == t) & (df_movs['Fecha'] <= dia)]
                c_h = m_h[m_h['Operacion'].str.upper() == 'COMPRA']['Cantidad'].sum()
                v_h = m_h[m_h['Operacion'].str.upper() == 'VENTA']['Cantidad'].sum()
                tenencia_dia = (c_h - v_h)
                
                if t in hist_precios.columns:
                    # Buscamos el precio de ese día o el anterior más cercano (ffill)
                    precios_hasta_dia = hist_precios.loc[:dia, t]
                    if not precios_hasta_dia.empty:
                        precio_h = precios_hasta_dia.iloc[-1]
                        if pd.isna(precio_h): # Si es un feriado, buscamos hacia atrás
                             precio_h = precios_hasta_dia.ffill().iloc[-1]
                        total_dia += (tenencia_dia / row['Ratio']) * precio_h
            
            valor_diario_total.append(total_dia)
        
        evolucion = pd.DataFrame(index=rango_dias)
        evolucion['Valor USD'] = valor_diario_total
        
        # FORZAMOS EL ÚLTIMO PUNTO: 
        # Si hoy el mercado está cerrado, el último valor del gráfico debe ser igual al Patrimonio Total
        evolucion.iloc[-1, evolucion.columns.get_loc('Valor USD')] = df_actual['Valuación USD'].sum()

        fig_evol = px.line(evolucion, y='Valor USD', title="Evolución del Patrimonio (Base Cierres Diarios)")
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
