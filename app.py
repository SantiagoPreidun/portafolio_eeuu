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
    .section-title {
        color: #f0f6fc;
        font-size: 20px; font-weight: bold; margin-bottom: 15px;
        border-left: 5px solid #00cc96; padding-left: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

try:
    AIRTABLE_KEY = st.secrets["AIRTABLE_API_KEY"]
    BASE_ID = st.secrets["BASE_ID"]
    table_movs = Table(AIRTABLE_KEY, BASE_ID, "Movimientos")
    table_port = Table(AIRTABLE_KEY, BASE_ID, "Portafolio")
except:
    st.error("Error en credenciales de Airtable.")
    st.stop()

def fix_ticker(t):
    return str(t).strip().replace('.', '-')

# --- 2. EJECUCIÓN ---
try:
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]
    
    col_dinero = next((c for c in df_movs.columns if c in ['Importe', 'Total Pesos', 'Monto']), 'Importe')

    # --- SECCIÓN 1: CARTERA ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">💼 Mi Portafolio (Rendimiento USD)</div>', unsafe_allow_html=True)
    
    if not df_actual.empty:
        tickers_api = [fix_ticker(t) for t in df_actual['Ticker_EEUU'].unique()]
        
        with st.spinner('Actualizando precios y calculando ganancias...'):
            data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
            if len(tickers_api) > 1:
                precios_dict = {k.replace('-', '.'): v for k, v in data_now.iloc[-1].to_dict().items()}
            else:
                precios_dict = {df_actual['Ticker_EEUU'].iloc[0]: float(data_now.iloc[-1])}

            df_actual['Precio Hoy'] = df_actual['Ticker_EEUU'].map(precios_dict)
            df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Precio Hoy']
            
            ganancias_nominales = []
            rets_posicion = []
            
            for _, row in df_actual.iterrows():
                t = row['Ticker_EEUU']
                m_t = df_movs[(df_movs['Ticker_EEUU'] == t) & (df_movs['Operacion'].str.upper() == 'COMPRA')]
                
                costo_acum_usd = 0
                if not m_t.empty:
                    h_p = yf.download(fix_ticker(t), start=m_t['Fecha'].min(), progress=False)['Close']
                    for _, op in m_t.iterrows():
                        try:
                            p_c_usd = h_p.loc[:op['Fecha']].ffill().iloc[-1]
                            if isinstance(p_c_usd, pd.Series): p_c_usd = p_c_usd.iloc[0]
                            costo_acum_usd += (op['Cantidad'] / op['Ratio']) * p_c_usd
                        except: continue
                    
                    # AQUÍ ESTABA EL ERROR: Cambiado costo_total_usd por costo_acum_usd
                    ganancia_usd = row['Valuación USD'] - costo_acum_usd
                    ret_perc = (ganancia_usd / costo_acum_usd * 100) if costo_acum_usd > 0 else 0
                else:
                    ganancia_usd, ret_perc = 0, 0
                
                ganancias_nominales.append(ganancia_usd)
                rets_posicion.append(ret_perc)
            
            df_actual['Ganancia (USD)'] = ganancias_nominales
            df_actual['Retorno (%)'] = rets_posicion

        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"Patrimonio Total: <span class='metric-text'>USD {df_actual['Valuación USD'].sum():,.2f}</span>", unsafe_allow_html=True)
            sel_port = st.dataframe(
                df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy', 'Ganancia (USD)', 'Retorno (%)']].style.format({
                    'Valuación USD': '${:,.2f}', 'Precio Hoy': '${:,.2f}', 
                    'Ganancia (USD)': '${:,.2f}', 'Retorno (%)': '{:.2f}%'
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
        st.markdown(f'<div class="section-title">🔍 Historial de Operaciones: {t_sel}</div>', unsafe_allow_html=True)
        
        m_t_det = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
        m_t_det['Fecha'] = pd.to_datetime(m_t_det['Fecha'])
        h_prices_det = yf.download(fix_ticker(t_sel), start=m_t_det['Fecha'].min(), progress=False)['Close']
        
        det_list = []
        for _, op in m_t_det.iterrows():
            try:
                p_c = h_prices_det.loc[:op['Fecha']].ffill().iloc[-1]
                if isinstance(p_c, pd.Series): p_c = p_c.iloc[0]
                c_usa = op['Cantidad'] / op['Ratio']
                det_list.append({
                    'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                    'Operación': op['Operacion'].upper(),
                    'Acciones (USA)': c_usa,
                    'Precio Compra (USD)': p_c,
                    'Ganancia Lote (USD)': (c_usa * row_sel['Precio Hoy']) - (c_usa * p_c),
                    'Retorno Lote (%)': ((row_sel['Precio Hoy'] / p_c) - 1) * 100
                })
            except: continue
        
        st.dataframe(pd.DataFrame(det_list).style.format({
            'Acciones (USA)': '{:.4f}', 'Precio Compra (USD)': '${:,.2f}', 
            'Ganancia Lote (USD)': '${:,.2f}', 'Retorno Lote (%)': '{:.2f}%'
        }).applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', subset=['Ganancia Lote (USD)', 'Retorno Lote (%)']), 
        use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 3: EVOLUCIÓN ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📈 Evolución Histórica</div>', unsafe_allow_html=True)
    
    @st.cache_data(ttl=3600)
    def calc_ev_pro(_m, _p, _t):
        f_i = pd.to_datetime(_m['Fecha']).min()
        hp = yf.download(_t, start=f_i, progress=False)['Close']
        if isinstance(hp, pd.Series): hp = hp.to_frame(); hp.columns = _t
        hp.columns = [c.replace('-', '.') for c in hp.columns]
        r = pd.date_range(start=f_i, end=datetime.datetime.now())
        ev = []
        for d in r:
            s_d = 0
            for _, a in _p.iterrows():
                tk = a['Ticker_EEUU']
                m_h = _m[(_m['Ticker_EEUU'] == tk) & (pd.to_datetime(_m['Fecha']) <= d)]
                q = (m_h[m_h['Operacion'].str.upper()=='COMPRA']['Cantidad'].sum() - m_h[m_h['Operacion'].str.upper()=='VENTA']['Cantidad'].sum()) / a['Ratio']
                if tk in hp.columns:
                    p_v = hp.loc[:d, tk].ffill()
                    s_d += q * p_v.iloc[-1] if not p_v.empty else 0
            ev.append(s_d)
        return pd.DataFrame({'USD': ev}, index=r)

    df_ev = calc_ev_pro(df_movs, df_actual, tickers_api)
    df_ev.iloc[-1] = df_actual['Valuación USD'].sum()
    st.plotly_chart(px.area(df_ev, y='USD', template="plotly_dark", color_discrete_sequence=['#00cc96']), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 4: LIQUIDADOS ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏁 Activos Liquidados (USD)</div>', unsafe_allow_html=True)
    
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
            res_l.append({'Ticker': t, 'Monto Compra': float(c_u), 'Monto Venta': float(v_u), 'Rendimiento': float(v_u-c_u), '%': float(((v_u/c_u)-1)*100 if c_u>0 else 0)})
        df_l = pd.DataFrame(res_l)
        df_tot = pd.DataFrame([{'Ticker': 'TOTAL GLOBAL', 'Monto Compra': df_l['Monto Compra'].sum(), 'Monto Venta': df_l['Monto Venta'].sum(), 'Rendimiento': df_l['Rendimiento'].sum(), '%': (df_l['Rendimiento'].sum()/df_l['Monto Compra'].sum()*100) if df_l['Monto Compra'].sum()>0 else 0}])
        st.dataframe(pd.concat([df_l, df_tot], ignore_index=True).style.format({'Monto Compra': '${:,.2f}', 'Monto Venta': '${:,.2f}', 'Rendimiento': '${:,.2f}', '%': '{:.2f}%'})
                     .apply(lambda x: ['font-weight: bold; background-color: #333' if x['Ticker'] == 'TOTAL GLOBAL' else '' for _ in x], axis=1), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error: {e}")
