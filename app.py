import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import datetime
import plotly.express as px

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor Inversiones USD", layout="wide")

# --- 2. CONEXIÓN A AIRTABLE ---
try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    # Usaremos la tabla de Movimientos como fuente de verdad para costos
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
except Exception as e:
    st.error(f"❌ Error de configuración (Secrets): {e}")
    st.stop()

# --- 3. BARRA LATERAL (CONTROLES) ---
st.sidebar.title("⚙️ Opciones de Análisis")
periodo_hist = st.sidebar.selectbox("Periodo para el gráfico", ["3mo", "6mo", "1y", "2y", "5y"], index=1)
benchmarks_dict = {"S&P 500": "SPY", "Nasdaq 100": "QQQ", "Oro": "GLD"}
comparar_con = st.sidebar.multiselect("Comparar contra:", list(benchmarks_dict.keys()), default=["S&P 500"])

# --- 4. FUNCIONES DE CÁLCULO ---

@st.cache_data(ttl=3600)
def obtener_precio_historico(ticker, fecha_str):
    """Obtiene el precio de cierre de un ticker en una fecha específica de forma segura."""
    try:
        start = datetime.datetime.strptime(fecha_str, "%Y-%m-%d")
        end = start + datetime.timedelta(days=5) # Margen por feriados/findes
        data = yf.download(ticker, start=start.strftime("%Y-%m-%d"), 
                           end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if not data.empty:
            # Fix para evitar 'Series is ambiguous': extraemos el valor escalar
            close_vals = data['Close']
            if isinstance(close_vals, pd.DataFrame):
                return float(close_vals.iloc[0, 0])
            else:
                return float(close_vals.iloc[0])
    except:
        return None
    return None

def procesar_cartera(records):
    """Procesa los movimientos de Airtable para calcular PPP y Tenencia actual."""
    df = pd.DataFrame([r['fields'] for r in records])
    df.columns = [c.strip() for c in df.columns] # Limpieza de nombres
    
    res = []
    # Agrupamos por Ticker para reconstruir cada posición
    for ticker, grupo in df.groupby('Ticker_EEUU'):
        total_acciones = 0
        total_costo_usd = 0
        total_costo_pesos = 0
        
        for _, fila in grupo.sort_values('Fecha').iterrows():
            # Convertimos CEDEARs a Acciones reales
            acciones_op = fila['Cantidad'] / fila['Ratio']
            precio_usd_h = obtener_precio_historico(ticker, str(fila['Fecha']))
            
            if precio_usd_h:
                costo_usd_op = acciones_op * precio_usd_h
                
                if fila['Operación'] == 'Compra':
                    total_acciones += acciones_op
                    total_costo_usd += costo_usd_op
                    total_costo_pesos += fila['Total Pesos']
                elif fila['Operación'] == 'Venta':
                    # Simplificación: restamos proporcionalmente
                    if total_acciones > 0:
                        porcentaje_venta = acciones_op / total_acciones
                        total_costo_usd -= (total_costo_usd * porcentaje_venta)
                        total_costo_pesos -= (total_costo_pesos * porcentaje_venta)
                    total_acciones -= acciones_op

        if total_acciones > 0:
            ppp_usd = total_costo_usd / total_acciones
            ccl_compra = total_costo_pesos / total_costo_usd
            res.append({
                'Ticker': ticker,
                'Acciones': total_acciones,
                'Costo_Total_USD': total_costo_usd,
                'PPP_USD': ppp_usd,
                'CCL_Promedio': ccl_compra
            })
    return pd.DataFrame(res)

# --- 5. EJECUCIÓN PRINCIPAL ---
st.title("💸 Dashboard: Realidad de mi Portafolio en USD")

try:
    with st.spinner('Cargando datos de Airtable y Wall Street...'):
        data_airtable = table_movs.all()
        if not data_airtable:
            st.info("La tabla 'Movimientos' está vacía.")
            st.stop()
            
        df_portfolio = procesar_cartera(data_airtable)
        
        # Obtener precios actuales
        tickers_en_cartera = df_portfolio['Ticker'].tolist()
        precios_actuales = yf.download(tickers_en_cartera, period="1d", auto_adjust=True)['Close']
        
        # Mapeo seguro de precios de hoy
        if len(tickers_en_cartera) > 1:
            dict_precios = precios_actuales.iloc[-1].to_dict()
        else:
            dict_precios = {tickers_en_cartera[0]: float(precios_actuales.iloc[-1])}
        
        df_portfolio['Precio_Hoy'] = df_portfolio['Ticker'].map(dict_precios)
        df_portfolio['Valor_Actual_USD'] = df_portfolio['Acciones'] * df_portfolio['Precio_Hoy']
        df_portfolio['Ganancia_USD'] = df_portfolio['Valor_Actual_USD'] - df_portfolio['Costo_Total_USD']
        df_portfolio['Rendimiento_%'] = (df_portfolio['Ganancia_USD'] / df_portfolio['Costo_Total_USD']) * 100

    # --- MÉTRICAS ---
    val_total = df_portfolio['Valor_Actual_USD'].sum()
    gan_total = df_portfolio['Ganancia_USD'].sum()
    rend_total = (gan_total / df_portfolio['Costo_Total_USD'].sum()) * 100
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Patrimonio Actual", f"USD {val_total:,.2f}")
    m2.metric("P&L Total (Moneda Dura)", f"USD {gan_total:,.2f}", f"{rend_total:.2f}%")
    m3.metric("CCL Promedio de Entrada", f"${df_portfolio['CCL_Promedio'].mean():,.2f}")

    # --- TABLA Y TORTA ---
    c1, c2 = st.columns([1, 2])
    with c1:
        fig_pie = px.pie(df_portfolio, values='Valor_Actual_USD', names='Ticker', hole=0.4, title="Distribución")
        st.plotly_chart(fig_pie, use_container_width=True)
    with c2:
        st.subheader("Detalle por Activo")
        st.dataframe(df_portfolio.style.format({
            'PPP_USD': '{:.2f}', 'Precio_Hoy': '{:.2f}', 'Valor_Actual_USD': '{:.2f}', 
            'Ganancia_USD': '{:.2f}', 'Rendimiento_%': '{:.2f}%', 'CCL_Promedio': '{:.2f}', 'Acciones': '{:.4f}'
        }), use_container_width=True)

    # --- COMPARATIVA HISTÓRICA ---
    st.divider()
    st.subheader(f"📊 Rendimiento acumulado vs Benchmarks ({periodo_hist})")
    
    # Descargar historial para gráfico
    lista_bench = [benchmarks_dict[b] for b in comparar_con]
    data_hist = yf.download(tickers_en_cartera + lista_bench, period=periodo_hist, auto_adjust=True)['Close'].ffill()
    
    # Calcular evolución de cartera (Base 100)
    evolucion = pd.DataFrame(index=data_hist.index)
    v_diario = 0
    for _, row in df_portfolio.iterrows():
        v_diario += data_hist[row['Ticker']] * row['Acciones']
    
    evolucion['Mi Cartera'] = (v_diario / v_diario.iloc[0]) * 100
    for b in comparar_con:
        ticker_b = benchmarks_dict[b]
        evolucion[b] = (data_hist[ticker_b] / data_hist[ticker_b].iloc[0]) * 100
        
    fig_line = px.line(evolucion, labels={'value': 'Evolución (Base 100)', 'Date': 'Fecha'})
    st.plotly_chart(fig_line, use_container_width=True)

except Exception as e:
    st.error(f"⚠️ Error general en el dashboard: {e}")
