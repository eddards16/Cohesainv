import streamlit as st
import pandas as pd
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from datetime import datetime

class InventarioDashboard:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        self.SPREADSHEET_ID = '1acGspGuv-i0KSA5Q8owZpFJb1ytgm1xljBLZoa2cSN8'
        self.RANGE_NAME = 'Carnes!A1:L'
        self.df = None

    def get_credentials(self):
        """Obtiene credenciales para Google Sheets API"""
        try:
            if st.secrets.has_key("gcp_service_account"):
                credentials_dict = st.secrets["gcp_service_account"]
                creds = service_account.Credentials.from_service_account_info(
                    credentials_dict,
                    scopes=self.SCOPES
                )
                return creds
            else:
                st.error("No se encontraron credenciales en los secretos")
                return None
        except Exception as e:
            st.error(f"Error al obtener credenciales: {str(e)}")
            return None

    def load_data(self):
        """Carga datos desde Google Sheets"""
        try:
            creds = self.get_credentials()
            if not creds:
                return False

            service = build('sheets', 'v4', credentials=creds)
            sheet = service.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=self.SPREADSHEET_ID,
                range=self.RANGE_NAME
            ).execute()
            
            values = result.get('values', [])
            if not values:
                st.error("No se encontraron datos en la hoja")
                return False
                
            self.df = pd.DataFrame(values[1:], columns=values[0])
            
            # Convertir columnas numéricas
            numeric_columns = ['cajas', 'kg', 'precio', 'precio total']
            for col in numeric_columns:
                self.df[col] = pd.to_numeric(self.df[col].replace('', '0').replace('E', '0'), errors='coerce')
            
            return True
            
        except Exception as e:
            st.error(f'Error durante la carga de datos: {str(e)}')
            return False

    def calcular_stock_actual(self):
        """
        Calcula el stock actual considerando lotes y todos los almacenes
        """
        stock_data = []
        todos_productos = self.df['nombre'].unique()
        todos_lotes = self.df['lote'].unique()
        todos_almacenes = pd.concat([
            self.df['almacen'],
            self.df['almacen actual']
        ]).unique()
        
        # Limpiar almacenes
        todos_almacenes = [a for a in todos_almacenes if pd.notna(a) and str(a).strip() != '']
        
        for producto in todos_productos:
            for lote in todos_lotes:
                for almacen in todos_almacenes:
                    # Filtrar por producto, lote y almacén
                    df_filtrado = self.df[
                        (self.df['nombre'] == producto) & 
                        (self.df['lote'] == lote)
                    ]
                    
                    # 1. Entradas directas
                    entradas = df_filtrado[
                        (df_filtrado['movimiento'] == 'ENTRADA') & 
                        (df_filtrado['almacen'] == almacen)
                    ]['cajas'].sum()
                    
                    # 2. Traspasos recibidos
                    traspasos_recibidos = df_filtrado[
                        (df_filtrado['movimiento'] == 'TRASPASO') & 
                        (df_filtrado['almacen actual'] == almacen)
                    ]['cajas'].sum()
                    
                    # 3. Traspasos enviados
                    traspasos_enviados = df_filtrado[
                        (df_filtrado['movimiento'] == 'TRASPASO') & 
                        (df_filtrado['almacen'] == almacen)
                    ]['cajas'].sum()
                    
                    # 4. Salidas (ventas)
                    salidas = df_filtrado[
                        (df_filtrado['movimiento'] == 'SALIDA') & 
                        (df_filtrado['almacen'] == almacen)
                    ]['cajas'].sum()
                    # Calcular stock y totales
                    total_inicial = entradas + traspasos_recibidos
                    stock = total_inicial - traspasos_enviados - salidas
                    
                    # Calcular kg
                    kg_entradas = df_filtrado[
                        (df_filtrado['movimiento'] == 'ENTRADA') & 
                        (df_filtrado['almacen'] == almacen)
                    ]['kg'].sum()
                    
                    kg_traspasos = df_filtrado[
                        (df_filtrado['movimiento'] == 'TRASPASO') & 
                        (df_filtrado['almacen actual'] == almacen)
                    ]['kg'].sum()
                    
                    kg_salidas = df_filtrado[
                        (df_filtrado['movimiento'] == 'SALIDA') & 
                        (df_filtrado['almacen'] == almacen)
                    ]['kg'].sum()
                    
                    kg_total = kg_entradas + kg_traspasos - kg_salidas
                    
                    # Calcular porcentajes
                    if total_inicial > 0:
                        porcentaje_vendido = (salidas / total_inicial) * 100
                        porcentaje_disponible = (stock / total_inicial) * 100
                    else:
                        porcentaje_vendido = 0
                        porcentaje_disponible = 0
                    
                    # Solo agregar si hay movimientos o stock
                    if total_inicial > 0 or stock != 0:
                        stock_data.append({
                            'Almacén': almacen,
                            'Producto': producto,
                            'Lote': lote,
                            'Stock': stock,
                            'Kg Total': kg_total,
                            'Total Inicial': total_inicial,
                            'Entradas': entradas,
                            'Traspasos Recibidos': traspasos_recibidos,
                            'Traspasos Enviados': traspasos_enviados,
                            'Salidas': salidas,
                            '% Vendido': round(porcentaje_vendido, 2),
                            '% Disponible': round(porcentaje_disponible, 2)
                        })
        
        return pd.DataFrame(stock_data)

    def vista_comercial(self):
        """Vista específica para el equipo comercial"""
        st.subheader("Vista Comercial - Stock por Corte")
        
        # Obtener stock actual
        stock_df = self.calcular_stock_actual()
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            lote_filter = st.multiselect(
                "Filtrar por Lote",
                options=sorted(stock_df['Lote'].unique())
            )
        with col2:
            almacen_filter = st.multiselect(
                "Filtrar por Almacén",
                options=sorted(stock_df['Almacén'].unique())
            )
        
        # Aplicar filtros
        if lote_filter:
            stock_df = stock_df[stock_df['Lote'].isin(lote_filter)]
        if almacen_filter:
            stock_df = stock_df[stock_df['Almacén'].isin(almacen_filter)]
        
        # Crear tabs para diferentes vistas
        tab1, tab2, tab3 = st.tabs(["Resumen General", "Análisis por Producto", "Análisis por Lote"])
        with tab1:
            # Resumen general
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Stock y Porcentajes de Venta")
                resumen = stock_df.groupby('Producto').agg({
                    'Total Inicial': 'sum',
                    'Stock': 'sum',
                    'Salidas': 'sum',
                    'Kg Total': 'sum'
                }).round(2)
                
                # Calcular porcentajes totales
                resumen['% Vendido'] = (resumen['Salidas'] / resumen['Total Inicial'] * 100).round(2)
                resumen['% Disponible'] = (resumen['Stock'] / resumen['Total Inicial'] * 100).round(2)
                
                # Formatear para mostrar
                resumen_display = resumen.copy()
                resumen_display['% Vendido'] = resumen_display['% Vendido'].apply(lambda x: f"{x}%")
                resumen_display['% Disponible'] = resumen_display['% Disponible'].apply(lambda x: f"{x}%")
                
                st.dataframe(resumen_display.sort_values('% Vendido', ascending=False))
            
            with col2:
                st.markdown("### Distribución de Ventas vs Stock")
                fig = px.bar(resumen, 
                            x=resumen.index, 
                            y=['% Vendido', '% Disponible'],
                            title="Porcentaje Vendido vs Disponible por Producto",
                            barmode='stack')
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            # Análisis por producto
            producto_seleccionado = st.selectbox(
                "Seleccionar Producto",
                options=sorted(stock_df['Producto'].unique())
            )
            
            # Mostrar detalle del producto
            detalle_producto = stock_df[stock_df['Producto'] == producto_seleccionado]
            
            st.markdown(f"### Detalle de {producto_seleccionado}")
            
            # Mostrar resumen por almacén
            cols = ['Almacén', 'Lote', 'Stock', 'Total Inicial', 'Salidas', '% Vendido', '% Disponible']
            st.dataframe(detalle_producto[cols].sort_values(['Almacén', 'Lote']))
            
            # Gráficos
            col1, col2 = st.columns(2)
            
            with col1:
                # Distribución por almacén
                fig = px.pie(detalle_producto, 
                            values='Stock', 
                            names='Almacén',
                            title=f"Distribución de Stock por Almacén")
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Stock por lote
                fig = px.bar(detalle_producto,
                            x='Lote',
                            y=['Stock', 'Salidas'],
                            title=f"Stock y Salidas por Lote",
                            barmode='group')
                st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            # Análisis por lote
            st.markdown("### Análisis por Lote")
            
            resumen_lote = stock_df.groupby('Lote').agg({
                'Total Inicial': 'sum',
                'Stock': 'sum',
                'Salidas': 'sum'
            }).round(2)
            
            resumen_lote['% Vendido'] = (resumen_lote['Salidas'] / resumen_lote['Total Inicial'] * 100).round(2)
            resumen_lote['% Disponible'] = (resumen_lote['Stock'] / resumen_lote['Total Inicial'] * 100).round(2)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.dataframe(resumen_lote)
            
            with col2:
                fig = px.bar(resumen_lote,
                            x=resumen_lote.index,
                            y=['% Vendido', '% Disponible'],
                            title="Porcentajes por Lote",
                            barmode='stack')
                st.plotly_chart(fig, use_container_width=True)
    def stock_view(self):
        st.subheader("Stock Actual por Almacén")
        
        # Obtener stock actual
        stock_df = self.calcular_stock_actual()
        
        # Crear tabs para diferentes vistas
        tab1, tab2, tab3 = st.tabs(["Resumen", "Detalle por Almacén", "Movimientos"])
        
        with tab1:
            # Resumen general
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Stock Actual por Almacén")
                resumen = stock_df.groupby('Almacén').agg({
                    'Stock': 'sum',
                    'Producto': 'count',
                    'Kg Total': 'sum'
                }).round(2)
                
                # Calcular productos con stock disponible
                productos_disponibles = stock_df[stock_df['Stock'] > 0].groupby('Almacén')['Producto'].nunique()
                resumen['Productos con Stock'] = productos_disponibles
                
                resumen.columns = ['Total Cajas', 'Productos Diferentes', 'Total Kg', 'Productos Disponibles']
                st.dataframe(resumen)
                
                # Mostrar totales
                st.markdown("### Totales Generales")
                total_cajas = resumen['Total Cajas'].sum()
                total_productos = len(stock_df['Producto'].unique())
                total_kg = resumen['Total Kg'].sum()
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Cajas", f"{total_cajas:,.0f}")
                col2.metric("Total Productos", f"{total_productos}")
                col3.metric("Total Kg", f"{total_kg:,.2f}")
            
            with col2:
                st.markdown("### Distribución de Stock")
                fig = px.pie(stock_df, 
                           values='Stock', 
                           names='Almacén',
                           title="Distribución de Stock por Almacén")
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            # Selector de almacén
            almacen_seleccionado = st.selectbox(
                "Seleccionar Almacén",
                options=sorted(stock_df['Almacén'].unique())
            )
            
            # Filtro de lote
            lotes_disponibles = sorted(stock_df[stock_df['Almacén'] == almacen_seleccionado]['Lote'].unique())
            lote_seleccionado = st.multiselect("Filtrar por Lote", options=lotes_disponibles)
            
            # Filtrar datos
            stock_almacen = stock_df[stock_df['Almacén'] == almacen_seleccionado]
            if lote_seleccionado:
                stock_almacen = stock_almacen[stock_almacen['Lote'].isin(lote_seleccionado)]
            
            st.markdown(f"### Detalle de Stock en {almacen_seleccionado}")
            
            # Mostrar detalle
            detalle_cols = ['Producto', 'Lote', 'Stock', 'Total Inicial', 'Salidas', 
                           '% Vendido', '% Disponible', 'Kg Total']
            st.dataframe(stock_almacen[detalle_cols].sort_values(['Producto', 'Lote']))
            
            # Gráficos
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.bar(stock_almacen, 
                           x='Producto', 
                           y='Stock',
                           color='Lote',
                           title=f'Stock por Producto en {almacen_seleccionado}')
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = px.bar(stock_almacen,
                           x='Producto',
                           y=['Stock', 'Salidas'],
                           title=f'Stock vs Salidas en {almacen_seleccionado}',
                           barmode='group')
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
    def ventas_view(self):
        st.subheader("Análisis de Ventas")
        
        ventas = self.df[self.df['movimiento'] == 'SALIDA'].copy()
        ventas = ventas[ventas['precio'] > 0]

        if not ventas.empty:
            tab1, tab2, tab3 = st.tabs(["Resumen de Ventas", "Análisis por Cliente", "Detalle de Ventas"])
            
            with tab1:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### Top Ventas por Monto")
                    ventas_producto = ventas.groupby(['nombre', 'lote']).agg({
                        'cajas': 'sum',
                        'kg': 'sum',
                        'precio total': 'sum'
                    }).round(2)
                    ventas_producto = ventas_producto.sort_values('precio total', ascending=False)
                    st.dataframe(ventas_producto, use_container_width=True)

                with col2:
                    st.markdown("### Distribución de Ventas")
                    fig = px.pie(
                        ventas_producto.reset_index(),
                        values='precio total',
                        names='nombre',
                        title="Distribución de Ventas por Producto"
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                st.markdown("### Análisis por Cliente")
                
                # Resumen total por cliente
                resumen_cliente = ventas.groupby('cliente').agg({
                    'cajas': 'sum',
                    'kg': 'sum',
                    'precio total': 'sum'
                }).round(2)
                
                st.markdown("#### Resumen Total por Cliente")
                st.dataframe(resumen_cliente.sort_values('precio total', ascending=False))
                
                # Gráfico de distribución de ventas por cliente
                fig = px.pie(
                    resumen_cliente.reset_index(),
                    values='precio total',
                    names='cliente',
                    title="Distribución de Ventas por Cliente"
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Detalle por cliente
                cliente_seleccionado = st.selectbox(
                    "Seleccionar Cliente para ver detalle",
                    options=sorted(ventas['cliente'].unique())
                )
                
                if cliente_seleccionado:
                    st.markdown(f"#### Detalle de Ventas - {cliente_seleccionado}")
                    ventas_cliente = ventas[ventas['cliente'] == cliente_seleccionado]
                    detalle_cliente = ventas_cliente.groupby(['nombre', 'lote']).agg({
                        'cajas': 'sum',
                        'kg': 'sum',
                        'precio total': 'sum'
                    }).round(2)
                    st.dataframe(detalle_cliente.sort_values('precio total', ascending=False))
            
            with tab3:
                st.markdown("### Detalle de Ventas")
                # Filtros
                col1, col2, col3 = st.columns(3)
                with col1:
                    cliente_filter = st.multiselect(
                        "Filtrar por Cliente",
                        options=sorted(ventas['cliente'].unique())
                    )
                with col2:
                    producto_filter = st.multiselect(
                        "Filtrar por Producto",
                        options=sorted(ventas['nombre'].unique())
                    )
                with col3:
                    vendedor_filter = st.multiselect(
                        "Filtrar por Vendedor",
                        options=sorted(ventas['vendedor'].unique())
                    )
                
                # Aplicar filtros
                ventas_filtradas = ventas.copy()
                if cliente_filter:
                    ventas_filtradas = ventas_filtradas[ventas_filtradas['cliente'].isin(cliente_filter)]
                if producto_filter:
                    ventas_filtradas = ventas_filtradas[ventas_filtradas['nombre'].isin(producto_filter)]
                if vendedor_filter:
                    ventas_filtradas = ventas_filtradas[ventas_filtradas['vendedor'].isin(vendedor_filter)]
                
                # Mostrar detalle
                st.dataframe(
                    ventas_filtradas[['nombre', 'lote', 'cliente', 'vendedor', 'cajas', 'kg', 'precio', 'precio total']]
                    .sort_values(['cliente', 'nombre']),
                    use_container_width=True
                )

    def run_dashboard(self):
        st.set_page_config(page_title="Inventario COHESA", layout="wide")
        st.title("Dashboard de Inventario COHESA")

        # Información de actualización y botón de recarga
        col1, col2 = st.sidebar.columns([2,1])
        with col1:
            st.write("Última actualización:", datetime.now().strftime("%H:%M:%S"))
        with col2:
            if st.button('🔄 Actualizar'):
                st.experimental_rerun()

        if not self.load_data():
            st.error("Error al cargar los datos")
            return

        # Tabs principales
        tab1, tab2, tab3 = st.tabs(["Stock", "Ventas", "Vista Comercial"])
        
        with tab1:
            self.stock_view()
        
        with tab2:
            self.ventas_view()
        
        with tab3:
            self.vista_comercial()

if __name__ == '__main__':
    dashboard = InventarioDashboard()
    dashboard.run_dashboard()
