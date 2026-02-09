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
        font-size: 20px;
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
    st.error("Error en credenciales de Airtable. Verificá los Secrets.")
    st.stop()

def fix_ticker(t):
    return str(t).strip().replace('.', '-')

# --- 2. EJECUCIÓN PRINCIPAL ---
try:
    # Carga de datos desde Airtable
    df_actual = pd.DataFrame([r['fields'] for r in table_port.all()])
    df_movs = pd.DataFrame([r['fields'] for r in table_movs.all()])
    df_actual.columns = [c.strip() for c in df_actual.columns]
    df_movs.columns = [c.strip() for c in df_movs.columns]
    
    col_dinero = next((c for c in df_movs.columns if c in ['Importe', 'Total Pesos', 'Monto']), 'Importe')

    # --- SECCIÓN 1: TENENCIA ACTUAL CON RETORNO (%) ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">💼 Mi Portafolio (Tenencia Actual)</div>', unsafe_allow_html=True)
    
    if not df_actual.empty:
        tickers_api = [fix_ticker(t) for t in df_actual['Ticker_EEUU'].unique()]
        with st.spinner('Actualizando precios y retornos...'):
            data_now = yf.download(tickers_api, period="1d", progress=False)['Close']
            
            if len(tickers_api) > 1:
                precios_dict = {k.replace('-', '.'): v for k, v in data_now.iloc[-1].to_dict().items()}
            else:
                precios_dict = {df_actual['Ticker_EEUU'].iloc[0]: float(data_now.iloc[-1])}

            df_actual['Precio Hoy'] = df_actual['Ticker_EEUU'].map(precios_dict)
            df_actual['Valuación USD'] = (df_actual['Cantidad'] / df_actual['Ratio']) * df_actual['Precio Hoy']
            
            # Cálculo de Retorno Totalizado por Posición
            rets_posicion = []
            for _, row in df_actual.iterrows():
                t = row['Ticker_EEUU']
                # Buscamos solo compras de este activo
                m_t = df_movs[(df_movs['Ticker_EEUU'] == t) & (df_movs['Operacion'].str.strip().str.upper() == 'COMPRA')]
                
                costo_total_usd = 0
                for _, op in m_t.iterrows():
                    try:
                        # Buscamos precio histórico en USD para dolarizar la compra
                        fecha_dt = pd.to_datetime(op['Fecha'])
                        h_p = yf.download(fix_ticker(t), start=fecha_dt, end=fecha_dt + datetime.timedelta(days=4), progress=False)['Close']
                        p_c = h_p.iloc[0] if not h_p.empty else row['Precio Hoy']
                        costo_total_usd += (op['Cantidad'] / op['Ratio']) * p_c
                    except:
                        costo_total_usd += 0
                
                ret_perc = ((row['Valuación USD'] / costo_total_usd) - 1) * 100 if costo_total_usd > 0 else 0
                rets_posicion.append(ret_perc)
            
            df_actual['Retorno (%)'] = rets_posicion

        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"Patrimonio Total: <span class='metric-text'>USD {df_actual['Valuación USD'].sum():,.2f}</span>", unsafe_allow_html=True)
            sel_port = st.dataframe(
                df_actual[['Ticker_EEUU', 'Cantidad', 'Ratio', 'Valuación USD', 'Precio Hoy', 'Retorno (%)']].style.format({
                    'Valuación USD': '${:,.2f}', 'Precio Hoy': '${:,.2f}', 'Retorno (%)': '{:.2f}%'
                }).applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', subset=['Retorno (%)']),
                use_container_width=True, on_select="rerun", selection_mode="single-row"
            )
        with c2:
            st.plotly_chart(px.pie(df_actual, values='Valuación USD', names='Ticker_EEUU', hole=0.4, template="plotly_dark"), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 2: DETALLE 100% USD (DRILL-DOWN) ---
    if len(sel_port.selection.rows) > 0:
        idx = sel_port.selection.rows[0]
        row_sel = df_actual.iloc[idx]
        t_sel = row_sel['Ticker_EEUU']
        
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="section-title">🔍 Análisis de Rendimiento USD: {t_sel}</div>', unsafe_allow_html=True)
        m_t_det = df_movs[df_movs['Ticker_EEUU'] == t_sel].copy()
        m_t_det['Fecha'] = pd.to_datetime(m_t_det['Fecha'])
        
        h_prices_det = yf.download(fix_ticker(t_sel), start=m_t_det['Fecha'].min(), progress=False)['Close']
        
        detalles = []
        for _, op in m_t_det.iterrows():
            try:
                p_c = h_prices_det.loc[:op['Fecha']].iloc[-1]
                if isinstance(p_c, pd.Series): p_c = p_c.iloc[0]
            except:
                p_c = row_sel['Precio Hoy']
            
            c_usa = op['Cantidad'] / op['Ratio']
            detalles.append({
                'Fecha': op['Fecha'].strftime('%d/%m/%Y'),
                'Operación': op['Operacion'].upper(),
                'Acciones (USA)': c_usa,
                'Precio Compra (USD)': float(p_c),
                'Rendimiento (%)': float(((row_sel['Precio Hoy'] / p_c) - 1) * 100)
            })
        
        st.dataframe(pd.DataFrame(detalles).style.format({'Acciones (USA)': '{:.4f}', 'Precio Compra (USD)': '${:,.2f}', 'Rendimiento (%)': '{:.2f}%'})
                     .applymap(lambda x: 'color: #ff4b4b' if isinstance(x, (float, int)) and x < 0 else 'color: #00cc96', subset=['Rendimiento (%)']), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 3: EVOLUCIÓN GLOBAL (ESTÁTICA) ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📈 Evolución Histórica del Patrimonio</div>', unsafe_allow_html=True)
    
    @st.cache_data(ttl=3600)
    def calcular_evol_estatica(_movs, _port, _tapi):
        f_i = pd.to_datetime(_movs['Fecha']).min()
        hp = yf.download(_tapi, start=f_i, progress=False)['Close']
        if isinstance(hp, pd.Series): hp = hp.to_frame(); hp.columns = _tapi
        hp.columns = [c.replace('-', '.') for c in hp.columns]
        
        rango = pd.date_range(start=f_i, end=datetime.datetime.now())
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

    df_ev = calcular_evol_estatica(df_movs, df_actual, [fix_ticker(t) for t in df_actual['Ticker_EEUU'].unique()])
    df_ev.iloc[-1] = df_actual['Valuación USD'].sum()
    st.plotly_chart(px.area(df_ev, y='USD', template="plotly_dark", color_discrete_sequence=['#00cc96']), use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- SECCIÓN 4: ACTIVOS LIQUIDADOS ---
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏁 Activos Liquidados (Ganancias Realizadas)</div>', unsafe_allow_html=True)
    
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
    else:
        st.info("No hay activos liquidados.")
    st.markdown('</div>', unsafe_allow_html=True)

except Exception as e:
    st.error(f"Error detectado: {e}")
