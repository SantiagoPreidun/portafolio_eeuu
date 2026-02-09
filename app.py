import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px
import datetime

# --- 1. CONFIGURACIÓN Y ESTILO CSS ---
st.set_page_config(page_title="Inversiones 360 - Pro", layout="wide")

# Inyectamos CSS para crear las "Tarjetas" (Cards) y mejorar la tipografía
st.markdown("""
    <style>
    /* Fondo principal */
    .main { background-color: #0e1117; }
    
    /* Contenedor de sección */
    .section-card {
        background-color: #161b22;
        padding: 25px;
        border-radius: 15px;
        border: 1px solid #30363d;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    
    /* Estilo de métricas */
    div[data-testid="stMetricValue"] {
        color: #00cc96 !important;
        font-family: 'Courier New', monospace;
    }
    
    /* Títulos de sección */
    .section-title {
        color: #f0f6fc;
        font-size: 24px;
        font-weight: bold;
        margin-bottom: 15px;
        border-left: 5px solid #00cc96;
        padding-left: 15px;
    }
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
    col_dinero = next((c for c in df_movs.columns if c in ['Importe', 'Total Pesos', 'Monto']), 'Importe')

    def fix_ticker_api(t):
        return str(t).strip().replace('.', '-')

    # --- SECCIÓN 1: TENENCIA ACTUAL ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">💼 Mi Portafolio Real (Tenencia Actual)</div>', unsafe_allow_html=True)
    
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
            
            # --- MAPA DE CALOR ---
            # Intentamos el gradiente, si falta matplotlib fallará silenciosamente a tabla normal
            try:
                styled_df = df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']].style.background_gradient(
                    cmap='Greens', subset=['Valuación USD']
                ).format({'Valuación USD': '{:,.2f}', 'Precio Hoy': '{:,.2f}'})
            except:
                styled_df = df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']]

            sel_port = st.dataframe(styled_df, use_container_width=True, on_select="rerun", selection_mode="single-row")
        
        with c2:
            fig_pie = px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.5, template="plotly_dark")
            fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 2: ANÁLISIS DETALLADO (DRILL-DOWN) ---
    if len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        fila_sel = df_actual.iloc[idx]
        t_sel = fila_sel['Ticker_EEUU']
        
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="section-title">🔍 Análisis de Rendimiento USD: {t_sel}</div>', unsafe_allow_html=True)
        
        m_t = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
        m_t['Fecha'] = pd.to_datetime(m_t['Fecha'])
        t_api_sel = fix_ticker_api(t_sel)
        h_precios = yf.download(t_api_sel, start=m_t['Fecha'].min(), progress=False)['Close']
        
        detalles_op = []
        for _, op in m_t.iterrows():
            try:
                p_compra_usd = h_precios.loc[:op['Fecha']].iloc[-1]
            except:
                p_compra_usd = fila_sel['Precio Hoy']
            
            cant_usa = op['Cantidad'] / op['Ratio']
            detalles_op.append({
                'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                'Acciones (USA)': cant_usa,
                'Precio Compra (USD)': p_compra_usd,
                'Rendimiento (%)': ((fila_sel['Precio Hoy'] / p_compra_usd) - 1) * 100
            })
        
        st.dataframe(pd.DataFrame(detalles_op).style.format({
            'Precio Compra (USD)': '${:,.2f}', 'Rendimiento (%)': '{:.2f}%'
        }).applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (int, float)) and x < 0 else 'color: #00cc96', subset=['Rendimiento (%)']), 
        use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 3: EVOLUCIÓN HISTÓRICA ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📈 Evolución Global del Patrimonio</div>', unsafe_allow_html=True)
    
    @st.cache_data(ttl=3600)
    def calcular_evolucion(_m, _a, _t):
        f_ini = pd.to_datetime(_m['Fecha']).min()
        hp = yf.download(_t, start=f_ini, progress=False)['Close']
        if isinstance(hp, pd.Series): hp = hp.to_frame(); hp.columns = _t
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

    df_ev = calcular_evolucion(df_movs, df_actual, tickers_api)
    df_ev.iloc[-1] = df_actual['Valuación USD'].sum()
    st.plotly_chart(px.area(df_ev, y='USD', template="plotly_dark", color_discrete_sequence=['#00cc96']), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 4: ACTIVOS LIQUIDADOS ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏁 Ganancias Realizadas (Liquidados)</div>', unsafe_allow_html=True)
    
    t_port = set(df_actual['Ticker_EEUU'].unique()) if not df_actual.empty else set()
    liq = list(set(df_movs['Ticker_EEUU'].unique()) - t_port)
    if liq:
        res_l = []
        for t in liq:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            m_t['Operacion'] = m_t['Operacion'].str.strip().str.upper()
            c = m_t[m_t['Operacion'] == 'COMPRA'][col_dinero].sum()
            v = m_t[m_t['Operacion'] == 'VENTA'][col_dinero].sum()
            res_l.append({'Ticker': t, 'Monto Compra': c, 'Monto Venta': v, 'Rendimiento': v-c, '%': ((v/c)-1)*100 if c>0 else 0})
        
        df_l = pd.DataFrame(res_l)
        # Fila de totales
        total_row = pd.DataFrame([{'Ticker': 'TOTAL GLOBAL', 'Monto Compra': df_l['Monto Compra'].sum(), 'Monto Venta': df_l['Monto Venta'].sum(), 'Rendimiento': df_l['Rendimiento'].sum(), '%': (df_l['Rendimiento'].sum()/df_l['Monto Compra'].sum()*100) if df_l['Monto Compra'].sum()>0 else 0}])
        df_l = pd.concat([df_l, total_row], ignore_index=True)
        
        st.dataframe(df_l.style.format({'Monto Compra': '${:,.2f}', 'Monto Venta': '${:,.2f}', 'Rendimiento': '${:,.2f}', '%': '{:.2f}%'})
                     .apply(lambda x: ['font-weight: bold; background-color: #333' if x['Ticker'] == 'TOTAL GLOBAL' else '' for _ in x], axis=1), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error: {e}")
