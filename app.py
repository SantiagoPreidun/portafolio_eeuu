# --- BUSCÁ ESTA SECCIÓN EN TU CÓDIGO Y REEMPLAZALA ---

with col1:
    st.metric("Patrimonio Total", f"USD {total_cartera:,.2f}")
    
    # CORRECCIÓN: Cambiamos names='Ticker' por names='Ticker Argy'
    fig_pie = px.pie(df, values='Total_USD', names='Ticker Argy', 
                     hole=0.4, title="Distribución por Activo")
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.subheader("📋 Desglose de Tenencia")
    # CORRECCIÓN: También actualizamos la lista de columnas para mostrar
    df_mostrar = df[[
        'Ticker Argy', 'Descripción', 'Cantidad', 'Ratio', 
        'Acciones_EEUU', 'Ticker_EEUU', 'Precio_USD', 'Total_USD'
    ]]
    
    st.dataframe(df_mostrar.style.format({
        'Acciones_EEUU': '{:.4f}',
        'Precio_USD': '${:.2f}',
        'Total_USD': '${:.2f}'
    }), use_container_width=True)

# Gráfico de barras (también corregimos el eje X)
st.divider()
fig_bar = px.bar(df, x='Ticker Argy', y='Total_USD', color='Ticker Argy',
                 title="Valorización por Ticket (USD)", text_auto='.2s')
st.plotly_chart(fig_bar, use_container_width=True)
