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

# -----------------------------------------------------------------------------
#                               Estilos CSS
# -----------------------------------------------------------------------------
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


# -----------------------------------------------------------------------------
#       1) Función externa cacheada para cargar datos desde Google Sheets
# -----------------------------------------------------------------------------
@st.cache_data
def load_data_from_sheets(spreadsheet_id: str, range_name: str) -> pd.DataFrame:
    """
    Carga datos desde Google Sheets y retorna un DataFrame.
    Vive fuera de la clase para evitar UnhashableParamError.
    """
    # Revisar credenciales en st.secrets
    if "gcp_service_account" not in st.secrets:
        st.error("No se encontraron credenciales en st.secrets (gcp_service_account).")
        return pd.DataFrame()

    credentials_dict = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )

    # Construir servicio de Sheets
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    # Leer el rango especificado
    result = sheet.values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name
    ).execute()
    values = result.get('values', [])
    if not values:
        return pd.DataFrame()

    df = pd.DataFrame(values[1:], columns=values[0])
    return df


# -----------------------------------------------------------------------------
#        2) Clase de utilidades: cálculos de porcentajes, formateos, etc.
# -----------------------------------------------------------------------------
class InventarioAnalytics:
    @staticmethod
    def calcular_porcentaje(parte, total):
        """Calcula porcentaje con manejo de errores."""
        try:
            return round((parte / total * 100), 2) if total > 0 else 0
        except:
            return 0

    @staticmethod
    def formatear_numero(numero, decimales=2):
        """Formatea números (ej: 1000 => 1K, 1,000,000 => 1M)."""
        try:
            if abs(numero) >= 1_000_000:
                return f"{numero/1_000_000:.{decimales}f}M"
            elif abs(numero) >= 1_000:
                return f"{numero/1_000:.{decimales}f}K"
            else:
                return f"{numero:.{decimales}f}"
        except:
            return "0"


