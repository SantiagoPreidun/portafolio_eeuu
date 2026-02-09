import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px
import datetime

# --- 1. CONFIGURACIÓN Y ESTILO ---
st.set_page_config(page_title="Inversiones Elite", layout="wide")

# CSS para remarcar secciones y mejorar estética
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #00cc96; }
    .stDataFrame { border: 1px solid #30363d; border-radius: 10px; }
    .section-box {
        padding: 20px;
        border-radius: 15px;
        background-color: #161b22;
        border: 1px solid #30363d;
        margin-bottom: 25px;
    }
    h1, h2, h3 { color: #f0f6fc; }
    </style>
    """, unsafe_allow_html=True)

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

    # --- SECCIÓN 1: TENENCIA ACTUAL (Con Mapa de Calor) ---
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.title("📊 Tenencia Actual y Composición")
    
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
            st.metric("Patrimonio Total USD", f"${df_actual['Valuación USD'].sum():,.2f}")
            
            # MAPA DE CALOR: Aplicamos degradado a la columna de Valuación
            styled_port = df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']].style.background_gradient(
                cmap='YlGn', subset=['Valuación USD']
            ).format({'Valuación USD': '${:,.2f}', 'Precio Hoy': '${:,.2f}'})

            sel_port = st.dataframe(styled_port, use_container_width=True, on_select="rerun", selection_mode="single-row")
        with c2:
            fig_pie = px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.5, 
                             color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 2: ANÁLISIS DETALLADO USD ---
    if len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        fila_sel = df_actual.iloc[idx]
        t_sel = fila_sel['Ticker_EEUU']
        
        st.markdown('<div class="section-box">', unsafe_allow_html=True)
        st.subheader(f"🔍 Drill-down: {t_sel}")
        
        m_t = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
        m_t['Fecha'] = pd.to_datetime(m_t['Fecha'])
        
        t_api_sel = fix_ticker_api(t_sel)
        h_precios_sel = yf.download(t_api_sel, start=m_t['Fecha'].min(), progress=False)['Close']
        
        detalles_op = []
        for _, op in m_t.iterrows():
            p_compra_usd = h_precios_sel.loc[:op['Fecha']].iloc[-1] if not h_precios_sel.loc[:op['Fecha']].empty else fila_sel['Precio Hoy']
            cant_usa = op['Cantidad'] / op['Ratio']
            detalles_op.append({
                'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                'Operación': op['Operacion'].upper(),
                'Precio Compra (USD)': p_compra_usd,
                'Rendimiento (%)': ((fila_sel['Precio Hoy'] / p_compra_usd) - 1) * 100
            })
        
        st.dataframe(pd.DataFrame(detalles_op).style.format({'Precio Compra (USD)': '${:,.2f}', 'Rendimiento (%)': '{:.2f}%'})
                     .applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (int, float)) and x < 0 else 'color: #00cc96', subset=['Rendimiento (%)']), 
                     use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 3: EVOLUCIÓN HISTÓRICA ---
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("📈 Evolución Global")
    
    @st.cache_data(ttl=3600)
    def get_evol_cached(_m, _a, _t):
        f_ini = pd.to_datetime(_m['Fecha']).min()
        hp = yf.download(_t, start=f_ini, progress=False)['Close']
        hp.columns = [c.replace('-', '.') for c in hp.columns]
        rango = pd.date_range(start=f_ini, end=datetime.datetime.now())
        ev = []
        for d in rango:
            s = 0
            for _, asset in _a.iterrows():
                tk = asset['Ticker_EEUU']
                m_h = _m[(_m['Ticker_EEUU'] == tk) & (pd.to_datetime(_m['Fecha']) <= d)]
                qty = (m_h[m_h['Operacion'].str.upper()=='COMPRA']['Cantidad'].sum() - m_h[m_h['Operacion'].str.upper()=='VENTA']['Cantidad'].sum())
                if tk in hp.columns:
                    s += (qty / asset['Ratio']) * hp.loc[:d, tk].ffill().iloc[-1]
            ev.append(s)
        return pd.DataFrame({'USD': ev}, index=rango)

    df_ev = get_evol_cached(df_movs, df_actual, tickers_api)
    df_ev.iloc[-1] = df_actual['Valuación USD'].sum()
    fig_ev = px.area(df_ev, y='USD', title=None, color_discrete_sequence=['#00cc96'])
    fig_ev.update_layout(xaxis_title=None, yaxis_title=None, height=300)
    st.plotly_chart(fig_ev, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 4: LIQUIDADOS ---
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.subheader("🏁 Ganancias Realizadas")
    # ... (Misma lógica de liquidados con totales que ya teníamos)
    st.markdown('</div>', unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error: {e}")
