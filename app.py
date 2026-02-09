import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import datetime
import plotly.express as px

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Gestor de Portafolio Pro", layout="wide")

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
    table_port = Table(AIRTABLE_KEY, BASE_ID, "Portafolio")
except Exception as e:
    st.error(f"Error en credenciales: {e}")
    st.stop()

# --- 2. FUNCIÓN DE PRECIO HISTÓRICO ---
@st.cache_data(ttl=3600)
def get_hist_price(ticker, fecha_str):
    try:
        t = ticker.replace('.', '-')
        start = datetime.datetime.strptime(fecha_str, "%Y-%m-%d")
        end = start + datetime.timedelta(days=5)
        data = yf.download(t, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), progress=False)
        if not data.empty:
            close_col = data['Close']
            return float(close_col.iloc[0, 0]) if isinstance(close_col, pd.DataFrame) else float(close_col.iloc[0])
    except: return None
    return None

# --- 3. PROCESAMIENTO PRINCIPAL ---
try:
    # Carga de Datos
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    
    # Limpieza de nombres
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]

    st.title("📈 Mi Portafolio Real")

    with st.spinner('Actualizando cotizaciones y calculando PPP...'):
        res_portfolio = []
        for _, row in df_actual.iterrows():
            ticker = row['Ticker_EEUU']
            cant_actual = row['Cantidad']
            ratio = row['Ratio']
            
            # Filtramos movimientos de este ticker
            m_ticker = df_movs[df_movs['Ticker_EEUU'] == ticker]
            
            # Cálculo de PPP (solo compras)
            m_compras = m_ticker[m_ticker['Operacion'].str.upper() == 'COMPRA']
            costo_usd_total = 0
            acc_acum = 0
            for _, m in m_compras.iterrows():
                p_h = get_hist_price(ticker, str(m['Fecha']))
                if p_h:
                    a_h = m['Cantidad'] / m['Ratio']
                    costo_usd_total += (a_h * p_h)
                    acc_acum += a_h
            
            ppp_usd = costo_usd_total / acc_acum if acc_acum > 0 else 0
            
            # Precio Actual
            p_hoy = yf.download(ticker.replace('.', '-'), period="1d", progress=False)['Close'].iloc[-1]
            p_hoy = float(p_hoy.iloc[0]) if isinstance(p_hoy, pd.Series) else float(p_hoy)
            
            res_portfolio.append({
                'Ticker': ticker,
                'Cant. CEDEAR': cant_actual,
                'PPP USD': ppp_usd,
                'Precio Hoy': p_hoy,
                'Valuación USD': (cant_actual / ratio) * p_hoy,
                'Rendimiento %': ((p_hoy / ppp_usd) - 1) * 100 if ppp_usd > 0 else 0
            })

        df_final = pd.DataFrame(res_portfolio)

    # --- 4. DASHBOARD SUPERIOR ---
    total_usd = df_final['Valuación USD'].sum()
    st.metric("Patrimonio Total Actual", f"USD {total_usd:,.2f}")

    # Tabla Principal (Habilitamos selección)
    st.subheader("📋 Tenencia Actual")
    event = st.dataframe(
        df_final.style.format({
            'PPP USD': '{:.2f}', 'Precio Hoy': '{:.2f}', 
            'Valuación USD': '{:.2f}', 'Rendimiento %': '{:.2f}%'
        }),
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # --- 5. CUADRO DE OPERACIONES FILTRADO (INTERACTIVO) ---
    st.divider()
    
    # Verificamos si hay una fila seleccionada
    if len(event.selection.rows) > 0:
        index_sel = event.selection.rows[0]
        ticker_sel = df_final.iloc[index_sel]['Ticker']
        
        st.subheader(f"🕒 Historial de Operaciones: {ticker_sel}")
        
        # Filtramos los movimientos originales por el ticker seleccionado
        historial_especifico = df_movs[df_movs['Ticker_EEUU'] == ticker_sel].sort_values('Fecha', ascending=False)
        
        st.table(historial_especifico[['Fecha', 'Operacion', 'Cantidad', 'Ratio', 'Total Pesos']])
    else:
        st.info("💡 Hacé clic en la fila de un activo arriba para ver su historial de compras y ventas aquí debajo.")

except Exception as e:
    st.error(f"Error en la aplicación: {e}")
