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

    # SECCIÓN 1: CARTERA (CON GANANCIAS Y RETORNOS USD)
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("💼 Mi Portafolio (Rendimiento Real USD)")
    
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
            
            # --- CÁLCULO DE GANANCIA Y RETORNO USD ---
            ganancias_list = []
            retornos_list = []

            for _, row in df_actual.iterrows():
                t = row['Ticker_EEUU']
                # Filtrar compras históricas para este activo
                m_t_compras = df_movs[(df_movs['Ticker_EEUU'] == t) & (df_movs['Operacion'].str.upper() == 'COMPRA')]
                
                if not m_t_compras.empty:
                    # Descargar historial para obtener el costo en USD de cada fecha
                    h_p = yf.download(fix_ticker(t), start=m_t_compras['Fecha'].min(), progress=False)['Close']
                    costo_acum_usd = 0
                    
                    for _, op in m_t_compras.iterrows():
                        try:
                            # Precio USD del activo en la fecha de compra
                            p_hist = h_p.loc[:op['Fecha']].ffill().iloc[-1]
                            if isinstance(p_hist, pd.Series): p_hist = p_hist.iloc[0]
                            # Costo lote = (Cantidad / Ratio) * Precio USD de ese día
                            costo_acum_usd += (op['Cantidad'] / op['Ratio']) * p_hist
                        except:
                            costo_acum_usd += (op['Cantidad'] / op['Ratio']) * row['Precio Hoy']
                    
                    ganancia_usd = row['Valuación USD'] - costo_acum_usd
                    retorno_perc = (ganancia_usd / costo_acum_usd * 100) if costo_acum_usd > 0 else 0
                else:
                    ganancia_usd, retorno_perc = 0, 0
                
                ganancias_list.append(ganancia_usd)
                retornos_list.append(retorno_perc)
            
            df_actual['Ganancia (USD)'] = ganancias_list
            df_actual['Retorno (%)'] = retornos_list

        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"Patrimonio Total: <span class='metric-text'>USD {df_actual['Valuación USD'].sum():,.2f}</span>", unsafe_allow_html=True)
            sel_port = st.dataframe(
                df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy', 'Ganancia (USD)', 'Retorno (%)']].style.format({
                    'Valuación USD': '${:,.2f}', 
                    'Precio Hoy': '${:,.2f}', 
                    'Ganancia (USD)': '${:,.2f}',
                    'Retorno (%)': '{:.2f}%'
                }).applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', 
                          subset=['Ganancia (USD)', 'Retorno (%)']),
                use_container_width=True, on_select="rerun", selection_mode="single-row"
            )
        with c2:
            st.plotly_chart(px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, template="plotly_dark"), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # SECCIÓN 2: DETALLE INTERACTIVO
    if len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        row_sel = df_actual.iloc[idx]
        t_sel = row_sel['Ticker_EEUU']
        
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader(f"🔍 Historial y Rendimiento: {t_sel}")
        m_t = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
        m_t['Fecha'] = pd.to_datetime(m_t['Fecha'])
        h_prices = yf.download(fix_ticker(t_sel), start=m_t['Fecha'].min(), progress=False)['Close']
        
        detalles = []
        for _, op in m_t.iterrows():
            try:
                p_compra = h_prices.loc[:op['Fecha']].ffill().iloc[-1]
                if isinstance(p_compra, pd.Series): p_compra = p_compra.iloc[0]
                rend_lote = ((row_sel['Precio Hoy'] / p_compra) - 1) * 100
                gan_lote = (op['Cantidad'] / op['Ratio']) * (row_sel['Precio Hoy'] - p_compra)
            except:
                p_compra, rend_lote, gan_lote = row_sel['Precio Hoy'], 0, 0
            
            detalles.append({
                'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                'Operación': op['Operacion'].upper(),
                'Precio Compra (USD)': float(p_compra),
                'Ganancia (USD)': float(gan_lote),
                'Retorno (%)': float(rend_lote)
            })
        
        st.dataframe(pd.DataFrame(detalles).style.format({
            'Precio Compra (USD)': '${:,.2f}', 'Ganancia (USD)': '${:,.2f}', 'Retorno (%)': '{:.2f}%'
        }).applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', 
                  subset=['Ganancia (USD)', 'Retorno (%)']), use_container_width=True)
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
                q = (m_h[m_h['Operacion'].str.upper()=='COMPRA']['Cantidad'].sum() - m_h[m_h['Operacion'].str.upper()=='VENTA']['Cantidad'].sum()) / a['Ratio']
                if tk in hp.columns:
                    p_val = hp.loc[:d, tk].ffill()
                    s += q * p_val.iloc[-1] if not p_val.empty else 0
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
            m_t_l = df_movs[df_movs['Ticker_EEUU'] == t].copy()
            h_p_l = yf.download(fix_ticker(t), start=m_t_l['Fecha'].min(), progress=False)['Close']
            c_u, v_u = 0, 0
            for _, op in m_t_l.iterrows():
                try:
                    p_l = h_p_l.loc[:op['Fecha']].ffill().iloc[-1]
                    if isinstance(p_l, pd.Series): p_l = p_l.iloc[0]
                    monto = (op['Cantidad'] / op['Ratio']) * p_l
                    if op['Operacion'].upper() == 'COMPRA': c_u += monto
                    else: v_u += monto
                except: continue
            res_l.append({'Ticker': t, 'Monto Compra': float(c_u), 'Monto Venta': float(v_u), 'Rendimiento': float(v_u-c_u), '%': float(((v_u/c_u)-1)*100 if c_u>0 else 0)})
        df_l = pd.DataFrame(res_l)
        df_tot = pd.DataFrame([{'Ticker': 'TOTAL GLOBAL', 'Monto Compra': df_l['Monto Compra'].sum(), 'Monto Venta': df_l['Monto Venta'].sum(), 'Rendimiento': df_l['Rendimiento'].sum(), '%': (df_l['Rendimiento'].sum()/df_l['Monto Compra'].sum()*100) if df_l['Monto Compra'].sum()>0 else 0}])
        st.dataframe(pd.concat([df_l, df_tot], ignore_index=True).style.format({'Monto Compra': '${:,.2f}', 'Monto Venta': '${:,.2f}', 'Rendimiento': '${:,.2f}', '%': '{:.2f}%'})
                     .apply(lambda x: ['font-weight: bold; background-color: #333' if x['Ticker'] == 'TOTAL GLOBAL' else '' for _ in x], axis=1), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error: {e}")
