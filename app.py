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

    # SECCIÓN 1: CARTERA
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("💼 Mi Portafolio")
    
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
            sel_port = st.dataframe(df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy']], 
                                    use_container_width=True, on_select="rerun", selection_mode="single-row")
        with c2:
            st.plotly_chart(px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, template="plotly_dark"), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # SECCIÓN 2: DETALLE USD
    if len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        row_sel = df_actual.iloc[idx]
        t_sel = row_sel['Ticker_EEUU']
        
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader(f"🔍 Rendimiento USD: {t_sel}")
        m_t = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
        m_t['Fecha'] = pd.to_datetime(m_t['Fecha'])
        h_prices = yf.download(fix_ticker(t_sel), start=m_t['Fecha'].min(), progress=False)['Close']
        
        detalles = []
        for _, op in m_t.iterrows():
            try:
                p_compra = h_prices.loc[:op['Fecha']].iloc[-1]
                if isinstance(p_compra, pd.Series): p_compra = p_compra.iloc[0]
            except:
                p_compra = row_sel['Precio Hoy']
            
            c_usa = op['Cantidad'] / op['Ratio']
            detalles.append({
                'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                'Precio Compra (USD)': float(p_compra),
                'Rendimiento (%)': float(((row_sel['Precio Hoy'] / p_compra) - 1) * 100)
            })
        
        st.dataframe(pd.DataFrame(detalles).style.format({'Precio Compra (USD)': '${:,.2f}', 'Rendimiento (%)': '{:.2f}%'})
                     .applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', subset=['Rendimiento (%)']), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # SECCIÓN 3: EVOLUCIÓN
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("📈 Evolución Global")
    @st.cache_data(ttl=3600)
    def calc_ev(_m, _p, _t):
        f_i = pd.to_datetime(_m['Fecha']).min()
        hp = yf.download(_t, start=f_i, progress=False)['Close']
        if isinstance(hp, pd.Series): hp = hp.to_frame(); hp.columns = _t
        hp.columns = [c.replace('-', '.') for c in hp.columns]
        r = pd.date_range(start=f_i, end=datetime.datetime.now())
        ev = []
        for d in r:
            s = 0
            for _, a in _p.iterrows():
                tk = a['Ticker_EEUU']
                m_h = _m[(_m['Ticker_EEUU'] == tk) & (pd.to_datetime(_m['Fecha']) <= d)]
                q = m_h[m_h['Operacion'].str.upper()=='COMPRA']['Cantidad'].sum() - m_h[m_h['Operacion'].str.upper()=='VENTA']['Cantidad'].sum()
                if tk in hp.columns:
                    s += (q / a['Ratio']) * hp.loc[:d, tk].ffill().iloc[-1]
            ev.append(s)
        return pd.DataFrame({'USD': ev}, index=r)

    df_ev = calc_ev(df_movs, df_actual, tickers_api)
    df_ev.iloc[-1] = df_actual['Valuación USD'].sum()
    st.plotly_chart(px.area(df_ev, y='USD', template="plotly_dark", color_discrete_sequence=['#00cc96']), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # SECCIÓN 4: LIQUIDADOS
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("🏁 Activos Liquidados")
    t_p = set(df_actual['Ticker_EEUU'].unique())
    t_l = list(set(df_movs['Ticker_EEUU'].unique()) - t_p)
    if t_l:
        res_l = []
        for t in t_l:
            m_t = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            c = m_t[m_t['Operacion'].str.upper()=='COMPRA'][col_dinero].sum()
            v = m_t[m_t['Operacion'].str.upper()=='VENTA'][col_dinero].sum()
            res_l.append({'Ticker': t, 'Monto Compra': float(c), 'Monto Venta': float(v), 'Rendimiento': float(v-c), '%': float(((v/c)-1)*100 if c>0 else 0)})
        df_l = pd.DataFrame(res_l)
        df_tot = pd.DataFrame([{'Ticker': 'TOTAL GLOBAL', 'Monto Compra': df_l['Monto Compra'].sum(), 'Monto Venta': df_l['Monto Venta'].sum(), 'Rendimiento': df_l['Rendimiento'].sum(), '%': (df_l['Rendimiento'].sum()/df_l['Monto Compra'].sum()*100) if df_l['Monto Compra'].sum()>0 else 0}])
        st.dataframe(pd.concat([df_l, df_tot], ignore_index=True).style.format({'Monto Compra': '${:,.2f}', 'Monto Venta': '${:,.2f}', 'Rendimiento': '${:,.2f}', '%': '{:.2f}%'})
                     .apply(lambda x: ['font-weight: bold; background-color: #333' if x['Ticker'] == 'TOTAL GLOBAL' else '' for _ in x], axis=1), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error: {e}")
