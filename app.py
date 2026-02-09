import streamlit as st
import pandas as pd
import yfinance as yf
from pyairtable import Table
import plotly.express as px
import datetime

# --- 1. CONFIGURACIÓN Y ESTILO ---
st.set_page_config(page_title="Inversiones 360", layout="wide")

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
except:
    st.error("Error en credenciales. Verificá los Secrets en Streamlit.")
    st.stop()

def fix_ticker(t):
    return str(t).strip().replace('.', '-')

# --- 2. EJECUCIÓN PRINCIPAL ---
try:
    # Carga inicial de datos
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]
    
    col_dinero = next((c for c in df_movs.columns if c in ['Importe', 'Total Pesos', 'Monto']), 'Importe')

    # --- SECCIÓN 1: TENENCIA ACTUAL (CÁLCULO USD) ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("💼 Mi Portafolio (Rendimiento Puro USD)")
    
    if not df_actual.empty:
        tickers_api = [fix_ticker(t) for t in df_actual['Ticker_EEUU'].unique()]
        
        with st.spinner('Sincronizando con Wall Street...'):
            data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
            if len(tickers_api) > 1:
                precios_dict = {k.replace('-', '.'): v for k, v in data_now.iloc[-1].to_dict().items()}
            else:
                precios_dict = {df_actual['Ticker_EEUU'].iloc[0]: float(data_now.iloc[-1])}

            df_actual['Precio Hoy'] = df_actual['Ticker_EEUU'].map(precios_dict)
            df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Precio Hoy']
            
            ganancias_usd, retornos_perc = [], []

            for _, row in df_actual.iterrows():
                t = row['Ticker_EEUU']
                m_t = df_movs[(df_movs['Ticker_EEUU'] == t) & (df_movs['Operacion'].str.upper() == 'COMPRA')]
                
                if not m_t.empty:
                    h_p = yf.download(fix_ticker(t), start=m_t['Fecha'].min(), progress=False)['Close']
                    costo_total_usd = 0
                    for _, op in m_t.iterrows():
                        try:
                            p_c_usd = h_p.loc[:op['Fecha']].ffill().iloc[-1]
                            if isinstance(p_c_usd, pd.Series): p_c_usd = p_c_usd.iloc[0]
                            costo_total_usd += (op['Cantidad'] / op['Ratio']) * p_c_usd
                        except: continue
                    ganancia = row['Valuación USD'] - costo_total_usd
                    retorno = (ganancia / costo_total_usd * 100) if costo_total_usd > 0 else 0
                else:
                    ganancia, retorno = 0, 0
                
                ganancias_usd.append(ganancia)
                retornos_perc.append(retorno)
            
            df_actual['Ganancia (USD)'] = ganancias_usd
            df_actual['Retorno (%)'] = retornos_perc

        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"Patrimonio Total: <span class='metric-text'>USD {df_actual['Valuación USD'].sum():,.2f}</span>", unsafe_allow_html=True)
            sel_port = st.dataframe(
                df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy', 'Ganancia (USD)', 'Retorno (%)']].style.format({
                    'Valuación USD': '${:,.2f}', 'Precio Hoy': '${:,.2f}', 'Ganancia (USD)': '${:,.2f}', 'Retorno (%)': '{:.2f}%'
                }).applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', subset=['Ganancia (USD)', 'Retorno (%)']),
                use_container_width=True, on_select="rerun", selection_mode="single-row"
            )
        with c2:
            st.plotly_chart(px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, template="plotly_dark"), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 2: DETALLE INTERACTIVO ---
    if 'sel_port' in locals() and len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        row_sel = df_actual.iloc[idx]
        t_sel = row_sel['Ticker_EEUU']
        
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader(f"🔍 Historial Detallado USD: {t_sel}")
        m_t_det = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
        m_t_det['Fecha'] = pd.to_datetime(m_t_det['Fecha'])
        h_prices_det = yf.download(fix_ticker(t_sel), start=m_t_det['Fecha'].min(), progress=False)['Close']
        
        detalles = []
        for _, op in m_t_det.iterrows():
            try:
                p_c = h_prices_det.loc[:op['Fecha']].ffill().iloc[-1]
                if isinstance(p_c, pd.Series): p_c = p_c.iloc[0]
                c_usa = op['Cantidad'] / op['Ratio']
                detalles.append({
                    'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                    'Operación': op['Operacion'].upper(),
                    'Acciones (USA)': c_usa,
                    'Precio Compra (USD)': float(p_c),
                    'Ganancia Lote (USD)': (c_usa * row_sel['Precio Hoy']) - (c_usa * p_c),
                    'Retorno Lote (%)': ((row_sel['Precio Hoy'] / p_c) - 1) * 100
                })
            except: continue
        
        st.dataframe(pd.DataFrame(detalles).style.format({
            'Acciones (USA)': '{:.4f}', 'Precio Compra (USD)': '${:,.2f}', 'Ganancia Lote (USD)': '${:,.2f}', 'Retorno Lote (%)': '{:.2f}%'
        }).applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', subset=['Ganancia Lote (USD)', 'Retorno Lote (%)']), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 3: EVOLUCIÓN HISTÓRICA ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("📈 Evolución Global del Patrimonio")
    @st.cache_data(ttl=3600)
    def calc_ev_final(_m, _p, _tapi):
        f_i = pd.to_datetime(_m['Fecha']).min()
        hp = yf.download(_tapi, start=f_i, progress=False)['Close']
        if isinstance(hp, pd.Series): hp = hp.to_frame(); hp.columns = _tapi
        hp.columns = [c.replace('-', '.') for c in hp.columns]
        r = pd.date_range(start=f_i, end=datetime.datetime.now())
        ev = []
        for d in r:
            s = 0
            for _, a in _p.iterrows():
                tk = a['Ticker_EEUU']
                m_h = _m[(_m['Ticker_EEUU'] == tk) & (pd.to_datetime(_m['Fecha']) <= d)]
                q = (m_h[m_h['Operacion'].str.upper()=='COMPRA']['Cantidad'].sum() - m_h[m_h['Operacion'].str.upper()=='VENTA']['Cantidad'].sum()) / a['Ratio']
                if tk in hp.columns:
                    p_val = hp.loc[:d, tk].ffill()
                    s += q * p_val.iloc[-1] if not p_val.empty else 0
            ev.append(s)
        return pd.DataFrame({'USD': ev}, index=r)

    df_ev = calc_ev_final(df_movs, df_actual, tickers_api)
    df_ev.iloc[-1] = df_actual['Valuación USD'].sum()
    st.plotly_chart(px.area(df_ev, y='USD', template="plotly_dark", color_discrete_sequence=['#00cc96']), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 4: ACTIVOS LIQUIDADOS ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("🏁 Ganancias Realizadas (Liquidados)")
    t_liq = list(set(df_movs['Ticker_EEUU'].unique()) - set(df_actual['Ticker_EEUU'].unique()))
    if t_liq:
        res_l = []
        for t in t_liq:
            m_t_l = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            h_p_l = yf.download(fix_ticker(t), start=m_t_l['Fecha'].min(), progress=False)['Close']
            c_u, v_u = 0, 0
            for _, op in m_t_l.iterrows():
                try:
                    p_l = h_p_l.loc[:op['Fecha']].ffill().iloc[-1]
                    if isinstance(p_l, pd.Series): p_l = p_l.iloc[0]
                    m = (op['Cantidad'] / op['Ratio']) * p_l
                    if op['Operacion'].upper() == 'COMPRA': c_u += m
                    else: v_u += m
                except: continue
            res_l.append({'Ticker': t, 'Monto Compra (USD)': float(c_u), 'Monto Venta (USD)': float(v_u), 'Rendimiento': float(v_u-c_u), '%': float(((v_u/c_u)-1)*100 if c_u>0 else 0)})
        df_l = pd.DataFrame(res_l)
        # FILA DE TOTALES
        df_tot = pd.DataFrame([{'Ticker': 'TOTAL GLOBAL', 'Monto Compra (USD)': df_l['Monto Compra (USD)'].sum(), 'Monto Venta (USD)': df_l['Monto Venta (USD)'].sum(), 'Rendimiento': df_l['Rendimiento'].sum(), '%': (df_l['Rendimiento'].sum()/df_l['Monto Compra (USD)'].sum()*100) if df_l['Monto Compra (USD)'].sum()>0 else 0}])
        st.dataframe(pd.concat([df_l, df_tot], ignore_index=True).style.format({'Monto Compra (USD)': '${:,.2f}', 'Monto Venta (USD)': '${:,.2f}', 'Rendimiento': '${:,.2f}', '%': '{:.2f}%'})
                     .apply(lambda x: ['font-weight: bold; background-color: #333' if x['Ticker'] == 'TOTAL GLOBAL' else '' for _ in x], axis=1), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error detectado: {e}")
