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
        # Ajuste para tickers con puntos (BRK.B -> BRK-B)
        t_api = ticker.replace('.', '-')
        start = datetime.datetime.strptime(fecha_str, "%Y-%m-%d")
        end = start + datetime.timedelta(days=5)
        data = yf.download(t_api, start=start.strftime("%Y-%m-%d"), 
                           end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if not data.empty:
            close_col = data['Close']
            # Extraer valor escalar para evitar error de ambigüedad
            return float(close_col.iloc[0, 0]) if isinstance(close_col, pd.DataFrame) else float(close_col.iloc[0])
    except:
        return None
    return None

def procesar_datos(records):
    df = pd.DataFrame([r['fields'] for r in records])
    df.columns = [c.strip() for c in df.columns] # Limpiar espacios
    
    res = []
    # Agrupamos por 'Ticker_EEUU' (Nombre exacto en tu Airtable)
    for ticker, grupo in df.groupby('Ticker_EEUU'):
        t_acciones = 0
        t_costo_usd = 0
        t_costo_pesos = 0
        
        for _, fila in grupo.sort_values('Fecha').iterrows():
            # Usamos 'Cantidad' y 'Ratio'
            acciones_reales = fila['Cantidad'] / fila['Ratio']
            p_usd_h = obtener_precio_h(ticker, str(fila['Fecha']))
            
            if p_usd_h:
                costo_usd = acciones_reales * p_usd_h
                # Normalizamos 'Operacion' a mayúsculas para evitar errores
                op = str(fila['Operacion']).upper().strip()
                
                if op == 'COMPRA':
                    t_acciones += acciones_reales
                    t_costo_usd += costo_usd
                    t_costo_pesos += fila['Total Pesos']
                elif op == 'VENTA':
                    if t_acciones > 0:
                        prop = acciones_reales / t_acciones
                        t_costo_usd -= (t_costo_usd * prop)
                        t_costo_pesos -= (t_costo_pesos * prop)
                    t_acciones -= acciones_reales

        if t_acciones > 0:
            res.append({
                'Ticker': ticker, # Nombre interno para el DataFrame
                'Acciones': t_acciones,
                'PPP_USD': t_costo_usd / t_acciones,
                'Costo_Total_USD': t_costo_usd,
                'CCL_Entrada': t_costo_pesos / t_costo_usd
            })
    return pd.DataFrame(res)

# --- 3. EJECUCIÓN PRINCIPAL ---
st.title("📈 Mi Portafolio Real (USD)")

try:
    with st.spinner('Procesando datos...'):
        movimientos = table_movs.all()
        if not movimientos:
            st.info("No hay datos en la tabla 'Movimientos'.")
            st.stop()
            
        df_p = procesar_datos(movimientos)
        
        if df_p.empty:
            st.warning("No se pudieron procesar posiciones activas.")
            st.stop()

        # Precios actuales
        tickers = df_p['Ticker'].tolist()
        tickers_api = [t.replace('.', '-') for t in tickers]
        data_now = yf.download(tickers_api, period="1d", auto_adjust=True)['Close']
        
        # Mapeo de precios actuales (manejo de ticker único o múltiple)
        if len(tickers) > 1:
            dict_now = data_now.iloc[-1].to_dict()
            dict_now = {k.replace('-', '.'): v for k, v in dict_now.items()}
        else:
            val = data_now.iloc[-1]
            dict_now = {tickers[0]: float(val.iloc[0] if isinstance(val, pd.Series) else val)}

        # Cálculos finales
        df_p['Precio_Hoy'] = df_p['Ticker'].map(dict_now)
        df_p['Valor_Actual_USD'] = df_p['Acciones'] * df_p['Precio_Hoy']
        df_p['Ganancia_USD'] = df_p['Valor_Actual_USD'] - df_p['Costo_Total_USD']
        df_p['Rendimiento'] = (df_p['Ganancia_USD'] / df_p['Costo_Total_USD']) * 100

    # MÉTRICAS
    c1, c2, c3 = st.columns(3)
    c1.metric("Cartera Total", f"USD {df_p['Valor_Actual_USD'].sum():,.2f}")
    c2.metric("P&L Total", f"USD {df_p['Ganancia_USD'].sum():,.2f}", f"{ (df_p['Ganancia_USD'].sum()/df_p['Costo_Total_USD'].sum())*100 :.2f}%")
    c3.metric("Dólar Promedio Entrada", f"${df_p['CCL_Entrada'].mean():,.2f}")

    # TABLA DE DETALLE
    st.subheader("📋 Detalle de Posiciones")
    st.dataframe(df_p.style.format({
        'PPP_USD': '{:.2f}', 'Precio_Hoy': '{:.2f}', 'Valor_Actual_USD': '{:.2f}', 
        'Ganancia_USD': '{:.2f}', 'Rendimiento': '{:.2f}%', 'CCL_Entrada': '{:.2f}', 'Acciones': '{:.4f}'
    }), use_container_width=True)

except Exception as e:
    st.error(f"Error en el dashboard: {e}")