# -----------------------------------------------------------------------------
#        3) Clase principal del Dashboard con vistas: Stock, Ventas, Comercial
# -----------------------------------------------------------------------------
class InventarioDashboard:
    def __init__(self):
        # Ajusta tu Spreadsheet ID y Rango
        self.SPREADSHEET_ID = "1acGspGuv-i0KSA5Q8owZpFJb1ytgm1xljBLZoa2cSN8"
        self.RANGE_NAME = "Carnes!A1:L"   # Cambia si tienes otra hoja/rango

        self.df = pd.DataFrame()         # DataFrame principal
        self.analytics = InventarioAnalytics()

        # Paleta de colores
        self.COLOR_SCHEME = {
            'primary': '#1f77b4',
            'secondary': '#ff7f0e',
            'success': '#2ecc71',
            'warning': '#e74c3c',
            'info': '#3498db',
            'background': '#f8f9fa',
            'text': '#2c3e50'
        }

        # Configuración de umbrales
        self.ESTADOS_STOCK = {
            'CRÍTICO': {'umbral': 5, 'color': '#e74c3c'},
            'BAJO': {'umbral': 20, 'color': '#f39c12'},
            'NORMAL': {'umbral': float('inf'), 'color': '#2ecc71'}
        }

    # -------------------------------------------------------------------------
    # (A) Cargar datos invocando a la función cacheada
    # -------------------------------------------------------------------------
    def load_data(self) -> bool:
        """Carga datos desde Google Sheets y hace limpieza."""
        with st.spinner("Cargando datos..."):
            df_tmp = load_data_from_sheets(self.SPREADSHEET_ID, self.RANGE_NAME)
            if df_tmp.empty:
                st.error("📊 No se encontraron datos en la hoja de cálculo.")
                return False

            # Validar columnas requeridas
            required_columns = [
                'nombre', 'lote', 'movimiento', 'almacen',
                'almacen actual', 'cajas', 'kg', 'precio', 'precio total'
            ]
            missing_cols = [c for c in required_columns if c not in df_tmp.columns]
            if missing_cols:
                st.error(f"❌ Faltan columnas requeridas: {missing_cols}")
                return False

            # Convertir columnas numéricas
            numeric_cols = ['cajas', 'kg', 'precio', 'precio total']
            for col in numeric_cols:
                df_tmp[col] = pd.to_numeric(
                    df_tmp[col].replace(['', 'E', '#VALUE!', '#N/A'], '0'),
                    errors='coerce'
                ).fillna(0)

            # Limpiar strings
            df_tmp['movimiento'] = df_tmp['movimiento'].str.upper().fillna('')
            df_tmp['almacen'] = df_tmp['almacen'].str.strip().fillna('')
            df_tmp['almacen actual'] = df_tmp['almacen actual'].str.strip().fillna('')

            # Asignar a self.df
            self.df = df_tmp
            st.success("✅ Datos cargados exitosamente")
            return True

    # -------------------------------------------------------------------------
    # (B) Cálculo de stock actual
    # -------------------------------------------------------------------------
    def calcular_stock_actual(self) -> pd.DataFrame:
        """
        Retorna un DF con las columnas:
        [Almacén, Producto, Lote, Stock, Kg Total, Entradas, Salidas, etc.]
        """
        try:
            if self.df.empty:
                return pd.DataFrame()

            with st.spinner('Calculando stock actual...'):
                stock_data = []

                # Listas únicas
                productos = self.df['nombre'].unique()
                lotes = self.df['lote'].unique()
                almacenes = pd.concat([
                    self.df['almacen'], self.df['almacen actual']
                ]).unique()
                almacenes = [a for a in almacenes if pd.notna(a) and str(a).strip() != '']

                total_items = len(productos)*len(lotes)*len(almacenes)
                progress_bar = st.progress(0)
                current_item = 0

                for prod in productos:
                    for lote in lotes:
                        for alm in almacenes:
                            current_item += 1
                            progress_bar.progress(current_item / total_items)

                            df_fil = self.df[(self.df['nombre'] == prod) & (self.df['lote'] == lote)]

                            # Entradas
                            df_ent = df_fil[(df_fil['movimiento'] == 'ENTRADA') & (df_fil['almacen'] == alm)]
                            entradas = df_ent['cajas'].sum()
                            kg_entradas = df_ent['kg'].sum()

                            # Traspasos Recibidos
                            df_t_rec = df_fil[(df_fil['movimiento'] == 'TRASPASO') & (df_fil['almacen actual'] == alm)]
                            tr_rec = df_t_rec['cajas'].sum()
                            kg_t_rec = df_t_rec['kg'].sum()

                            # Traspasos Enviados
                            df_t_env = df_fil[(df_fil['movimiento'] == 'TRASPASO') & (df_fil['almacen'] == alm)]
                            tr_env = df_t_env['cajas'].sum()
                            kg_t_env = df_t_env['kg'].sum()

                            # Salidas
                            df_sal = df_fil[(df_fil['movimiento'] == 'SALIDA') & (df_fil['almacen'] == alm)]
                            salidas = df_sal['cajas'].sum()
                            kg_sal = df_sal['kg'].sum()
                            ventas_total = df_sal['precio total'].sum()

                            # Cálculos
                            total_inicial = entradas + tr_rec
                            stock = total_inicial - tr_env - salidas
                            kg_total = kg_entradas + kg_t_rec - kg_t_env - kg_sal

                            pct_vendido = self.analytics.calcular_porcentaje(salidas, total_inicial)
                            pct_disp = self.analytics.calcular_porcentaje(stock, total_inicial)
                            rotacion = pct_vendido

                            # Estado Stock
                            estado = 'NORMAL'
                            for est, config in self.ESTADOS_STOCK.items():
                                if stock <= config['umbral']:
                                    estado = est
                                    break

                            # Guardar si hubo movimiento
                            if total_inicial > 0 or stock != 0:
                                stock_data.append({
                                    'Almacén': alm,
                                    'Producto': prod,
                                    'Lote': lote,
                                    'Stock': stock,
                                    'Kg Total': kg_total,
                                    'Total Inicial': total_inicial,
                                    'Entradas': entradas,
                                    'Traspasos Recibidos': tr_rec,
                                    'Traspasos Enviados': tr_env,
                                    'Salidas': salidas,
                                    'Ventas Total': ventas_total,
                                    '% Vendido': pct_vendido,
                                    '% Disponible': pct_disp,
                                    'Estado Stock': estado,
                                    'Rotación': rotacion
                                })

                progress_bar.empty()

                stock_df = pd.DataFrame(stock_data).round(2)
                if stock_df.empty:
                    st.warning("📊 No se encontraron datos de stock para mostrar")
                return stock_df
        except Exception as e:
            st.error(f"❌ Error en el cálculo de stock: {str(e)}")
            return pd.DataFrame()

    # -------------------------------------------------------------------------
    # (C) Métricas Generales
    # -------------------------------------------------------------------------
    def calcular_metricas_generales(self, stock_df: pd.DataFrame) -> dict:
        """Calcula algunas métricas globales del DF de stock."""
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
        try:
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
            st.error(f"Error cálculo métricas generales: {e}")
            return {}

    def mostrar_metricas(self, metricas: dict, columnas=4):
        """Muestra un dict de métricas en tarjetas."""
        cols = st.columns(columnas)
        i = 0
        for titulo, valor in metricas.items():
            with cols[i % columnas]:
                if isinstance(valor, float):
                    valor_str = f"{valor:,.2f}"
                else:
                    valor_str = f"{valor}"
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
            i += 1

    # -------------------------------------------------------------------------
    # (D) Generación de gráficos
    # -------------------------------------------------------------------------
    def generar_grafico_stock(self, stock_df: pd.DataFrame, tipo='barras', titulo=''):
        """Genera un gráfico de stock (barras, pie, treemap)."""
        if stock_df.empty:
            return None

        layout_config = {
            'paper_bgcolor': 'rgba(0,0,0,0)',
            'plot_bgcolor': 'rgba(0,0,0,0)',
            'font': {'color': self.COLOR_SCHEME['text']},
            'title': {
                'text': titulo,
                'font': {'size': 20, 'color': self.COLOR_SCHEME['text']},
                'x': 0.5, 'xanchor': 'center'
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
                }
            )
            fig.update_layout(**layout_config, xaxis_tickangle=-45, height=500, bargap=0.2)

        elif tipo == 'pie':
            fig = px.pie(
                stock_df,
                values='Stock',
                names='Almacén'
            )
            fig.update_traces(textposition='inside', textinfo='percent+label', hole=0.4)
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

        else:
            fig = None

        return fig

    def generar_grafico_entradas_vs_salidas(self, stock_df: pd.DataFrame):
        """Genera sub-gráfico Entradas vs Salidas + % Vendido por producto."""
        if stock_df.empty:
            st.warning("No hay datos para Entradas vs. Salidas")
            return

        df_group = stock_df.groupby('Producto').agg({
            'Entradas': 'sum',
            'Salidas': 'sum',
            'Total Inicial': 'sum'
        }).reset_index()

        # % Vendido
        df_group['% Vendido'] = df_group.apply(
            lambda row: self.analytics.calcular_porcentaje(row['Salidas'], row['Total Inicial']),
            axis=1
        )

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
                marker_color=self.COLOR_SCHEME['primary']
            ),
            secondary_y=True
        )

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

    # -------------------------------------------------------------------------
    # (E) Vistas del Dashboard
    # -------------------------------------------------------------------------
    def stock_view(self):
        """Vista principal del stock."""
        st.markdown(f"<h2 style='color: {self.COLOR_SCHEME['text']}; margin-bottom: 20px;'>📊 Vista General de Stock</h2>", 
                    unsafe_allow_html=True)

        stock_df = self.calcular_stock_actual()
        if stock_df.empty:
            st.warning("⚠️ No hay datos disponibles para mostrar")
            return

        # Filtros
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

        df_filtered = stock_df.copy()
        if lote_filter:
            df_filtered = df_filtered[df_filtered['Lote'].isin(lote_filter)]
        if almacen_filter:
            df_filtered = df_filtered[df_filtered['Almacén'].isin(almacen_filter)]
        if estado_filter:
            df_filtered = df_filtered[df_filtered['Estado Stock'].isin(estado_filter)]

        # Métricas
        st.markdown("### 📈 Métricas Principales")
        metricas = self.calcular_metricas_generales(df_filtered)
        self.mostrar_metricas(metricas)

        # Visualizaciones
        st.markdown("### 📊 Análisis Visual")
        col1, col2 = st.columns(2)
        with col1:
            fig_stock = self.generar_grafico_stock(
                df_filtered, tipo='barras', titulo='Stock por Producto y Estado'
            )
            if fig_stock:
                st.plotly_chart(fig_stock, use_container_width=True)

        with col2:
            fig_tree = self.generar_grafico_stock(
                df_filtered, tipo='treemap', titulo='Distribución de Stock'
            )
            if fig_tree:
                st.plotly_chart(fig_tree, use_container_width=True)

        # Tabla
        st.markdown("### 📋 Detalle de Stock")
        st.dataframe(
            df_filtered[[
                'Almacén','Producto','Lote','Stock','Kg Total','Estado Stock',
                '% Disponible','Rotación'
            ]],
            use_container_width=True,
            height=400
        )

        # Gráfico Entradas vs Salidas y % Vendido
        st.markdown("### 📊 Entradas vs. Salidas y % Vendido (por Producto)")
        self.generar_grafico_entradas_vs_salidas(df_filtered)

    def ventas_view(self):
        """Vista de Ventas."""
        st.markdown(f"<h2 style='color: {self.COLOR_SCHEME['text']}; margin-bottom: 20px;'>💰 Análisis de Ventas</h2>", 
                    unsafe_allow_html=True)

        # Filtrar SALIDAS
        ventas = self.df[self.df['movimiento'] == 'SALIDA'].copy()
        ventas = ventas[ventas['precio'] > 0]

        if ventas.empty:
            st.warning("⚠️ No hay datos de ventas disponibles")
            return

        tabs = st.tabs(["📊 Resumen de Ventas", "👥 Análisis por Cliente", "📋 Detalle de Ventas"])

        with tabs[0]:
            total_ventas = ventas['precio total'].sum()
            total_kg = ventas['kg'].sum()
            total_cajas = ventas['cajas'].sum()
            precio_prom = total_ventas / total_kg if total_kg else 0

            metricas = {
                "Total Ventas": total_ventas,
                "Total Kg Vendidos": total_kg,
                "Total Cajas Vendidas": total_cajas,
                "Precio Promedio/Kg": precio_prom
            }
            self.mostrar_metricas(metricas)

            # Ventas por producto
            st.markdown("### 📈 Top Ventas por Producto")
            col1, col2 = st.columns([3,2])
            with col1:
                ventas_prod = ventas.groupby(['nombre','lote']).agg({
                    'cajas':'sum','kg':'sum','precio total':'sum'
                }).round(2).sort_values('precio total', ascending=False)
                ventas_prod['% del Total'] = (ventas_prod['precio total'] / total_ventas * 100).round(2)
                ventas_prod['Precio/Kg'] = (ventas_prod['precio total'] / ventas_prod['kg']).round(2)
                st.dataframe(ventas_prod, use_container_width=True, height=400)
            with col2:
                fig = px.pie(
                    ventas_prod.reset_index(),
                    values='precio total',
                    names='nombre',
                    title="Distribución de Ventas por Producto",
                    hole=0.4
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)

        with tabs[1]:
            st.markdown("### 👥 Análisis por Cliente")
            total_ventas = ventas['precio total'].sum()  # recalcular

            ventas_cliente = ventas.groupby('cliente').agg({
                'cajas':'sum','kg':'sum','precio total':'sum'
            }).round(2).sort_values('precio total', ascending=False)
            ventas_cliente['% del Total'] = (ventas_cliente['precio total'] / total_ventas * 100).round(2)
            ventas_cliente['Precio/Kg'] = (ventas_cliente['precio total'] / ventas_cliente['kg']).round(2)
            st.dataframe(ventas_cliente, use_container_width=True)

            st.markdown("### 🔍 Detalle por Cliente")
            cliente_sel = st.selectbox(
                "Seleccionar Cliente",
                options=sorted(ventas['cliente'].dropna().unique())
            )
            if cliente_sel:
                df_cliente = ventas[ventas['cliente'] == cliente_sel]
                total_cli = df_cliente['precio total'].sum()
                kg_cli = df_cliente['kg'].sum()

                metricas_cliente = {
                    "Total Compras": total_cli,
                    "Total Kg": kg_cli,
                    "% del Total": (total_cli/total_ventas*100) if total_ventas else 0,
                    "Precio Promedio/Kg": total_cli/kg_cli if kg_cli>0 else 0
                }
                self.mostrar_metricas(metricas_cliente)

                col1, col2 = st.columns(2)
                with col1:
                    fig_dist = px.pie(
                        df_cliente,
                        values='precio total',
                        names='nombre',
                        title=f"Distribución de Compras - {cliente_sel}",
                        hole=0.4
                    )
                    st.plotly_chart(fig_dist, use_container_width=True)
                with col2:
                    fig_bar = px.bar(
                        df_cliente,
                        x='nombre',
                        y=['cajas','kg'],
                        title=f"Cantidades por Producto - {cliente_sel}",
                        barmode='group'
                    )
                    fig_bar.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_bar, use_container_width=True)

        with tabs[2]:
            st.markdown("### 📋 Detalle de Ventas")
            col1, col2, col3 = st.columns(3)
            with col1:
                cliente_filter = st.multiselect(
                    "Filtrar por Cliente",
                    options=sorted(ventas['cliente'].dropna().unique())
                )
            with col2:
                producto_filter = st.multiselect(
                    "Filtrar por Producto",
                    options=sorted(ventas['nombre'].dropna().unique())
                )
            with col3:
                vendedor_filter = st.multiselect(
                    "Filtrar por Vendedor",
                    options=sorted([v for v in ventas['vendedor'].dropna().unique() if str(v).strip()])
                )

            df_fil = ventas.copy()
            if cliente_filter:
                df_fil = df_fil[df_fil['cliente'].isin(cliente_filter)]
            if producto_filter:
                df_fil = df_fil[df_fil['nombre'].isin(producto_filter)]
            if vendedor_filter:
                df_fil = df_fil[df_fil['vendedor'].isin(vendedor_filter)]

            st.dataframe(
                df_fil[[
                    'nombre','lote','cliente','vendedor',
                    'cajas','kg','precio','precio total'
                ]].sort_values(['cliente','nombre']),
                use_container_width=True,
                height=400
            )

    def vista_comercial(self):
        """Vista Comercial (Análisis de Stock + Ventas)."""
        st.markdown(f"<h2 style='color: {self.COLOR_SCHEME['text']}; margin-bottom: 20px;'>🎯 Vista Comercial</h2>", 
                    unsafe_allow_html=True)

        stock_df = self.calcular_stock_actual()
        if stock_df.empty:
            st.warning("⚠️ No hay datos de Stock para mostrar")
            return

        st.markdown("### 🔍 Filtros de Análisis")
        c1, c2, c3 = st.columns(3)
        with c1:
            lote_filter = st.multiselect(
                "Filtrar por Lote",
                options=sorted(stock_df['Lote'].unique())
            )
        with c2:
            alm_filter = st.multiselect(
                "Filtrar por Almacén",
                options=sorted(stock_df['Almacén'].unique())
            )
        with c3:
            est_filter = st.multiselect(
                "Filtrar por Estado",
                options=sorted(stock_df['Estado Stock'].unique())
            )

        df_f = stock_df.copy()
        if lote_filter:
            df_f = df_f[df_f['Lote'].isin(lote_filter)]
        if alm_filter:
            df_f = df_f[df_f['Almacén'].isin(alm_filter)]
        if est_filter:
            df_f = df_f[df_f['Estado Stock'].isin(est_filter)]

        tab1, tab2, tab3 = st.tabs(["📊 Resumen General", "🔍 Por Producto", "📍 Por Almacén"])

        with tab1:
            metricas = self.calcular_metricas_generales(df_f)
            self.mostrar_metricas(metricas)

            col1, col2 = st.columns(2)
            with col1:
                fig_stock = self.generar_grafico_stock(
                    df_f, tipo='barras', titulo='Stock por Producto y Estado'
                )
                if fig_stock:
                    st.plotly_chart(fig_stock, use_container_width=True, key="key_grafico1")

            with col2:
                fig_tree = self.generar_grafico_stock(
                    df_f, tipo='treemap', titulo='Distribución de Stock'
                )
                if fig_tree:
                    st.plotly_chart(fig_tree, use_container_width=True)

            st.markdown("#### 📊 Entradas vs. Salidas y % Vendido (por Producto)")
            self.generar_grafico_entradas_vs_salidas(df_f)

        with tab2:
            st.markdown("### 🔍 Análisis Detallado por Producto")
            prod_sel = st.selectbox(
                "Seleccionar Producto",
                options=sorted(df_f['Producto'].unique())
            )
            if prod_sel:
                df_prod = df_f[df_f['Producto'] == prod_sel]
                metricas_prod = {
                    "Stock Total": df_prod['Stock'].sum(),
                    "Kg Totales": df_prod['Kg Total'].sum(),
                    "Ventas Totales ($)": df_prod['Ventas Total'].sum(),
                    "Rotación (%)": df_prod['Rotación'].mean()
                }
                self.mostrar_metricas(metricas_prod)

                st.markdown("#### 📋 Detalle por Almacén y Lote")
                st.dataframe(
                    df_prod[[
                        'Almacén','Lote','Stock','Kg Total','Total Inicial',
                        'Salidas','% Vendido','% Disponible','Estado Stock'
                    ]].sort_values(['Almacén','Lote']),
                    use_container_width=True
                )

                c1, c2 = st.columns(2)
                with c1:
                    fig_pie = px.pie(
                        df_prod,
                        values='Stock',
                        names='Almacén',
                        title=f"Distribución por Almacén - {prod_sel}",
                        hole=0.4
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
                with c2:
                    fig_bar = px.bar(
                        df_prod,
                        x='Lote',
                        y=['Stock','Salidas'],
                        title=f"Stock vs Salidas - {prod_sel}",
                        barmode='group'
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

        with tab3:
            st.markdown("### 📍 Análisis Detallado por Almacén")
            alm_sel = st.selectbox(
                "Seleccionar Almacén",
                options=sorted(df_f['Almacén'].unique())
            )
            if alm_sel:
                df_alm = df_f[df_f['Almacén'] == alm_sel]
                metricas_alm = {
                    "Total Productos": len(df_alm['Producto'].unique()),
                    "Stock Total": df_alm['Stock'].sum(),
                    "Productos Críticos": len(df_alm[df_alm['Estado Stock'] == 'CRÍTICO'])
                }
                self.mostrar_metricas(metricas_alm, 3)

                st.markdown("#### 📊 Estado de Stock por Producto")
                resumen_stock = df_alm.groupby('Producto').agg({
                    'Stock': 'sum',
                    'Kg Total': 'sum',
                    'Total Inicial': 'sum',
                    'Salidas': 'sum',
                    '% Vendido': 'mean',
                    '% Disponible': 'mean'
                }).round(2).reset_index()

                # Determinar estado para cada producto
                def definir_estado(stock_val):
                    for est, cfg in self.ESTADOS_STOCK.items():
                        if stock_val <= cfg['umbral']:
                            return est
                    return 'NORMAL'

                resumen_stock['Estado'] = resumen_stock['Stock'].apply(definir_estado)

                st.dataframe(
                    resumen_stock.sort_values('Stock', ascending=False),
                    use_container_width=True
                )

                c1, c2 = st.columns(2)
                with c1:
                    fig_stock_alm = px.bar(
                        df_alm,
                        x='Producto',
                        y='Stock',
                        color='Estado Stock',
                        title=f"Stock por Producto - {alm_sel}"
                    )
                    fig_stock_alm.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_stock_alm, use_container_width=True)
                
                with c2:
                    fig_estados = px.pie(
                        df_alm,
                        names='Estado Stock',
                        values='Stock',
                        title=f"Distribución por Estado - {alm_sel}",
                        hole=0.4
                    )
                    st.plotly_chart(fig_estados, use_container_width=True)


    # -------------------------------------------------------------------------
    # (F) Método principal: run_dashboard()
    # -------------------------------------------------------------------------
    def run_dashboard(self):
        """Ejecución principal del Dashboard."""
        st.markdown(f"""
            <h1 style='text-align: center; color: {self.COLOR_SCHEME['primary']}; padding: 1rem 0;'>
                📦 Dashboard de Inventario COHESA
            </h1>
        """, unsafe_allow_html=True)

        with st.sidebar:
            st.markdown("### ⚙️ Control del Dashboard")
            st.write("🕒 Última actualización:", datetime.now().strftime("%H:%M:%S"))

            if st.button('🔄 Actualizar Datos', key="refresh_button"):
                st.cache_data.clear()
                st.rerun()

        if not self.load_data():
            st.error("❌ Error al cargar los datos")
            return

        tab1, tab2, tab3 = st.tabs(["📊 Stock", "💰 Ventas", "🎯 Vista Comercial"])

        with tab1:
            self.stock_view()

        with tab2:
            self.ventas_view()

        with tab3:
            self.vista_comercial()


# -----------------------------------------------------------------------------
#                   4) Punto de entrada: Ejecutar el Dashboard
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    dashboard = InventarioDashboard()
    dashboard.run_dashboard()