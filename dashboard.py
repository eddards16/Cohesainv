import streamlit as st
# Configuración de la página - DEBE SER LA PRIMERA LÍNEA DE STREAMLIT
st.set_page_config(
    page_title="Inventario COHESA",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from datetime import datetime
import numpy as np

# Aplicar estilos CSS personalizados
st.markdown("""
    <style>
    .main {
        padding: 1rem 1rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 16px;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .st-emotion-cache-1wivap2 {
        background-color: #ffffff;
        border-radius: 5px;
        padding: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    h1 {
        color: #1f77b4;
        font-weight: bold;
        padding: 1rem 0;
    }
    h2, h3 {
        color: #2c3e50;
        padding: 0.5rem 0;
    }
    .stAlert {
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

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
        
        # Esquema de colores mejorado
        self.COLOR_SCHEME = {
            'primary': '#1f77b4',
            'secondary': '#ff7f0e',
            'success': '#2ecc71',
            'warning': '#e74c3c',
            'info': '#3498db',
            'background': '#f8f9fa',
            'text': '#2c3e50'
        }
        
        # Estados de stock con colores mejorados
        self.ESTADOS_STOCK = {
            'CRÍTICO': {'umbral': 5, 'color': '#e74c3c'},
            'BAJO': {'umbral': 20, 'color': '#f39c12'},
            'NORMAL': {'umbral': float('inf'), 'color': '#2ecc71'}
        }
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
                if os.path.exists('client_secret.json'):
                    creds = service_account.Credentials.from_service_account_file(
                        'client_secret.json',
                        scopes=self.SCOPES
                    )
                    return creds
                else:
                    st.error("🔑 No se encontraron credenciales. Verifica la configuración.")
                    return None
        except Exception as e:
            st.error(f"⚠️ Error al obtener credenciales: {str(e)}")
            return None

    def load_data(self):
        """Carga y preprocesa los datos con validaciones mejoradas"""
        try:
            with st.spinner('Cargando datos...'):
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
                    st.error("📊 No se encontraron datos en la hoja de cálculo")
                    return False
                
                # Crear DataFrame con validaciones mejoradas
                self.df = pd.DataFrame(values[1:], columns=values[0])
                
                # Validar columnas requeridas
                required_columns = ['nombre', 'lote', 'movimiento', 'almacen', 'almacen actual', 
                                'cajas', 'kg', 'precio', 'precio total']
                missing_columns = [col for col in required_columns if col not in self.df.columns]
                if missing_columns:
                    st.error(f"❌ Faltan columnas requeridas: {', '.join(missing_columns)}")
                    return False
                
                # Convertir y validar columnas numéricas con mejor manejo de errores
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
                
                # Validar movimientos
                movimientos_validos = {'ENTRADA', 'SALIDA', 'TRASPASO'}
                movimientos_invalidos = set(self.df['movimiento'].unique()) - movimientos_validos
                if movimientos_invalidos:
                    st.warning(f"⚠️ Se encontraron movimientos no estándar: {', '.join(movimientos_invalidos)}")
                
                st.success("✅ Datos cargados exitosamente")
                return True
                
        except Exception as e:
            st.error(f"❌ Error durante la carga de datos: {str(e)}")
            return False

    def calcular_stock_actual(self):
        """Calcula el stock actual con análisis detallado"""
        try:
            with st.spinner('Calculando stock actual...'):
                stock_data = []
                todos_productos = self.df['nombre'].unique()
                todos_lotes = self.df['lote'].unique()
                todos_almacenes = pd.concat([
                    self.df['almacen'],
                    self.df['almacen actual']
                ]).unique()
                
                # Limpiar almacenes
                todos_almacenes = [a for a in todos_almacenes if pd.notna(a) and str(a).strip() != '']
                
                # Barra de progreso
                progress_bar = st.progress(0)
                total_items = len(todos_productos) * len(todos_lotes) * len(todos_almacenes)
                current_item = 0

                for producto in todos_productos:
                    for lote in todos_lotes:
                        for almacen in todos_almacenes:
                            # Actualizar progreso
                            current_item += 1
                            progress_bar.progress(current_item / total_items)
                            # Filtrar datos relevantes
                            df_filtrado = self.df[
                                (self.df['nombre'] == producto) & 
                                (self.df['lote'] == lote)
                            ]
                            
                            # Calcular movimientos
                            entradas_df = df_filtrado[
                                (df_filtrado['movimiento'] == 'ENTRADA') & 
                                (df_filtrado['almacen'] == almacen)
                            ]
                            entradas = entradas_df['cajas'].sum()
                            kg_entradas = entradas_df['kg'].sum()
                            
                            traspasos_recibidos_df = df_filtrado[
                                (df_filtrado['movimiento'] == 'TRASPASO') & 
                                (df_filtrado['almacen actual'] == almacen)
                            ]
                            traspasos_recibidos = traspasos_recibidos_df['cajas'].sum()
                            kg_traspasos_recibidos = traspasos_recibidos_df['kg'].sum()
                            
                            traspasos_enviados_df = df_filtrado[
                                (df_filtrado['movimiento'] == 'TRASPASO') & 
                                (df_filtrado['almacen'] == almacen)
                            ]
                            traspasos_enviados = traspasos_enviados_df['cajas'].sum()
                            kg_traspasos_enviados = traspasos_enviados_df['kg'].sum()
                            
                            salidas_df = df_filtrado[
                                (df_filtrado['movimiento'] == 'SALIDA') & 
                                (df_filtrado['almacen'] == almacen)
                            ]
                            salidas = salidas_df['cajas'].sum()
                            kg_salidas = salidas_df['kg'].sum()
                            ventas_total = salidas_df['precio total'].sum()
                            
                            # Cálculos finales
                            total_inicial = entradas + traspasos_recibidos
                            stock = total_inicial - traspasos_enviados - salidas
                            kg_total = kg_entradas + kg_traspasos_recibidos - kg_traspasos_enviados - kg_salidas
                            
                            # Calcular métricas
                            porcentaje_vendido = self.analytics.calcular_porcentaje(salidas, total_inicial)
                            porcentaje_disponible = self.analytics.calcular_porcentaje(stock, total_inicial)
                            rotacion = self.analytics.calcular_porcentaje(salidas, total_inicial) if total_inicial > 0 else 0
                            
                            # Determinar estado del stock
                            estado_stock = 'NORMAL'
                            for estado, config in self.ESTADOS_STOCK.items():
                                if stock <= config['umbral']:
                                    estado_stock = estado
                                    break
                            
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
                                    'Días Inventario': 0,
                                    'Kg Entradas': kg_entradas,
                                    'Kg Traspasos Recibidos': kg_traspasos_recibidos,
                                    'Kg Traspasos Enviados': kg_traspasos_enviados,
                                    'Kg Salidas': kg_salidas
                                })
                
                # Limpiar barra de progreso
                progress_bar.empty()
                
                # Crear DataFrame final
                stock_df = pd.DataFrame(stock_data)
                if stock_df.empty:
                    st.warning("📊 No se encontraron datos de stock para mostrar")
                    return pd.DataFrame()
                    
                stock_df = stock_df.sort_values(['Almacén', 'Producto', 'Lote'])
                stock_df = stock_df.round(2)
                
                return stock_df
                
        except Exception as e:
            st.error(f"❌ Error en el cálculo de stock: {str(e)}")
            return pd.DataFrame()

    def generar_grafico_stock(self, stock_df, tipo='barras', titulo='', filtro=None):
        """Genera gráficos personalizados para el análisis de stock"""
        try:
            if stock_df.empty:
                return None

            if filtro:
                stock_df = stock_df[filtro]

            # Configuración común de estilo
            layout_config = {
                'paper_bgcolor': 'rgba(0,0,0,0)',
                'plot_bgcolor': 'rgba(0,0,0,0)',
                'font': {'color': self.COLOR_SCHEME['text']},
                'title': {
                    'font': {'size': 20, 'color': self.COLOR_SCHEME['text']},
                    'x': 0.5,
                    'xanchor': 'center'
                },
                'showlegend': True,
                'legend': {'bgcolor': 'rgba(255,255,255,0.8)'}
            }

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
                    **layout_config,
                    xaxis_tickangle=-45,
                    height=500,
                    bargap=0.2
                )
            elif tipo == 'pie':
                fig = px.pie(
                    stock_df,
                    values='Stock',
                    names='Almacén',
                    title=titulo,
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig.update_traces(
                    textposition='inside',
                    textinfo='percent+label',
                    hole=0.4,
                    marker=dict(line=dict(color='white', width=2))
                )
                fig.update_layout(**layout_config)
            
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
                fig.update_layout(**layout_config)
            
            # Añadir marca de agua
            fig.add_annotation(
                text="COHESA Inventory",
                xref="paper",
                yref="paper",
                x=0.5,
                y=-0.2,
                showarrow=False,
                font=dict(size=10, color="lightgrey"),
                opacity=0.5
            )

            return fig

        except Exception as e:
            st.error(f"❌ Error al generar gráfico: {str(e)}")
            return None

    def mostrar_metricas(self, metricas, columnas=4):
        """Muestra métricas en un formato visual mejorado"""
        cols = st.columns(columnas)
        
        for i, (titulo, valor) in enumerate(metricas.items()):
            with cols[i % columnas]:
                st.markdown(f"""
                    <div class="metric-card">
                        <h4 style="color: {self.COLOR_SCHEME['text']}; margin-bottom: 8px;">
                            {titulo}
                        </h4>
                        <p style="font-size: 24px; font-weight: bold; color: {self.COLOR_SCHEME['primary']}; margin: 0;">
                            {valor:,.2f}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
    def calcular_metricas_generales(self, stock_df):
    """Calcula métricas generales del inventario"""
    try:
        if stock_df.empty:
            return {
                'Total Productos': 0,
                'Total Almacenes': 0,
                'Total Lotes': 0,
                'Total Cajas en Stock': 0,
                'Total Kg en Stock': 0,
                'Total Ventas ($)': 0,
                'Productos en Estado Crítico': 0,
                'Rotación Promedio (%)': 0
            }

        return {
            'Total Productos': len(stock_df['Producto'].unique()),
            'Total Almacenes': len(stock_df['Almacén'].unique()),
            'Total Lotes': len(stock_df['Lote'].unique()),
            'Total Cajas en Stock': stock_df['Stock'].sum(),
            'Total Kg en Stock': stock_df['Kg Total'].sum(),
            'Total Ventas ($)': stock_df['Ventas Total'].sum(),
            'Productos en Estado Crítico': len(stock_df[stock_df['Estado Stock'] == 'CRÍTICO']),
            'Rotación Promedio (%)': stock_df['Rotación'].mean()
        }
            
    except Exception as e:
        st.error(f"❌ Error en el cálculo de métricas generales: {str(e)}")
        return {
            'Total Productos': 0,
            'Total Almacenes': 0,
            'Total Lotes': 0,
            'Total Cajas en Stock': 0,
            'Total Kg en Stock': 0,
            'Total Ventas ($)': 0,
            'Productos en Estado Crítico': 0,
            'Rotación Promedio (%)': 0
        }

    def stock_view(self):
        """Vista principal del stock con diseño mejorado"""
        st.markdown("""
            <h2 style='color: {}; margin-bottom: 20px;'>
                📊 Vista General de Stock
            </h2>
        """.format(self.COLOR_SCHEME['text']), unsafe_allow_html=True)
        
        # Obtener datos de stock
        stock_df = self.calcular_stock_actual()
        if stock_df.empty:
            st.warning("⚠️ No hay datos disponibles para mostrar")
            return

        # Contenedor para filtros
        with st.container():
            st.markdown("### 🔍 Filtros")
            col1, col2, col3 = st.columns(3)
            with col1:
                lote_filter = st.multiselect(
                    "Filtrar por Lote",
                    options=sorted(stock_df['Lote'].unique()),
                    key="stock_lote_filter"
                )
            with col2:
                almacen_filter = st.multiselect(
                    "Filtrar por Almacén",
                    options=sorted(stock_df['Almacén'].unique()),
                    key="stock_almacen_filter"
                )
            with col3:
                estado_filter = st.multiselect(
                    "Filtrar por Estado",
                    options=sorted(stock_df['Estado Stock'].unique()),
                    key="stock_estado_filter"
                )

        # Aplicar filtros
        df_filtered = stock_df.copy()
        if lote_filter:
            df_filtered = df_filtered[df_filtered['Lote'].isin(lote_filter)]
        if almacen_filter:
            df_filtered = df_filtered[df_filtered['Almacén'].isin(almacen_filter)]
        if estado_filter:
            df_filtered = df_filtered[df_filtered['Estado Stock'].isin(estado_filter)]

        # Métricas principales
        st.markdown("### 📈 Métricas Principales")
        metricas = self.calcular_metricas_generales(df_filtered)
        self.mostrar_metricas(metricas)

        # Visualizaciones
        st.markdown("### 📊 Análisis Visual")
        col1, col2 = st.columns(2)
        
        with col1:
            fig_stock = self.generar_grafico_stock(
                df_filtered,
                tipo='barras',
                titulo='Stock por Producto y Estado',
            )
            if fig_stock:
                st.plotly_chart(fig_stock, use_container_width=True, key='stock_bar_main')

        with col2:
            fig_dist = self.generar_grafico_stock(
                df_filtered,
                tipo='treemap',
                titulo='Distribución de Stock',
            )
            if fig_dist:
                st.plotly_chart(fig_dist, use_container_width=True, key='stock_tree_main')

        # Tabla detallada
        st.markdown("### 📋 Detalle de Stock")
        st.dataframe(
            df_filtered[[
                'Almacén', 'Producto', 'Lote', 'Stock', 'Kg Total',
                'Estado Stock', '% Disponible', 'Rotación'
            ]].sort_values(['Almacén', 'Producto']),
            use_container_width=True,
            height=400
        )
    def ventas_view(self):
        """Vista detallada de ventas con diseño mejorado"""
        st.markdown("""
            <h2 style='color: {}; margin-bottom: 20px;'>
                💰 Análisis de Ventas
            </h2>
        """.format(self.COLOR_SCHEME['text']), unsafe_allow_html=True)
        
        # Filtrar ventas
        ventas = self.df[self.df['movimiento'] == 'SALIDA'].copy()
        ventas = ventas[ventas['precio'] > 0]

        if ventas.empty:
            st.warning("⚠️ No hay datos de ventas disponibles")
            return

        # Crear tabs con diseño mejorado
        tabs = st.tabs(["📊 Resumen de Ventas", "👥 Análisis por Cliente", "📋 Detalle de Ventas"])
        
        with tabs[0]:
            # Métricas principales
            total_ventas = ventas['precio total'].sum()
            total_kg = ventas['kg'].sum()
            total_cajas = ventas['cajas'].sum()
            precio_promedio = total_ventas / total_kg if total_kg > 0 else 0
            
            metricas = {
                "Total Ventas": total_ventas,
                "Total Kg Vendidos": total_kg,
                "Total Cajas Vendidas": total_cajas,
                "Precio Promedio/Kg": precio_promedio
            }
            self.mostrar_metricas(metricas)

            # Análisis por producto
            st.markdown("### 📈 Top Ventas por Producto")
            col1, col2 = st.columns([3, 2])
            
            with col1:
                ventas_producto = ventas.groupby(['nombre', 'lote']).agg({
                    'cajas': 'sum',
                    'kg': 'sum',
                    'precio total': 'sum'
                }).round(2)
                ventas_producto = ventas_producto.sort_values('precio total', ascending=False)
                
                # Calcular métricas adicionales
                ventas_producto['% del Total'] = (ventas_producto['precio total'] / total_ventas * 100).round(2)
                ventas_producto['Precio/Kg'] = (ventas_producto['precio total'] / ventas_producto['kg']).round(2)
                
                st.dataframe(
                    ventas_producto,
                    use_container_width=True,
                    height=400
                )

            with col2:
                fig = px.pie(
                    ventas_producto.reset_index(),
                    values='precio total',
                    names='nombre',
                    title="Distribución de Ventas por Producto",
                    hole=0.4
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True, key='ventas_pie_main')

        with tabs[1]:
            st.markdown("### 👥 Análisis por Cliente")
            
            # Resumen por cliente
            ventas_cliente = ventas.groupby('cliente').agg({
                'cajas': 'sum',
                'kg': 'sum',
                'precio total': 'sum'
            }).round(2)
            
            ventas_cliente['% del Total'] = (ventas_cliente['precio total'] / total_ventas * 100).round(2)
            ventas_cliente['Precio/Kg'] = (ventas_cliente['precio total'] / ventas_cliente['kg']).round(2)
            ventas_cliente = ventas_cliente.sort_values('precio total', ascending=False)
            
            st.dataframe(ventas_cliente, use_container_width=True)
            
            # Análisis detallado por cliente
            st.markdown("### 🔍 Detalle por Cliente")
            cliente_seleccionado = st.selectbox(
                "Seleccionar Cliente",
                options=sorted(ventas['cliente'].unique()),
                key="ventas_cliente_selector"
            )
            
            if cliente_seleccionado:
                ventas_detalle = ventas[ventas['cliente'] == cliente_seleccionado]
                
                # Métricas del cliente
                total_cliente = ventas_detalle['precio total'].sum()
                total_kg_cliente = ventas_detalle['kg'].sum()
                
                metricas_cliente = {
                    "Total Compras": total_cliente,
                    "Total Kg": total_kg_cliente,
                    "% del Total": (total_cliente / total_ventas * 100),
                    "Precio Promedio/Kg": total_cliente / total_kg_cliente if total_kg_cliente > 0 else 0
                }
                self.mostrar_metricas(metricas_cliente)
                
                # Gráficos de análisis
                col1, col2 = st.columns(2)
                with col1:
                    fig_dist = px.pie(
                        ventas_detalle,
                        values='precio total',
                        names='nombre',
                        title=f"Distribución de Compras - {cliente_seleccionado}",
                        hole=0.4
                    )
                    st.plotly_chart(fig_dist, use_container_width=True, key='cliente_pie')
                
                with col2:
                    fig_cant = px.bar(
                        ventas_detalle,
                        x='nombre',
                        y=['cajas', 'kg'],
                        title=f"Cantidades por Producto - {cliente_seleccionado}",
                        barmode='group'
                    )
                    fig_cant.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_cant, use_container_width=True, key='cliente_bar')

        with tabs[2]:
            st.markdown("### 📋 Detalle de Ventas")
            
            # Filtros mejorados
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
            
            # Mostrar tabla detallada
            st.dataframe(
                ventas_filtradas[[
                    'nombre', 'lote', 'cliente', 'vendedor', 'cajas', 'kg', 
                    'precio', 'precio total'
                ]].sort_values(['cliente', 'nombre']),
                use_container_width=True,
                height=400
            )
    def vista_comercial(self):
        """Vista comercial con análisis detallado y diseño mejorado"""
        st.markdown("""
            <h2 style='color: {}; margin-bottom: 20px;'>
                🎯 Vista Comercial - Análisis de Stock y Ventas
            </h2>
        """.format(self.COLOR_SCHEME['text']), unsafe_allow_html=True)
        
        # Obtener datos
        stock_df = self.calcular_stock_actual()
        if stock_df.empty:
            st.warning("⚠️ No hay datos disponibles para mostrar")
            return

        # Filtros superiores con diseño mejorado
        with st.container():
            st.markdown("### 🔍 Filtros de Análisis")
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

        # Tabs con análisis específicos
        tab1, tab2, tab3 = st.tabs([
            "📊 Resumen General",
            "🔍 Análisis por Producto",
            "📍 Análisis por Almacén"
        ])

        with tab1:
            # Métricas principales
            metricas = self.calcular_metricas_generales(df_filtered)
            self.mostrar_metricas(metricas)

            # Gráficos de resumen
            col1, col2 = st.columns(2)
            with col1:
                fig_stock = self.generar_grafico_stock(
                    df_filtered,
                    tipo='barras',
                    titulo='Stock por Producto y Estado'
                )
                if fig_stock:
                    st.plotly_chart(fig_stock, use_container_width=True, key='comercial_stock_bar')

            with col2:
                fig_dist = self.generar_grafico_stock(
                    df_filtered,
                    tipo='treemap',
                    titulo='Distribución de Stock por Almacén y Producto'
                )
                if fig_dist:
                    st.plotly_chart(fig_dist, use_container_width=True, key='comercial_stock_tree')

        with tab2:
            st.markdown("### 🔍 Análisis Detallado por Producto")
            
            producto_seleccionado = st.selectbox(
                "Seleccionar Producto para Análisis",
                options=sorted(df_filtered['Producto'].unique()),
                key="comercial_producto_selector"
            )
            
            if producto_seleccionado:
                df_producto = df_filtered[df_filtered['Producto'] == producto_seleccionado]
                
                # Métricas del producto
                metricas_producto = {
                    "Stock Total": df_producto['Stock'].sum(),
                    "Kg Totales": df_producto['Kg Total'].sum(),
                    "Ventas Totales ($)": df_producto['Ventas Total'].sum(),
                    "Rotación (%)": df_producto['Rotación'].mean()
                }
                self.mostrar_metricas(metricas_producto)
                
                # Detalle por almacén y lote
                st.markdown("#### 📋 Detalle por Almacén y Lote")
                detalle_cols = ['Almacén', 'Lote', 'Stock', 'Kg Total', 'Total Inicial', 
                              'Salidas', '% Vendido', '% Disponible', 'Estado Stock']
                st.dataframe(
                    df_producto[detalle_cols].sort_values(['Almacén', 'Lote']),
                    use_container_width=True
                )
                
                # Gráficos de análisis
                col1, col2 = st.columns(2)
                with col1:
                    fig_dist_almacen = px.pie(
                        df_producto,
                        values='Stock',
                        names='Almacén',
                        title=f"Distribución por Almacén - {producto_seleccionado}",
                        hole=0.4
                    )
                    st.plotly_chart(fig_dist_almacen, use_container_width=True, key='comercial_prod_pie')
                
                with col2:
                    fig_evolucion = px.bar(
                        df_producto,
                        x='Lote',
                        y=['Stock', 'Salidas'],
                        title=f"Stock vs Salidas - {producto_seleccionado}",
                        barmode='group'
                    )
                    st.plotly_chart(fig_evolucion, use_container_width=True, key='comercial_prod_bar')

        with tab3:
            st.markdown("### 📍 Análisis Detallado por Almacén")
            
            almacen_seleccionado = st.selectbox(
                "Seleccionar Almacén para Análisis",
                options=sorted(df_filtered['Almacén'].unique()),
                key="comercial_almacen_selector"
            )
            
            if almacen_seleccionado:
                df_almacen = df_filtered[df_filtered['Almacén'] == almacen_seleccionado]
                
                # Métricas del almacén
                metricas_almacen = {
                    "Total Productos": len(df_almacen['Producto'].unique()),
                    "Stock Total": df_almacen['Stock'].sum(),
                    "Productos Críticos": len(df_almacen[df_almacen['Estado Stock'] == 'CRÍTICO'])
                }
                self.mostrar_metricas(metricas_almacen, 3)
                
                # Análisis de stock
                st.markdown("#### 📊 Estado de Stock por Producto")
                
                resumen_stock = df_almacen.groupby('Producto').agg({
                    'Stock': 'sum',
                    'Kg Total': 'sum',
                    'Total Inicial': 'sum',
                    'Salidas': 'sum',
                    '% Vendido': 'mean',
                    '% Disponible': 'mean'
                }).round(2)
                
                resumen_stock['Estado'] = resumen_stock['Stock'].apply(
                    lambda x: next(
                        (estado for estado, config in self.ESTADOS_STOCK.items() 
                         if x <= config['umbral']),
                        'NORMAL'
                    )
                )
                
                st.dataframe(
                    resumen_stock.sort_values('Stock', ascending=False),
                    use_container_width=True
                )
                
                # Gráficos de análisis
                col1, col2 = st.columns(2)
                with col1:
                    fig_stock = px.bar(
                        df_almacen,
                        x='Producto',
                        y='Stock',
                        color='Estado Stock',
                        title=f"Stock por Producto - {almacen_seleccionado}"
                    )
                    fig_stock.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_stock, use_container_width=True, key='comercial_alm_bar')
                
                with col2:
                    fig_estados = px.pie(
                        df_almacen,
                        names='Estado Stock',
                        values='Stock',
                        title=f"Distribución por Estado - {almacen_seleccionado}",
                        hole=0.4
                    )
                    st.plotly_chart(fig_estados, use_container_width=True, key='comercial_alm_pie')

    def run_dashboard(self):
        """Función principal del dashboard con diseño mejorado"""
        # Título principal con estilo mejorado
        st.markdown("""
            <h1 style='text-align: center; color: {}; padding: 1rem 0;'>
                📦 Dashboard de Inventario COHESA
            </h1>
        """.format(self.COLOR_SCHEME['primary']), unsafe_allow_html=True)

        # Sidebar con información y controles
        with st.sidebar:
            st.markdown("### ⚙️ Control del Dashboard")
            st.write("🕒 Última actualización:", datetime.now().strftime("%H:%M:%S"))
            
            if st.button('🔄 Actualizar Datos', key="refresh_button"):
                st.cache_data.clear()
                st.rerun()

        # Cargar datos
        if not self.load_data():
            st.error("❌ Error al cargar los datos")
            return

        # Tabs principales
        tab1, tab2, tab3 = st.tabs(["📊 Stock", "💰 Ventas", "🎯 Vista Comercial"])
        
        with tab1:
            self.stock_view()
        
        with tab2:
            self.ventas_view()
        
        with tab3:
            self.vista_comercial()

if __name__ == '__main__':
    dashboard = InventarioDashboard()
    dashboard.run_dashboard()
