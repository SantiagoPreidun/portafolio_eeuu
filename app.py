import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import datetime
import plotly.express as px

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Dashboard de Inversiones", layout="wide")

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
except Exception as e:
    st.error(f"❌ Error de configuración: {e}")
    st.stop()

# --- 2. FUNCIONES DE CÁLCULO ---

@st.cache_data(ttl=3600)
def obtener_precio_h(ticker, fecha_str):
    try:
        t_api = ticker.replace('.', '-')
        start = datetime.datetime.strptime(fecha_str, "%Y-%m-%d")
        end = start + datetime.timedelta(days=5)
        data = yf.download(t_api, start=start.strftime("%Y-%m-%d"), 
                           end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if not data.empty:
            close_col = data['Close']
            return float(close_col.iloc[0, 0]) if isinstance(close_col, pd.DataFrame) else float(close_col.iloc[0])
    except:
        return None
    return None

def procesar_datos(records):
    df = pd.DataFrame([r['fields'] for r in records])
    df.columns = [c.strip() for c in df.columns]
    
    res = []
    # Procesamos Ticker por Ticker
    for ticker, grupo in df.groupby('Ticker_EEUU'):
        acciones_netas = 0
        costo_total_usd_neto = 0
        pesos_totales_netos = 0
        
        # Ordenamos por fecha para seguir el flujo real de dinero
        for _, fila in grupo.sort_values('Fecha').iterrows():
            acciones_op = fila['Cantidad'] / fila['Ratio']
            op = str(fila['Operacion']).upper().strip()
            
            # Buscamos el precio histórico en USD
            p_usd_h = obtener_precio_h(ticker, str(fila['Fecha']))
            if p_usd_h is None: continue
            
            costo_usd_op = acciones_op * p_usd_h

            if op == 'COMPRA':
                # Al comprar, sumamos acciones y costos
                acciones_netas += acciones_op
                costo_total_usd_neto += costo_usd_op
                pesos_totales_netos += fila['Total Pesos']
            
            elif op == 'VENTA':
                # Al vender, reducimos la tenencia proporcionalmente
                if acciones_netas > 0:
                    # Calculamos el costo promedio ANTES de la venta
                    ppp_antes = costo_total_usd_neto / acciones_netas
                    ppp_pesos_antes = pesos_totales_netos / acciones_netas
                    
                    # Restamos acciones y el costo proporcional que representaban
                    acciones_netas -= acciones_op
                    costo_total_usd_neto = acciones_netas * ppp_antes
                    pesos_totales_netos = acciones_netas * ppp_pesos_antes

        # Solo incluimos en el dashboard activos que aún tengamos (tenencia > 0)
        if acciones_netas > 0.0001: 
            res.append({
                'Ticker': ticker,
                'Acciones': acciones_netas,
                'PPP_USD': costo_total_usd_neto / acciones_netas,
                'Costo_Total_USD': costo_total_usd_neto,
                'CCL_Entrada': pesos_totales_netos / costo_total_usd_neto if costo_total_usd_neto > 0 else 0
            })
    return pd.DataFrame(res)

# --- 3. EJECUCIÓN ---
st.title("📈 Mi Portafolio Real (Tenencia Actual)")

try:
    with st.spinner('Calculando tenencia neta y precios...'):
        movimientos = table_movs.all()
        df_p = procesar_datos(movimientos)
        
        if df_p.empty:
            st.warning("No tienes posiciones abiertas actualmente.")
            st.stop()

        # Precios actuales
        tickers_api = [t.replace('.', '-') for t in df_p['Ticker'].tolist()]
        data_now = yf.download(tickers_api, period="1d", auto_adjust=True)['Close']
        
        # Mapeo de precios
        if len(df_p) > 1:
            dict_now = data_now.iloc[-1].to_dict()
            dict_now = {k.replace('-', '.'): v for k, v in dict_now.items()}
        else:
            val = data_now.iloc[-1]
            dict_now = {df_p['Ticker'].iloc[0]: float(val.iloc[0] if isinstance(val, pd.Series) else val)}

        df_p['Precio_Hoy'] = df_p['Ticker'].map(dict_now)
        df_p['Valor_Actual_USD'] = df_p['Acciones'] * df_p['Precio_Hoy']
        df_p['Ganancia_USD'] = df_p['Valor_Actual_USD'] - df_p['Costo_Total_USD']
        df_p['Rendimiento'] = (df_p['Ganancia_USD'] / df_p['Costo_Total_USD']) * 100

    # MÉTRICAS
    c1, c2, c3 = st.columns(3)
    c1.metric("Valuación Actual", f"USD {df_p['Valor_Actual_USD'].sum():,.2f}")
    c2.metric("P&L No Realizado", f"USD {df_p['Ganancia_USD'].sum():,.2f}", f"{(df_p['Ganancia_USD'].sum()/df_p['Costo_Total_USD'].sum())*100:.2f}%")
    c3.metric("Dólar Promedio Entrada", f"${df_p['CCL_Entrada'].mean():,.2f}")

    st.subheader("📋 Detalle de Posiciones Abiertas")
    st.dataframe(df_p.style.format({
        'PPP_USD': '{:.2f}', 'Precio_Hoy': '{:.2f}', 'Valor_Actual_USD': '{:.2f}', 
        'Ganancia_USD': '{:.2f}', 'Rendimiento': '{:.2f}%', 'CCL_Entrada': '{:.2f}', 'Acciones': '{:.4f}'
    }), use_container_width=True)

except Exception as e:
    st.error(f"Error: {e}")
