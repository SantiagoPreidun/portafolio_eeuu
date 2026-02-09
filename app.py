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
    st.error("Error en credenciales. Verificá los Secrets.")
    st.stop()

def fix_ticker(t):
    return str(t).strip().replace('.', '-')

# --- 2. EJECUCIÓN ---
try:
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]
    
    # --- SECCIÓN 1: CARTERA (TENENCIA ACTUAL) ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">💼 Mi Portafolio (Rendimiento USD)</div>', unsafe_allow_html=True)
    
    if not df_actual.empty:
        tickers_api = [fix_ticker(t) for t in df_actual['Ticker_EEUU'].unique()]
        
        with st.spinner('Actualizando precios de Wall Street...'):
            data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
            if len(tickers_api) > 1:
                precios_dict = {k.replace('-', '.'): v for k, v in data_now.iloc[-1].to_dict().items()}
            else:
                precios_dict = {df_actual['Ticker_EEUU'].iloc[0]: float(data_now.iloc[-1])}

            df_actual['Precio Hoy'] = df_actual['Ticker_EEUU'].map(precios_dict)
            df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Precio Hoy']
            
            # Cálculo de Retorno Promedio por Posición (Solo USD)
            rets_posicion = []
            for _, row in df_actual.iterrows():
                t = row['Ticker_EEUU']
                m_t = df_movs[(df_movs['Ticker_EEUU'] == t) & (df_movs['Operacion'].str.upper() == 'COMPRA')]
                
                if not m_t.empty:
                    h_p = yf.download(fix_ticker(t), start=m_t['Fecha'].min(), progress=False)['Close']
                    costo_acum_usd = 0
                    total_acciones_eeuu = 0
                    
                    for _, op in m_t.iterrows():
                        try:
                            p_c_usd = h_p.loc[:op['Fecha']].ffill().iloc[-1]
                            if isinstance(p_c_usd, pd.Series): p_c_usd = p_c_usd.iloc[0]
                            cant_eeuu = op['Cantidad'] / op['Ratio']
                            costo_acum_usd += cant_eeuu * p_c_usd
                            total_acciones_eeuu += cant_eeuu
                        except: continue
                    
                    p_promedio = costo_acum_usd / total_acciones_eeuu if total_acciones_eeuu > 0 else row['Precio Hoy']
                    ret_perc = ((row['Precio Hoy'] / p_promedio) - 1) * 100
                else:
                    ret_perc = 0
                rets_posicion.append(ret_perc)
            
            df_actual['Retorno (%)'] = rets_posicion

        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"Patrimonio Total: <span class='metric-text'>USD {df_actual['Valuación USD'].sum():,.2f}</span>", unsafe_allow_html=True)
            sel_port = st.dataframe(
                df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy', 'Retorno (%)']],
                use_container_width=True, on_select="rerun", selection_mode="single-row"
            )
        with c2:
            st.plotly_chart(px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, template="plotly_dark"), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 2: DETALLE INTERACTIVO (LO QUE FALTABA) ---
    if 'sel_port' in locals() and len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        row_sel = df_actual.iloc[idx]
        t_sel = row_sel['Ticker_EEUU']
        
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="section-title">🔍 Historial de Operaciones: {t_sel}</div>', unsafe_allow_html=True)
        
        m_t_det = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
        m_t_det['Fecha'] = pd.to_datetime(m_t_det['Fecha'])
        
        with st.spinner('Analizando lotes...'):
            h_prices_det = yf.download(fix_ticker(t_sel), start=m_t_det['Fecha'].min(), progress=False)['Close']
            
            detalles = []
            for _, op in m_t_det.iterrows():
                try:
                    p_c = h_prices_det.loc[:op['Fecha']].ffill().iloc[-1]
                    if isinstance(p_c, pd.Series): p_c = p_c.iloc[0]
                    
                    rend_lote = ((row_sel['Precio Hoy'] / p_c) - 1) * 100
                    detalles.append({
                        'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                        'Operación': op['Operacion'].upper(),
                        'Acciones (USA)': op['Cantidad'] / op['Ratio'],
                        'Precio Compra (USD)': p_c,
                        'Retorno Lote (%)': rend_lote
                    })
                except: continue
            
            st.dataframe(pd.DataFrame(detalles).style.format({
                'Acciones (USA)': '{:.4f}', 'Precio Compra (USD)': '${:,.2f}', 'Retorno Lote (%)': '{:.2f}%'
            }).applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', subset=['Retorno Lote (%)']), 
            use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 3: EVOLUCIÓN HISTÓRICA ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📈 Evolución Histórica del Patrimonio</div>', unsafe_allow_html=True)
    
    @st.cache_data(ttl=3600)
    def calc_evol(_movs, _port, _tapi):
        f_i = pd.to_datetime(_movs['Fecha']).min()
        hp = yf.download(_tapi, start=f_i, progress=False)['Close']
        if isinstance(hp, pd.Series): hp = hp.to_frame(); hp.columns = _tapi
        hp.columns = [c.replace('-', '.') for c in hp.columns]
        r = pd.date_range(start=f_i, end=datetime.datetime.now())
        ev = []
        for d in r:
            s = 0
            for _, a in _port.iterrows():
                tk = a['Ticker_EEUU']
                m_h = _movs[(_movs['Ticker_EEUU'] == tk) & (pd.to_datetime(_movs['Fecha']) <= d)]
                q = (m_h[m_h['Operacion'].str.upper()=='COMPRA']['Cantidad'].sum() - m_h[m_h['Operacion'].str.upper()=='VENTA']['Cantidad'].sum()) / a['Ratio']
                if tk in hp.columns:
                    p = hp.loc[:d, tk].ffill().iloc[-1] if not hp.loc[:d, tk].empty else 0
                    s += q * p
            ev.append(s)
        return pd.DataFrame({'USD': ev}, index=r)

    df_ev = calc_evol(df_movs, df_actual, tickers_api)
    df_ev.iloc[-1] = df_actual['Valuación USD'].sum()
    st.plotly_chart(px.area(df_ev, y='USD', template="plotly_dark", color_discrete_sequence=['#00cc96']), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 4: ACTIVOS LIQUIDADOS ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏁 Activos Liquidados (USD)</div>', unsafe_allow_html=True)
    
    t_p = set(df_actual['Ticker_EEUU'].unique())
    t_l = list(set(df_movs['Ticker_EEUU'].unique()) - t_p)
    if t_l:
        res_l = []
        for t in t_l:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            h_p_l = yf.download(fix_ticker(t), start=m_t['Fecha'].min(), progress=False)['Close']
            c_usd, v_usd = 0, 0
            for _, op in m_t.iterrows():
                try:
                    p_f = h_p_l.loc[:op['Fecha']].ffill().iloc[-1]
                    if isinstance(p_f, pd.Series): p_f = p_f.iloc[0]
                    monto = (op['Cantidad'] / op['Ratio']) * p_f
                    if op['Operacion'].upper() == 'COMPRA': c_usd += monto
                    else: v_usd += monto
                except: continue
            res_l.append({'Ticker': t, 'Monto Compra (USD)': c_usd, 'Monto Venta (USD)': v_usd, 'Rendimiento': v_usd-c_usd, '%': ((v_usd/c_usd)-1)*100 if c_usd>0 else 0})
        
        df_l = pd.DataFrame(res_l)
        st.dataframe(df_l.style.format({'Monto Compra (USD)': '${:,.2f}', 'Monto Venta (USD)': '${:,.2f}', 'Rendimiento': '${:,.2f}', '%': '{:.2f}%'}), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error detectado: {e}")
