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
from plotly.subplots import make_subplots

from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from datetime import datetime
import numpy as np

# --------------------------------------------------------------------------------
#                                Estilos CSS
# --------------------------------------------------------------------------------
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

# --------------------------------------------------------------------------------
#                     Clase de utilidades y formateos numéricos
# --------------------------------------------------------------------------------
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
        """Formatea números para visualización (K, M, etc.)"""
        try:
            if abs(numero) >= 1_000_000:
                return f"{numero/1_000_000:.{decimales}f}M"
            elif abs(numero) >= 1_000:
                return f"{numero/1_000:.{decimales}f}K"
            else:
                return f"{numero:.{decimales}f}"
        except:
            return "0"

# --------------------------------------------------------------------------------
#                          Clase principal del Dashboard
# --------------------------------------------------------------------------------
class InventarioDashboard:
    def __init__(self):
        # Ajusta estos valores a tu hoja de Google
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        self.SPREADSHEET_ID = '1acGspGuv-i0KSA5Q8owZpFJb1ytgm1xljBLZoa2cSN8'
        self.RANGE_NAME = 'Carnes!A1:L'
        
        self.df = None
        self.analytics = InventarioAnalytics()
        
        # Paleta de colores y configuración
        self.COLOR_SCHEME = {
            'primary': '#1f77b4',
            'secondary': '#ff7f0e',
            'success': '#2ecc71',
            'warning': '#e74c3c',
            'info': '#3498db',
            'background': '#f8f9fa',
            'text': '#2c3e50'
        }
        
        # Umbrales para estados de stock
        self.ESTADOS_STOCK = {
            'CRÍTICO': {'umbral': 5, 'color': '#e74c3c'},
            'BAJO': {'umbral': 20, 'color': '#f39c12'},
            'NORMAL': {'umbral': float('inf'), 'color': '#2ecc71'}
        }

    # ----------------------------------------------------------------------------
    #                  Manejo de credenciales y carga de datos
    # ----------------------------------------------------------------------------
    def get_credentials(self):
        """Obtiene credenciales para Google Sheets API"""
        try:
            # Opción 1: usar credenciales alojadas en Streamlit Cloud (Secrets)
            if st.secrets.get("gcp_service_account"):
                credentials_dict = st.secrets["gcp_service_account"]
                creds = service_account.Credentials.from_service_account_info(
                    credentials_dict,
                    scopes=self.SCOPES
                )
                return creds
            else:
                # Opción 2: usar archivo local 'client_secret.json'
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

    @st.cache_data
    def load_data(self):
        """Carga y preprocesa los datos desde Google Sheets"""
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
                
                # Crear DataFrame desde la hoja de cálculo
                self.df = pd.DataFrame(values[1:], columns=values[0])
                
                # Validar que existan las columnas requeridas
                required_columns = [
                    'nombre', 'lote', 'movimiento', 'almacen', 
                    'almacen actual', 'cajas', 'kg', 'precio', 'precio total'
                ]
                missing_columns = [col for col in required_columns if col not in self.df.columns]
                if missing_columns:
                    st.error(f"❌ Faltan columnas requeridas: {', '.join(missing_columns)}")
                    return False
                
                # Convertir columnas numéricas adecuadamente
                numeric_columns = ['cajas', 'kg', 'precio', 'precio total']
                for col in numeric_columns:
                    self.df[col] = pd.to_numeric(
                        self.df[col].replace(['', 'E', '#VALUE!', '#N/A'], '0'),
                        errors='coerce'
                    ).fillna(0)
                
                # Limpiar algunas columnas de texto
                self.df['movimiento'] = self.df['movimiento'].str.upper().fillna('')
                self.df['almacen'] = self.df['almacen'].str.strip().fillna('')
                self.df['almacen actual'] = self.df['almacen actual'].str.strip().fillna('')
                
                st.success("✅ Datos cargados exitosamente")
                return True
                
        except Exception as e:
            st.error(f"❌ Error durante la carga de datos: {str(e)}")
            return False

    # ----------------------------------------------------------------------------
    #                      Cálculos de stock y métricas
    # ----------------------------------------------------------------------------
    def calcular_metricas_generales(self, stock_df):
        """Calcula métricas generales del inventario a partir del DF de stock"""
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

    def calcular_stock_actual(self):
        """
        Calcula el stock actual a nivel de Producto, Lote y Almacén.
        Devuelve un DataFrame con columnas como:
        [Almacén, Producto, Lote, Stock, Kg Total, Entradas, Salidas, % Vendido, ...]
        """
        try:
            with st.spinner('Calculando stock actual...'):
                stock_data = []

                # Listas únicas de productos, lotes y almacenes
                todos_productos = self.df['nombre'].unique()
                todos_lotes = self.df['lote'].unique()
                todos_almacenes = pd.concat([
                    self.df['almacen'], 
                    self.df['almacen actual']
                ]).unique()
                todos_almacenes = [a for a in todos_almacenes if pd.notna(a) and str(a).strip() != '']

                # Barra de progreso
                total_items = len(todos_productos) * len(todos_lotes) * len(todos_almacenes)
                progress_bar = st.progress(0)
                current_item = 0

                for producto in todos_productos:
                    for lote in todos_lotes:
                        for almacen in todos_almacenes:
                            current_item += 1
                            progress_bar.progress(current_item / total_items)

                            # Filtrar data para (producto, lote)
                            df_filtrado = self.df[
                                (self.df['nombre'] == producto) & 
                                (self.df['lote'] == lote)
                            ]
                            
                            # Entradas: movimiento = ENTRADA en 'almacen'
                            entradas_df = df_filtrado[
                                (df_filtrado['movimiento'] == 'ENTRADA') & 
                                (df_filtrado['almacen'] == almacen)
                            ]
                            entradas = entradas_df['cajas'].sum()
                            kg_entradas = entradas_df['kg'].sum()

                            # Traspasos recibidos: movimiento = TRASPASO y 'almacen actual' == almacen
                            traspasos_recibidos_df = df_filtrado[
                                (df_filtrado['movimiento'] == 'TRASPASO') & 
                                (df_filtrado['almacen actual'] == almacen)
                            ]
                            traspasos_recibidos = traspasos_recibidos_df['cajas'].sum()
                            kg_traspasos_recibidos = traspasos_recibidos_df['kg'].sum()
                            
                            # Traspasos enviados: movimiento = TRASPASO y 'almacen' == almacen
                            traspasos_enviados_df = df_filtrado[
                                (df_filtrado['movimiento'] == 'TRASPASO') & 
                                (df_filtrado['almacen'] == almacen)
                            ]
                            traspasos_enviados = traspasos_enviados_df['cajas'].sum()
                            kg_traspasos_enviados = traspasos_enviados_df['kg'].sum()
                            
                            # Salidas: movimiento = SALIDA y 'almacen' == almacen
                            salidas_df = df_filtrado[
                                (df_filtrado['movimiento'] == 'SALIDA') & 
                                (df_filtrado['almacen'] == almacen)
                            ]
                            salidas = salidas_df['cajas'].sum()
                            kg_salidas = salidas_df['kg'].sum()
                            ventas_total = salidas_df['precio total'].sum()
                            
                            # Cálculo de totales
                            total_inicial = entradas + traspasos_recibidos
                            stock = total_inicial - traspasos_enviados - salidas
                            kg_total = kg_entradas + kg_traspasos_recibidos - kg_traspasos_enviados - kg_salidas
                            
                            # % vendido y % disponible
                            porcentaje_vendido = self.analytics.calcular_porcentaje(salidas, total_inicial)
                            porcentaje_disponible = self.analytics.calcular_porcentaje(stock, total_inicial)
                            
                            # Rotación (se puede asimilar a % vendido)
                            rotacion = porcentaje_vendido
                            
                            # Determinar estado de stock según umbrales
                            estado_stock = 'NORMAL'
                            for estado, config in self.ESTADOS_STOCK.items():
                                if stock <= config['umbral']:
                                    estado_stock = estado
                                    break
                            
                            # Almacenar solo si hubo movimiento
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
                                    'Días Inventario': 0,  # Puedes calcular días de inventario si deseas
                                    'Kg Entradas': kg_entradas,
                                    'Kg Traspasos Recibidos': kg_traspasos_recibidos,
                                    'Kg Traspasos Enviados': kg_traspasos_enviados,
                                    'Kg Salidas': kg_salidas
                                })

                progress_bar.empty()
                
                # DataFrame final
                stock_df = pd.DataFrame(stock_data)
                if stock_df.empty:
                    st.warning("📊 No se encontraron datos de stock para mostrar")
                    return pd.DataFrame()

                # Ordenar y redondear
                stock_df = stock_df.sort_values(['Almacén', 'Producto', 'Lote'])
                stock_df = stock_df.round(2)
                
                return stock_df
                
        except Exception as e:
            st.error(f"❌ Error en el cálculo de stock: {str(e)}")
            return pd.DataFrame()

    # ----------------------------------------------------------------------------
    #                        Helper: Mostrar métricas en columnas
    # ----------------------------------------------------------------------------
    def mostrar_metricas(self, metricas, columnas=4):
        """Muestra métricas en formato de tarjetas (cards)"""
        cols = st.columns(columnas)
        
        # Iteramos cada métrica y la mostramos
        for i, (titulo, valor) in enumerate(metricas.items()):
            with cols[i % columnas]:
                # Formatear valor si es numérico
                if isinstance(valor, (int, float)):
                    valor_str = f"{valor:,.2f}"
                else:
                    valor_str = str(valor)
                
                st.markdown(f"""
                    <div class="metric-card">
                        <h4 style="color: {self.COLOR_SCHEME['text']}; margin-bottom: 8px;">
                            {titulo}
                        </h4>
                        <p style="font-size: 24px; font-weight: bold; color: {self.COLOR_SCHEME['primary']}; margin: 0;">
                            {valor_str}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

    # ----------------------------------------------------------------------------
    #            Helper: Gráficos genéricos (barras, pie, treemap)
    # ----------------------------------------------------------------------------
    def generar_grafico_stock(self, stock_df, tipo='barras', titulo='', filtro=None):
        """Genera gráficos para el análisis de stock (barras, pie, treemap)"""
        try:
            if stock_df.empty:
                return None

            # Aplicar un filtro extra si se desea
            if filtro:
                stock_df = stock_df[filtro]

            # Config común de estilo
            layout_config = {
                'paper_bgcolor': 'rgba(0,0,0,0)',
                'plot_bgcolor': 'rgba(0,0,0,0)',
                'font': {'color': self.COLOR_SCHEME['text']},
                'title': {
                    'text': titulo,
                    'font': {'size': 20, 'color': self.COLOR_SCHEME['text']},
                    'x': 0.5,
                    'xanchor': 'center'
                },
                'showlegend': True,
                'legend': {'bgcolor': 'rgba(255,255,255,0.8)'}
            }

            # Renderizar en función del tipo de gráfico
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
                    }
                )
                fig.update_layout(**layout_config, xaxis_tickangle=-45, height=500, bargap=0.2)
            
            elif tipo == 'pie':
                fig = px.pie(
                    stock_df,
                    values='Stock',
                    names='Almacén'
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
                    }
                )
                fig.update_layout(**layout_config)
            
            return fig

        except Exception as e:
            st.error(f"❌ Error al generar gráfico: {str(e)}")
            return None

    # ----------------------------------------------------------------------------
    #   NUEVO: Gráfico que muestra Entradas vs. Salidas y % Vendido por producto
    # ----------------------------------------------------------------------------
    def generar_grafico_entradas_vs_salidas(self, stock_df):
        """
        Genera un gráfico que compara Entradas y Salidas por Producto, 
        además de un % de Ventas (Salidas/Entradas).
        """
        try:
            if stock_df.empty:
                st.warning("No hay datos para Entradas vs. Salidas")
                return

            # Agrupar por producto
            df_group = stock_df.groupby('Producto').agg({
                'Entradas': 'sum',
                'Salidas': 'sum',
                'Total Inicial': 'sum'
            }).reset_index()
            
            # Calcular porcentaje vendido
            df_group['% Vendido'] = df_group.apply(
                lambda row: self.analytics.calcular_porcentaje(row['Salidas'], row['Total Inicial']),
                axis=1
            )

            # Crear subgráfico con 2 ejes Y (barras y línea)
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Barras: Entradas
            fig.add_trace(
                go.Bar(
                    x=df_group['Producto'],
                    y=df_group['Entradas'],
                    name='Entradas',
                    marker_color=self.COLOR_SCHEME['success']
                ),
                secondary_y=False
            )
            
            # Barras: Salidas
            fig.add_trace(
                go.Bar(
                    x=df_group['Producto'],
                    y=df_group['Salidas'],
                    name='Salidas',
                    marker_color=self.COLOR_SCHEME['warning']
                ),
                secondary_y=False
            )
            
            # Línea: % Vendido
            fig.add_trace(
                go.Scatter(
                    x=df_group['Producto'],
                    y=df_group['% Vendido'],
                    name='% Vendido',
                    mode='lines+markers',
                    marker_color=self.COLOR_SCHEME['primary'],
                    yaxis='y2'
                ),
                secondary_y=True
            )

            # Layout
            fig.update_layout(
                title_text="Entradas vs. Salidas y % Vendido",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(title="Producto", tickangle=-45),
                yaxis=dict(title="Cajas"),
                yaxis2=dict(title="% Vendido", overlaying='y', side='right'),
                hovermode="x unified",
                plot_bgcolor='white'
            )
            
            st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"❌ Error generando gráfico Entradas vs Salidas: {e}")

    # ----------------------------------------------------------------------------
    #                            Vistas del dashboard
    # ----------------------------------------------------------------------------
    def stock_view(self):
        """Vista principal del stock con diseño mejorado"""
        st.markdown(f"<h2 style='color: {self.COLOR_SCHEME['text']}; margin-bottom: 20px;'>📊 Vista General de Stock</h2>", 
                    unsafe_allow_html=True)
        
        # Obtener datos de stock
        stock_df = self.calcular_stock_actual()
        if stock_df.empty:
            st.warning("⚠️ No hay datos disponibles para mostrar")
            return

        # Contenedor de filtros
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

        # Aplicar filtros al DF
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
                titulo='Stock por Producto y Estado'
            )
            if fig_stock:
                st.plotly_chart(fig_stock, use_container_width=True, key='stock_bar_main')

        with col2:
            fig_dist = self.generar_grafico_stock(
                df_filtered,
                tipo='treemap',
                titulo='Distribución de Stock'
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

        # NUEVO GRÁFICO: Entradas vs Salidas y % vendido (sólo para DF filtrado)
        st.markdown("### 📊 Entradas vs. Salidas y % Vendido (por Producto)")
        self.generar_grafico_entradas_vs_salidas(df_filtered)

    def ventas_view(self):
        """Vista detallada de ventas con diseño mejorado"""
        st.markdown(f"<h2 style='color: {self.COLOR_SCHEME['text']}; margin-bottom: 20px;'>💰 Análisis de Ventas</h2>", 
                    unsafe_allow_html=True)
        
        # Filtrar únicamente filas de SALIDA
        ventas = self.df[self.df['movimiento'] == 'SALIDA'].copy()
        ventas = ventas[ventas['precio'] > 0]

        if ventas.empty:
            st.warning("⚠️ No hay datos de ventas disponibles")
            return

        # Crear tabs
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
            total_ventas = ventas['precio total'].sum()  # recalcular si se ha modificado
            ventas_cliente = ventas.groupby('cliente').agg({
                'cajas': 'sum',
                'kg': 'sum',
                'precio total': 'sum'
            }).round(2)
            
            ventas_cliente['% del Total'] = (ventas_cliente['precio total'] / total_ventas * 100).round(2)
            ventas_cliente['Precio/Kg'] = (ventas_cliente['precio total'] / ventas_cliente['kg']).round(2)
            ventas_cliente = ventas_cliente.sort_values('precio total', ascending=False)
            
            st.dataframe(ventas_cliente, use_container_width=True)

            # Detalle por cliente
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
                    "% del Total": (total_cliente / total_ventas * 100) if total_ventas > 0 else 0,
                    "Precio Promedio/Kg": total_cliente / total_kg_cliente if total_kg_cliente > 0 else 0
                }
                self.mostrar_metricas(metricas_cliente)
                
                # Gráficos
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
            
            # Mostrar tabla
            st.dataframe(
                ventas_filtradas[[
                    'nombre', 'lote', 'cliente', 'vendedor', 'cajas', 'kg', 
                    'precio', 'precio total'
                ]].sort_values(['cliente', 'nombre']),
                use_container_width=True,
                height=400
            )

    def vista_comercial(self):
        """Vista comercial con análisis cruzado de Stock y Ventas"""
        st.markdown(f"<h2 style='color: {self.COLOR_SCHEME['text']}; margin-bottom: 20px;'>🎯 Vista Comercial - Análisis de Stock y Ventas</h2>", 
                    unsafe_allow_html=True)
        
        # Obtener stock
        stock_df = self.calcular_stock_actual()
        if stock_df.empty:
            st.warning("⚠️ No hay datos disponibles para mostrar")
            return

        # Filtros
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

        # Tabs
        tab1, tab2, tab3 = st.tabs(["📊 Resumen General", "🔍 Análisis por Producto", "📍 Análisis por Almacén"])

        with tab1:
            # Métricas
            metricas = self.calcular_metricas_generales(df_filtered)
            self.mostrar_metricas(metricas)

            # Gráficos
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
                    titulo='Distribución de Stock'
                )
                if fig_dist:
                    st.plotly_chart(fig_dist, use_container_width=True, key='comercial_stock_tree')

            # NUEVO: Entradas vs Salidas y % Vendido
            st.markdown("#### 📊 Entradas vs. Salidas y % Vendido (por Producto)")
            self.generar_grafico_entradas_vs_salidas(df_filtered)

        with tab2:
            st.markdown("### 🔍 Análisis Detallado por Producto")
            
            producto_seleccionado = st.selectbox(
                "Seleccionar Producto",
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
                detalle_cols = [
                    'Almacén', 'Lote', 'Stock', 'Kg Total', 'Total Inicial', 
                    'Salidas', '% Vendido', '% Disponible', 'Estado Stock'
                ]
                st.dataframe(
                    df_producto[detalle_cols].sort_values(['Almacén', 'Lote']),
                    use_container_width=True
                )
                
                # Gráficos
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
                "Seleccionar Almacén",
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
                
                # Resumen
                st.markdown("#### 📊 Estado de Stock por Producto")
                resumen_stock = df_almacen.groupby('Producto').agg({
                    'Stock': 'sum',
                    'Kg Total': 'sum',
                    'Total Inicial': 'sum',
                    'Salidas': 'sum',
                    '% Vendido': 'mean',
                    '% Disponible': 'mean'
                }).round(2)

                # Determinar estado
                def obtener_estado(stock_val):
                    for est, config in self.ESTADOS_STOCK.items():
                        if stock_val <= config['umbral']:
                            return est
                    return 'NORMAL'
                
                resumen_stock['Estado'] = resumen_stock['Stock'].apply(obtener_estado)
                
                st.dataframe(
                    resumen_stock.sort_values('Stock', ascending=False),
                    use_container_width=True
                )
                
                # Gráficos
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

    # ----------------------------------------------------------------------------
    #                     Función principal (run) del Dashboard
    # ----------------------------------------------------------------------------
    def run_dashboard(self):
        """Función principal del dashboard"""
        st.markdown(f"""
            <h1 style='text-align: center; color: {self.COLOR_SCHEME['primary']}; padding: 1rem 0;'>
                📦 Dashboard de Inventario COHESA
            </h1>
        """, unsafe_allow_html=True)

        # SIDEBAR
        with st.sidebar:
            st.markdown("### ⚙️ Control del Dashboard")
            st.write("🕒 Última actualización:", datetime.now().strftime("%H:%M:%S"))
            
            if st.button('🔄 Actualizar Datos', key="refresh_button"):
                # Limpia la caché y recarga
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

# ----------------------------------------------------------------------------
#                          Ejecución del Dashboard
# ----------------------------------------------------------------------------
if __name__ == '__main__':
    dashboard = InventarioDashboard()
    dashboard.run_dashboard()