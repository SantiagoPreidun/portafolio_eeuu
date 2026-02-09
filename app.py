import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px
import datetime

# --- 1. CONFIGURACIÓN Y ESTILO ---
st.set_page_config(page_title="Inversiones 360", layout="wide")

# Diseño de "Tarjetas" para separar secciones visualmente
st.markdown("""
    <style>
    .section-card {
        background-color: #161b22;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #30363d;
        margin-bottom: 20px;
    }
    .metric-text { color: #00cc96; font-weight: bold; font-size: 24px; }
    </style>
    """, unsafe_allow_html=True)

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
    table_port = Table(AIRTABLE_KEY, BASE_ID, "Portafolio")
except Exception as e:
    st.error("Error en credenciales de Airtable.")
    st.stop()

# --- 2. CARGA DE DATOS ---
def fix_ticker(t):
    return str(t).strip().replace('.', '-')

try:
    # Traemos datos base
    recs_port = table_port.all()
    recs_movs = table_movs.all()
    
    df_actual = pd.DataFrame([r['fields'] for r in recs_port])
    df_movs = pd.DataFrame([r['fields'] for r in recs_movs])
    
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]
    
    # Identificación de columna de dinero
    col_dinero = next((c for c in df_movs.columns if c in ['Importe', 'Total Pesos', 'Monto']), 'Importe')

    # --- 3. PROCESAMIENTO DE CARTERA ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("💼 Composición de Cartera")
    
    if not df_actual.empty:
        tickers_api = [fix_ticker(t) for t in df_actual['Ticker_EEUU'].unique()]
        data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
        
        if len(tickers_api) > 1:
            precios_dict = {k.replace('-', '.'): v for k, v in data_now.iloc[-1].to_dict().items()}
        else:
            precios_dict = {df_actual['Ticker_EEUU'].iloc[0]: float(data_now.iloc[-1])}

        df_actual['Precio Hoy'] = df_actual['Ticker_EEUU'].map(precios_dict)
        df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Precio Hoy']
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"Patrimonio Total: <span class='metric-text'>USD {df_actual['Valuación USD'].sum():,.2f}</span>", unsafe_allow_html=True)
            # Tabla principal sin background_gradient para evitar errores de matplotlib
            sel_port = st.dataframe(
                df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']],
                use_container_width=True, on_select="rerun", selection_mode="single-row"
            )
        with c2:
            fig_pie = px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, template="plotly_dark")
            fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_pie, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 4. ANÁLISIS DETALLADO (DRILL-DOWN) ---
    if len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        row_sel = df_actual.iloc[idx]
        t_sel = row_sel['Ticker_EEUU']
        
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader(f"🔍 Rendimiento Histórico USD: {t_sel}")
        
        m_t = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
        m_t['Fecha'] = pd.to_datetime(m_t['Fecha'])
        
        # Obtenemos precios históricos para dolarizar
        h_prices = yf.download(fix_ticker(t_sel), start=m_t['Fecha'].min(), progress=False)['Close']
        
        detalles = []
        for _, op in m_t.iterrows():
            try:
                p_compra = h_prices.loc[:op['Fecha']].iloc[-1]
            except:
                p_compra = row_sel['Precio Hoy']
            
            c_usa = op['Cantidad'] / op['Ratio']
            rend = ((row_sel['Precio Hoy'] / p_compra) - 1) * 100
            detalles.append({
                'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                'Acciones (USA)': c_usa,
                'Precio Compra (USD)': p_compra,
                'Rendimiento (%)': rend
            })
        
        st.dataframe(pd.DataFrame(detalles).style.format({
            'Precio Compra (USD)': '${:,.2f}', 'Rendimiento (%)': '{:.2f}%'
        }).applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', subset=['Rendimiento (%)']),
        use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- 5. GRÁFICO DE EVOLUCIÓN (ESTÁTICO) ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("📈 Evolución Global del Portafolio")

    @st.cache_data(ttl=3600)
    def calcular_evol_global(_movs, _port, _tapi):
        f_ini = pd.to_datetime(_movs['Fecha']).min()
        hp = yf.download(_tapi, start=f_ini, progress=False)['Close']
        if isinstance(hp, pd.Series): hp = hp.to_frame(); hp.columns = _tapi
        hp.columns = [c.replace('-', '.') for c in hp.columns]
        
        rango = pd.date_range(start=f_ini, end=datetime.datetime.now())
        ev = []
        for d in rango:
            s_dia = 0
            for _, asset in _port.iterrows():
                tk = asset['Ticker_EEUU']
                m_h = _movs[(_movs['Ticker_EEUU'] == tk) & (pd.to_datetime(_movs['Fecha']) <= d)]
                q = m_h[m_h['Operacion'].str.upper()=='COMPRA']['Cantidad'].sum() - m_h[m_h['Operacion'].str.upper()=='VENTA']['Cantidad'].sum()
                if tk in hp.columns:
                    p = hp.loc[:d, tk].ffill().iloc[-1] if not hp.loc[:d, tk].empty else 0
                    s_dia += (q / asset['Ratio']) * p
            ev.append(s_dia)
        return pd.DataFrame({'USD': ev}, index=rango)

    with st.spinner('Cargando historial...'):
        df_ev = calcular_evol_global(df_movs, df_actual, tickers_api)
        df_ev.iloc[-1] = df_actual['Valuación USD'].sum()
        st.plotly_chart(px.area(df_ev, y='USD', template="plotly_dark", color_discrete_sequence=['#00cc96']), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- 6. ACTIVOS LIQUIDADOS ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("🏁 Ganancias Realizadas (Cerradas)")
    
    t_en_port = set(df_actual['Ticker_EEUU'].unique())
    t_liq = list(set(df_movs['Ticker_EEUU'].unique()) - t_en_port)
    
    if t_liq:
        res_l = []
        for t in t_liq:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            c = m_t[m_t['Operacion'].str.upper()=='COMPRA'][col_dinero].sum()
            v = m_t[m_t['Operacion'].str.upper()=='VENTA'][col_dinero].sum()
            res_l.append({'Ticker': t, 'Monto Compra': c, 'Monto Venta': v, 'Rendimiento': v-c, '%': ((v/c)-1)*100 if c>0 else 0})
        
        df_l = pd.DataFrame(res_l)
        # Totales
        df_tot = pd.DataFrame([{'Ticker': 'TOTAL GLOBAL', 'Monto Compra': df_l['Monto Compra'].sum(), 'Monto Venta': df_l['Monto Venta'].sum(), 'Rendimiento': df_l['Rendimiento'].sum(), '%': (df_l['Rendimiento'].sum()/df_l['Monto Compra'].sum()*100) if df_l['Monto Compra'].sum()>0 else 0}])
        df_final_liq = pd.concat([df_l, df_tot], ignore_index=True)
        
        st.dataframe(df_final_liq.style.format({'Monto Compra': '${:,.2f}', 'Monto Venta': '${:,.2f}', 'Rendimiento': '${:,.2f}', '%': '{:.2f}%'})
                     .apply(lambda x: ['font-weight: bold; background-color: #333' if x['Ticker'] == 'TOTAL GLOBAL' else '' for _ in x], axis=1), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error detectado: {e}")
