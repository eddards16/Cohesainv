import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from datetime import datetime
import numpy as np

class InventarioAnalytics:
    """Clase de utilidad para cálculos y análisis"""
    @staticmethod
    def calcular_porcentaje(parte, total):
        """Calcula porcentaje con manejo de errores"""
        try:
            return round((parte / total * 100), 2) if total > 0 else 0
        except:
            return 0

    @staticmethod
    def formatear_numero(numero, decimales=2):
        """Formatea números para visualización"""
        try:
            if abs(numero) >= 1000000:
                return f"{numero/1000000:.{decimales}f}M"
            elif abs(numero) >= 1000:
                return f"{numero/1000:.{decimales}f}K"
            else:
                return f"{numero:.{decimales}f}"
        except:
            return "0"

class InventarioDashboard:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        self.SPREADSHEET_ID = '1acGspGuv-i0KSA5Q8owZpFJb1ytgm1xljBLZoa2cSN8'
        self.RANGE_NAME = 'Carnes!A1:L'
        self.df = None
        self.analytics = InventarioAnalytics()
        
        # Configuración de colores y estilos
        self.COLOR_SCHEME = {
            'primary': '#1f77b4',
            'secondary': '#ff7f0e',
            'success': '#2ca02c',
            'warning': '#d62728',
            'info': '#17becf'
        }
        
        # Configuración de estados
        self.ESTADOS_STOCK = {
            'CRÍTICO': {'umbral': 5, 'color': '#d62728'},
            'BAJO': {'umbral': 20, 'color': '#ff7f0e'},
            'NORMAL': {'umbral': float('inf'), 'color': '#2ca02c'}
        }

    def get_credentials(self):
        """Obtiene credenciales para Google Sheets API con manejo de errores mejorado"""
        try:
            if st.secrets.has_key("gcp_service_account"):
                credentials_dict = st.secrets["gcp_service_account"]
                creds = service_account.Credentials.from_service_account_info(
                    credentials_dict,
                    scopes=self.SCOPES
                )
                return creds
            else:
                # Intenta cargar credenciales locales
                if os.path.exists('client_secret.json'):
                    creds = service_account.Credentials.from_service_account_file(
                        'client_secret.json',
                        scopes=self.SCOPES
                    )
                    return creds
                else:
                    st.error("No se encontraron credenciales. Verifica la configuración.")
                    return None
        except Exception as e:
            st.error(f"Error al obtener credenciales: {str(e)}")
            return None

    def load_data(self):
        """Carga y preprocesa los datos con validaciones mejoradas"""
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
                st.error("No se encontraron datos en la hoja de cálculo")
                return False
            
            # Crear DataFrame
            self.df = pd.DataFrame(values[1:], columns=values[0])
            
            # Validar columnas requeridas
            required_columns = ['nombre', 'lote', 'movimiento', 'almacen', 'almacen actual', 
                              'cajas', 'kg', 'precio', 'precio total']
            missing_columns = [col for col in required_columns if col not in self.df.columns]
            if missing_columns:
                st.error(f"Faltan columnas requeridas: {', '.join(missing_columns)}")
                return False
            
            # Convertir y validar columnas numéricas
            numeric_columns = ['cajas', 'kg', 'precio', 'precio total']
            for col in numeric_columns:
                self.df[col] = pd.to_numeric(
                    self.df[col].replace(['', 'E', '#VALUE!', '#N/A'], '0'),
                    errors='coerce'
                ).fillna(0)
            
            # Limpiar y estandarizar datos
            self.df['movimiento'] = self.df['movimiento'].str.upper()
            self.df['almacen'] = self.df['almacen'].str.strip()
            self.df['almacen actual'] = self.df['almacen actual'].str.strip()
            
            # Validar valores únicos esperados
            movimientos_validos = {'ENTRADA', 'SALIDA', 'TRASPASO'}
            movimientos_invalidos = set(self.df['movimiento'].unique()) - movimientos_validos
            if movimientos_invalidos:
                st.warning(f"Se encontraron movimientos no estándar: {movimientos_invalidos}")
            
            return True
            
        except Exception as e:
            st.error(f"Error durante la carga de datos: {str(e)}")
            return False
    def calcular_stock_actual(self):
        """
        Calcula el stock actual con análisis detallado por producto, lote y almacén
        Incluye métricas adicionales y validaciones
        """
        try:
            stock_data = []
            todos_productos = self.df['nombre'].unique()
            todos_lotes = self.df['lote'].unique()
            todos_almacenes = pd.concat([
                self.df['almacen'],
                self.df['almacen actual']
            ]).unique()
            
            # Limpiar y validar almacenes
            todos_almacenes = [a for a in todos_almacenes if pd.notna(a) and str(a).strip() != '']
            
            for producto in todos_productos:
                for lote in todos_lotes:
                    for almacen in todos_almacenes:
                        # Filtrar datos relevantes
                        df_filtrado = self.df[
                            (self.df['nombre'] == producto) & 
                            (self.df['lote'] == lote)
                        ]
                        
                        # 1. Entradas directas
                        entradas_df = df_filtrado[
                            (df_filtrado['movimiento'] == 'ENTRADA') & 
                            (df_filtrado['almacen'] == almacen)
                        ]
                        entradas = entradas_df['cajas'].sum()
                        kg_entradas = entradas_df['kg'].sum()
                        
                        # 2. Traspasos recibidos
                        traspasos_recibidos_df = df_filtrado[
                            (df_filtrado['movimiento'] == 'TRASPASO') & 
                            (df_filtrado['almacen actual'] == almacen)
                        ]
                        traspasos_recibidos = traspasos_recibidos_df['cajas'].sum()
                        kg_traspasos_recibidos = traspasos_recibidos_df['kg'].sum()
                        
                        # 3. Traspasos enviados
                        traspasos_enviados_df = df_filtrado[
                            (df_filtrado['movimiento'] == 'TRASPASO') & 
                            (df_filtrado['almacen'] == almacen)
                        ]
                        traspasos_enviados = traspasos_enviados_df['cajas'].sum()
                        kg_traspasos_enviados = traspasos_enviados_df['kg'].sum()
                        
                        # 4. Salidas (ventas)
                        salidas_df = df_filtrado[
                            (df_filtrado['movimiento'] == 'SALIDA') & 
                            (df_filtrado['almacen'] == almacen)
                        ]
                        salidas = salidas_df['cajas'].sum()
                        kg_salidas = salidas_df['kg'].sum()
                        ventas_total = salidas_df['precio total'].sum()
                        
                        # Cálculos de stock y métricas
                        total_inicial = entradas + traspasos_recibidos
                        stock = total_inicial - traspasos_enviados - salidas
                        kg_total = kg_entradas + kg_traspasos_recibidos - kg_traspasos_enviados - kg_salidas
                        
                        # Cálculo de porcentajes
                        porcentaje_vendido = self.analytics.calcular_porcentaje(salidas, total_inicial)
                        porcentaje_disponible = self.analytics.calcular_porcentaje(stock, total_inicial)
                        
                        # Determinar estado del stock
                        estado_stock = 'NORMAL'
                        for estado, config in self.ESTADOS_STOCK.items():
                            if stock <= config['umbral']:
                                estado_stock = estado
                                break
                        
                        # Calcular métricas adicionales
                        rotacion = self.analytics.calcular_porcentaje(salidas, total_inicial) if total_inicial > 0 else 0
                        dias_inventario = 0  # TODO: Implementar cálculo de días de inventario
                        
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
                                'Ventas Total': ventas_total,
                                '% Vendido': porcentaje_vendido,
                                '% Disponible': porcentaje_disponible,
                                'Estado Stock': estado_stock,
                                'Rotación': rotacion,
                                'Días Inventario': dias_inventario,
                                'Kg Entradas': kg_entradas,
                                'Kg Traspasos Recibidos': kg_traspasos_recibidos,
                                'Kg Traspasos Enviados': kg_traspasos_enviados,
                                'Kg Salidas': kg_salidas
                            })
            
            # Convertir a DataFrame y validar resultados
            stock_df = pd.DataFrame(stock_data)
            if stock_df.empty:
                st.warning("No se encontraron datos de stock para mostrar")
                return pd.DataFrame()
                
            # Ordenar y limpiar datos
            stock_df = stock_df.sort_values(['Almacén', 'Producto', 'Lote'])
            stock_df = stock_df.round(2)
            
            return stock_df
            
        except Exception as e:
            st.error(f"Error en el cálculo de stock: {str(e)}")
            return pd.DataFrame()

    def calcular_metricas_generales(self, stock_df):
        """Calcula métricas generales del inventario"""
        try:
            metricas = {
                'Total Productos': len(stock_df['Producto'].unique()),
                'Total Almacenes': len(stock_df['Almacén'].unique()),
                'Total Lotes': len(stock_df['Lote'].unique()),
                'Total Cajas en Stock': stock_df['Stock'].sum(),
                'Total Kg en Stock': stock_df['Kg Total'].sum(),
                'Total Ventas ($)': stock_df['Ventas Total'].sum(),
                'Productos en Estado Crítico': len(stock_df[stock_df['Estado Stock'] == 'CRÍTICO']),
                'Rotación Promedio (%)': stock_df['Rotación'].mean()
            }
            
            return metricas
            
        except Exception as e:
            st.error(f"Error en el cálculo de métricas generales: {str(e)}")
            return {}
    def generar_grafico_stock(self, stock_df, tipo='barras', titulo='', filtro=None):
        """Genera gráficos personalizados para el análisis de stock"""
        try:
            if stock_df.empty:
                return None

            if filtro:
                stock_df = stock_df[filtro]

            if tipo == 'barras':
                fig = px.bar(
                    stock_df,
                    x='Producto',
                    y='Stock',
                    color='Estado Stock',
                    color_discrete_map={
                        'CRÍTICO': self.ESTADOS_STOCK['CRÍTICO']['color'],
                        'BAJO': self.ESTADOS_STOCK['BAJO']['color'],
                        'NORMAL': self.ESTADOS_STOCK['NORMAL']['color']
                    },
                    title=titulo
                )
                fig.update_layout(
                    xaxis_tickangle=-45,
                    height=500,
                    showlegend=True,
                    legend_title_text='Estado de Stock'
                )
            
            elif tipo == 'pie':
                fig = px.pie(
                    stock_df,
                    values='Stock',
                    names='Almacén',
                    title=titulo
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
            
            elif tipo == 'treemap':
                fig = px.treemap(
                    stock_df,
                    path=['Almacén', 'Producto'],
                    values='Stock',
                    color='Estado Stock',
                    color_discrete_map={
                        'CRÍTICO': self.ESTADOS_STOCK['CRÍTICO']['color'],
                        'BAJO': self.ESTADOS_STOCK['BAJO']['color'],
                        'NORMAL': self.ESTADOS_STOCK['NORMAL']['color']
                    },
                    title=titulo
                )
            
            return fig

        except Exception as e:
            st.error(f"Error al generar gráfico: {str(e)}")
            return None

    def vista_comercial(self):
        """Vista específica para el equipo comercial con análisis detallado"""
        st.subheader("Vista Comercial - Análisis de Stock y Ventas")
        
        # Obtener datos de stock
        stock_df = self.calcular_stock_actual()
        if stock_df.empty:
            st.warning("No hay datos disponibles para mostrar")
            return

        # Filtros superiores
        col1, col2, col3 = st.columns(3)
        with col1:
            lote_filter = st.multiselect(
                "Filtrar por Lote",
                options=sorted(stock_df['Lote'].unique()),
                key="comercial_lote_filter"
            )
        with col2:
            almacen_filter = st.multiselect(
                "Filtrar por Almacén",
                options=sorted(stock_df['Almacén'].unique()),
                key="comercial_almacen_filter"
            )
        with col3:
            estado_filter = st.multiselect(
                "Filtrar por Estado",
                options=sorted(stock_df['Estado Stock'].unique()),
                key="comercial_estado_filter"
            )

        # Aplicar filtros
        df_filtered = stock_df.copy()
        if lote_filter:
            df_filtered = df_filtered[df_filtered['Lote'].isin(lote_filter)]
        if almacen_filter:
            df_filtered = df_filtered[df_filtered['Almacén'].isin(almacen_filter)]
        if estado_filter:
            df_filtered = df_filtered[df_filtered['Estado Stock'].isin(estado_filter)]

        # Tabs para diferentes vistas
        tab1, tab2, tab3 = st.tabs(["Resumen General", "Análisis por Producto", "Análisis por Almacén"])

        with tab1:
            # Métricas principales
            metricas = self.calcular_metricas_generales(df_filtered)
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Total Cajas en Stock",
                    f"{metricas['Total Cajas en Stock']:,.0f}",
                    delta=None
                )
            with col2:
                st.metric(
                    "Total Kg en Stock",
                    f"{metricas['Total Kg en Stock']:,.2f}",
                    delta=None
                )
            with col3:
                st.metric(
                    "Productos en Estado Crítico",
                    f"{metricas['Productos en Estado Crítico']}",
                    delta=None
                )
            with col4:
                st.metric(
                    "Rotación Promedio",
                    f"{metricas['Rotación Promedio (%)']:.1f}%",
                    delta=None
                )

            # Gráficos de resumen
            col1, col2 = st.columns(2)
            with col1:
                fig_stock = self.generar_grafico_stock(
                    df_filtered,
                    tipo='barras',
                    titulo='Stock por Producto y Estado'
                )
                if fig_stock:
                    st.plotly_chart(fig_stock, use_container_width=True)

            with col2:
                fig_dist = self.generar_grafico_stock(
                    df_filtered,
                    tipo='treemap',
                    titulo='Distribución de Stock por Almacén y Producto'
                )
                if fig_dist:
                    st.plotly_chart(fig_dist, use_container_width=True)

        with tab2:
            # Análisis por Producto
            st.markdown("### Análisis Detallado por Producto")
            
            # Selector de producto
            producto_seleccionado = st.selectbox(
                "Seleccionar Producto",
                options=sorted(df_filtered['Producto'].unique()),
                key="comercial_producto_selector"
            )
            
            if producto_seleccionado:
                df_producto = df_filtered[df_filtered['Producto'] == producto_seleccionado]
                
                # Métricas del producto
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(
                        "Stock Total",
                        f"{df_producto['Stock'].sum():,.0f} cajas",
                        delta=None
                    )
                with col2:
                    st.metric(
                        "Kg Totales",
                        f"{df_producto['Kg Total'].sum():,.2f} kg",
                        delta=None
                    )
                with col3:
                    ventas_totales = df_producto['Ventas Total'].sum()
                    st.metric(
                        "Ventas Totales",
                        f"${ventas_totales:,.0f}",
                        delta=None
                    )
                with col4:
                    rotacion_promedio = df_producto['Rotación'].mean()
                    st.metric(
                        "Rotación",
                        f"{rotacion_promedio:.1f}%",
                        delta=None
                    )
                
                # Detalle por almacén y lote
                st.markdown("#### Detalle por Almacén y Lote")
                detalle_cols = ['Almacén', 'Lote', 'Stock', 'Kg Total', 'Total Inicial', 
                              'Salidas', '% Vendido', '% Disponible', 'Estado Stock']
                st.dataframe(
                    df_producto[detalle_cols].sort_values(['Almacén', 'Lote']),
                    use_container_width=True
                )
                
                # Gráficos de análisis
                col1, col2 = st.columns(2)
                with col1:
                    # Distribución por almacén
                    fig_dist_almacen = px.pie(
                        df_producto,
                        values='Stock',
                        names='Almacén',
                        title=f"Distribución de Stock por Almacén - {producto_seleccionado}"
                    )
                    st.plotly_chart(fig_dist_almacen, use_container_width=True)
                
                with col2:
                    # Evolución de ventas y stock
                    fig_evolucion = px.bar(
                        df_producto,
                        x='Lote',
                        y=['Stock', 'Salidas'],
                        title=f"Stock vs Salidas por Lote - {producto_seleccionado}",
                        barmode='group'
                    )
                    st.plotly_chart(fig_evolucion, use_container_width=True)

        with tab3:
            # Análisis por Almacén
            st.markdown("### Análisis Detallado por Almacén")
            
            # Selector de almacén
            almacen_seleccionado = st.selectbox(
                "Seleccionar Almacén",
                options=sorted(df_filtered['Almacén'].unique()),
                key="comercial_almacen_selector"
            )
            
            if almacen_seleccionado:
                df_almacen = df_filtered[df_filtered['Almacén'] == almacen_seleccionado]
                
                # Métricas del almacén
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        "Total Productos",
                        f"{len(df_almacen['Producto'].unique())}",
                        delta=None
                    )
                with col2:
                    st.metric(
                        "Stock Total",
                        f"{df_almacen['Stock'].sum():,.0f} cajas",
                        delta=None
                    )
                with col3:
                    st.metric(
                        "Productos Críticos",
                        f"{len(df_almacen[df_almacen['Estado Stock'] == 'CRÍTICO'])}",
                        delta=None
                    )
                
                # Análisis de stock
                st.markdown("#### Estado de Stock por Producto")
                
                # Crear tabla de resumen
                resumen_stock = df_almacen.groupby('Producto').agg({
                    'Stock': 'sum',
                    'Kg Total': 'sum',
                    'Total Inicial': 'sum',
                    'Salidas': 'sum',
                    '% Vendido': 'mean',
                    '% Disponible': 'mean'
                }).round(2)
                
                # Agregar estado de stock
                def determinar_estado(stock):
                    for estado, config in self.ESTADOS_STOCK.items():
                        if stock <= config['umbral']:
                            return estado
                    return 'NORMAL'
                
                resumen_stock['Estado'] = resumen_stock['Stock'].apply(determinar_estado)
                
                # Mostrar resumen
                st.dataframe(
                    resumen_stock.sort_values('Stock', ascending=False),
                    use_container_width=True
                )
                
                # Gráficos de análisis
                col1, col2 = st.columns(2)
                with col1:
                    # Stock por producto
                    fig_stock = px.bar(
                        df_almacen,
                        x='Producto',
                        y='Stock',
                        color='Estado Stock',
                        title=f"Stock por Producto - {almacen_seleccionado}"
                    )
                    fig_stock.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_stock, use_container_width=True)
                
                with col2:
                    # Distribución de estados
                    fig_estados = px.pie(
                        df_almacen,
                        names='Estado Stock',
                        values='Stock',
                        title=f"Distribución por Estado de Stock - {almacen_seleccionado}"
                    )
                    st.plotly_chart(fig_estados, use_container_width=True)
    def ventas_view(self):
        """Vista detallada de ventas y análisis comercial"""
        st.subheader("Análisis de Ventas")
        
        # Filtrar solo ventas con precio
        ventas = self.df[self.df['movimiento'] == 'SALIDA'].copy()
        ventas = ventas[ventas['precio'] > 0]

        if ventas.empty:
            st.warning("No hay datos de ventas disponibles")
            return

        # Crear tabs para diferentes vistas
        tab1, tab2, tab3 = st.tabs(["Resumen de Ventas", "Análisis por Cliente", "Detalle de Ventas"])
        
        with tab1:
            # Métricas principales de ventas
            total_ventas = ventas['precio total'].sum()
            total_kg = ventas['kg'].sum()
            total_cajas = ventas['cajas'].sum()
            precio_promedio = total_ventas / total_kg if total_kg > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Ventas", f"${total_ventas:,.0f}")
            with col2:
                st.metric("Total Kg Vendidos", f"{total_kg:,.2f}")
            with col3:
                st.metric("Total Cajas Vendidas", f"{total_cajas:,.0f}")
            with col4:
                st.metric("Precio Promedio/Kg", f"${precio_promedio:,.2f}")

            # Análisis por producto
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### Top Ventas por Monto")
                ventas_producto = ventas.groupby(['nombre', 'lote']).agg({
                    'cajas': 'sum',
                    'kg': 'sum',
                    'precio total': 'sum'
                }).round(2)
                ventas_producto = ventas_producto.sort_values('precio total', ascending=False)
                
                # Calcular porcentajes
                ventas_producto['% del Total'] = (ventas_producto['precio total'] / total_ventas * 100).round(2)
                ventas_producto['Precio/Kg'] = (ventas_producto['precio total'] / ventas_producto['kg']).round(2)
                
                st.dataframe(ventas_producto, use_container_width=True)

            with col2:
                # Gráfico de distribución de ventas
                fig = px.pie(
                    ventas_producto.reset_index(),
                    values='precio total',
                    names='nombre',
                    title="Distribución de Ventas por Producto"
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.markdown("### Análisis por Cliente")
            
            # Resumen por cliente
            ventas_cliente = ventas.groupby('cliente').agg({
                'cajas': 'sum',
                'kg': 'sum',
                'precio total': 'sum'
            }).round(2)
            
            # Calcular métricas adicionales
            ventas_cliente['% del Total'] = (ventas_cliente['precio total'] / total_ventas * 100).round(2)
            ventas_cliente['Precio/Kg'] = (ventas_cliente['precio total'] / ventas_cliente['kg']).round(2)
            ventas_cliente = ventas_cliente.sort_values('precio total', ascending=False)
            
            # Mostrar resumen
            st.markdown("#### Resumen de Ventas por Cliente")
            st.dataframe(ventas_cliente, use_container_width=True)
            
            # Selector de cliente para detalle
            cliente_seleccionado = st.selectbox(
                "Seleccionar Cliente para ver detalle",
                options=sorted(ventas['cliente'].unique()),
                key="ventas_cliente_selector"
            )
            
            if cliente_seleccionado:
                st.markdown(f"#### Detalle de Ventas - {cliente_seleccionado}")
                ventas_detalle = ventas[ventas['cliente'] == cliente_seleccionado]
                
                # Resumen por producto para el cliente seleccionado
                detalle_cliente = ventas_detalle.groupby(['nombre', 'lote']).agg({
                    'cajas': 'sum',
                    'kg': 'sum',
                    'precio total': 'sum',
                    'precio': 'mean'
                }).round(2)
                
                st.dataframe(detalle_cliente.sort_values('precio total', ascending=False))
                
                # Gráficos de análisis
                col1, col2 = st.columns(2)
                with col1:
                    fig = px.pie(
                        detalle_cliente.reset_index(),
                        values='precio total',
                        names='nombre',
                        title=f"Distribución de Compras - {cliente_seleccionado}"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    fig = px.bar(
                        detalle_cliente.reset_index(),
                        x='nombre',
                        y=['cajas', 'kg'],
                        title=f"Cantidades por Producto - {cliente_seleccionado}",
                        barmode='group'
                    )
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)

        with tab3:
            st.markdown("### Detalle de Ventas")
            
            # Filtros
            col1, col2, col3 = st.columns(3)
            with col1:
                cliente_filter = st.multiselect(
                    "Filtrar por Cliente",
                    options=sorted(ventas['cliente'].unique()),
                    key="ventas_cliente_filter"
                )
            with col2:
                producto_filter = st.multiselect(
                    "Filtrar por Producto",
                    options=sorted(ventas['nombre'].unique()),
                    key="ventas_producto_filter"
                )
            with col3:
                vendedor_filter = st.multiselect(
                    "Filtrar por Vendedor",
                    options=sorted([v for v in ventas['vendedor'].unique() if str(v).strip()]),
                    key="ventas_vendedor_filter"
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
                ventas_filtradas[[
                    'nombre', 'lote', 'cliente', 'vendedor', 'cajas', 'kg', 
                    'precio', 'precio total'
                ]].sort_values(['cliente', 'nombre']),
                use_container_width=True
            )

    def run_dashboard(self):
        """Función principal para ejecutar el dashboard"""
        st.set_page_config(page_title="Inventario COHESA", layout="wide")
        st.title("Dashboard de Inventario COHESA")

        # Información de actualización y botón de recarga
        col1, col2 = st.sidebar.columns([2,1])
        with col1:
            st.write("Última actualización:", datetime.now().strftime("%H:%M:%S"))
        with col2:
            if st.button('🔄 Actualizar', key="refresh_button"):
                st.cache_data.clear()
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
