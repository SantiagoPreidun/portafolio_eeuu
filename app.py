import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import datetime

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Gestión de Portafolio USD", layout="wide")

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    # Conectamos ambas tablas
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
    table_port = Table(AIRTABLE_KEY, BASE_ID, "Portafolio")
except Exception as e:
    st.error(f"Error de conexión con Airtable: {e}")
    st.stop()

# --- 2. LÓGICA DE PROCESAMIENTO HISTÓRICO ---
@st.cache_data(ttl=3600)
def procesar_historial(records):
    df = pd.DataFrame([r['fields'] for r in records])
    resultados = []
    
    for ticker, grupo in df.groupby('Ticker_EEUU'):
        total_acciones = 0
        total_invertido_usd = 0
        total_invertido_pesos = 0
        
        for _, fila in grupo.iterrows():
            # Datos de la operación
            fecha = fila['Fecha']
            acciones_op = fila['Cantidad'] / fila['Ratio']
            pesos_op = fila['Total Pesos']
            
            # Buscar precio USD histórico (Yahoo Finance)
            start = datetime.datetime.strptime(fecha, "%Y-%m-%d")
            end = start + datetime.timedelta(days=4)
            hist = yf.download(ticker, start=start.strftime("%Y-%m-%d"), 
                               end=end.strftime("%Y-%m-%d"), progress=False)
            
            if not hist.empty:
                precio_usd_hist = hist['Close'].iloc[0]
                costo_usd_op = acciones_op * precio_usd_hist
                
                # Cálculo de CCL de esa operación
                ccl_op = pesos_op / costo_usd_op if costo_usd_op > 0 else 0
                
                if fila['Operación'] == 'Compra':
                    total_acciones += acciones_op
                    total_invertido_usd += costo_usd_op
                    total_invertido_pesos += pesos_op
                else: # Venta
                    total_acciones -= acciones_op
                    # (Aquí se podría sofisticar más restando proporcionalmente)

        ppp_usd = total_invertido_usd / total_acciones if total_acciones > 0 else 0
        ccl_promedio = total_invertido_pesos / total_invertido_usd if total_invertido_usd > 0 else 0
        
        resultados.append({
            'Ticker': ticker,
            'Acciones_EEUU': total_acciones,
            'PPP_USD': ppp_usd,
            'Inversión_Total_USD': total_invertido_usd,
            'CCL_Promedio_Compra': ccl_promedio
        })
    return pd.DataFrame(resultados)

# --- 3. INTERFAZ Y DASHBOARD ---
st.title("💼 Dashboard de Inversiones: Realidad USD")

try:
    records_movs = table_movs.all()
    if records_movs:
        with st.spinner('Analizando movimientos históricos y consultando precios...'):
            df_analisis = procesar_historial(records_movs)
            
            # Precios de HOY
            tickers = df_analisis['Ticker'].tolist()
            precios_hoy = yf.download(tickers, period="1d")['Close'].iloc[-1]
            
            if len(tickers) == 1:
                df_analisis['Precio_Actual'] = precios_hoy
            else:
                df_analisis['Precio_Actual'] = df_analisis['Ticker'].map(precios_hoy)

        # CÁLCULOS DE PERFORMANCE
        df_analisis['Valuación_Actual_USD'] = df_analisis['Acciones_EEUU'] * df_analisis['Precio_Actual']
        df_analisis['Ganancia_USD'] = df_analisis['Valuación_Actual_USD'] - df_analisis['Inversión_Total_USD']
        df_analisis['Rendimiento_%'] = (df_analisis['Ganancia_USD'] / df_analisis['Inversión_Total_USD']) * 100

        # MÉTRICAS PRINCIPALES
        m1, m2, m3 = st.columns(3)
        m1.metric("Patrimonio Total USD", f"${df_analisis['Valuación_Actual_USD'].sum():,.2f}")
        m2.metric("Ganancia Total USD", f"${df_analisis['Ganancia_USD'].sum():,.2f}", 
                  f"{ (df_analisis['Ganancia_USD'].sum() / df_analisis['Inversión_Total_USD'].sum())*100 :.2f}%")
        m3.metric("CCL Promedio Cartera", f"${df_analisis['CCL_Promedio_Compra'].mean():,.2f}")

        # TABLA DE DETALLE PROFESIONAL
        st.subheader("📋 Análisis Detallado por Activo")
        st.dataframe(df_analisis.style.format({
            'PPP_USD': '{:.2f}',
            'Precio_Actual': '{:.2f}',
            'Valuación_Actual_USD': '{:.2f}',
            'Ganancia_USD': '{:.2f}',
            'Rendimiento_%': '{:.2f}%',
            'CCL_Promedio_Compra': '{:.2f}'
        }), use_container_width=True)

    else:
        st.info("No se encontraron movimientos. Cargá tus compras en Airtable.")

except Exception as e:
    st.error(f"Error procesando el dashboard: {e}")
