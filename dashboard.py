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
    if "gcp_service_account" not in st.secrets:
        st.error("No se encontraron credenciales en st.secrets (gcp_service_account).")
        return pd.DataFrame()

    credentials_dict = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        credentials_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )

    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

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
#        3) Clase principal del Dashboard
# -----------------------------------------------------------------------------
class InventarioDashboard:
    def __init__(self):
        # IDs y rangos de la Google Sheet (Ajusta a tus valores)
        self.SPREADSHEET_ID = "1acGspGuv-i0KSA5Q8owZpFJb1ytgm1xljBLZoa2cSN8"
        self.RANGE_CARNES = "Carnes!A1:L"
        self.RANGE_IMPORT = "Importacion!A1:E"

        # DataFrames principales
        self.df = pd.DataFrame()             # Para datos de "Carnes"
        self.df_import = pd.DataFrame()      # Para datos de "Importación"
        self.df_merged = pd.DataFrame()      # Para unir "Carnes" + "Importación"

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

        # Umbrales de stock (por número de Cajas)
        self.ESTADOS_STOCK = {
            'CRÍTICO': {'umbral': 5, 'color': '#e74c3c'},
            'BAJO': {'umbral': 20, 'color': '#f39c12'},
            'NORMAL': {'umbral': float('inf'), 'color': '#2ecc71'}
        }

    # -------------------------------------------------------------------------
    # 1) Carga de datos
    # -------------------------------------------------------------------------
    def load_data(self) -> bool:
        try:
            with st.spinner("Cargando datos..."):
                # Cargar datos de Carnes
                df_carnes = load_data_from_sheets(self.SPREADSHEET_ID, self.RANGE_CARNES)
                if df_carnes.empty:
                    st.error("📊 No se encontraron datos en la hoja de Carnes.")
                    return False

                # Cargar datos de Importación
                df_imp = load_data_from_sheets(self.SPREADSHEET_ID, self.RANGE_IMPORT)
                if df_imp.empty:
                    st.error("📊 No se encontraron datos en la hoja de Importación.")
                    return False

                # Limpieza inicial de df_carnes
                for col in ['cajas','kg','precio','precio total']:
                    if col in df_carnes.columns:
                        df_carnes[col] = pd.to_numeric(
                            df_carnes[col].replace(['', 'E', '#VALUE!', '#N/A'], '0'),
                            errors='coerce'
                        ).fillna(0)

                for col in ['movimiento','almacen','almacen actual','nombre']:
                    if col in df_carnes.columns:
                        df_carnes[col] = df_carnes[col].astype(str).str.strip().fillna('')

                # Limpieza en importación: cambio de comas a punto en KG NETOS, etc.
                if 'KG NETOS' in df_imp.columns:
                    df_imp['KG NETOS'] = (
                        df_imp['KG NETOS']
                        .astype(str)
                        .str.replace(',', '.', regex=False)
                        .astype(float)
                        .fillna(0)
                    )
                if 'CAJAS' in df_imp.columns:
                    df_imp['CAJAS'] = pd.to_numeric(df_imp['CAJAS'], errors='coerce').fillna(0)

                # Normalizar nombres para poder hacer merge
                df_imp_ren = df_imp.copy()
                df_imp_ren.rename(columns={'MERCADERIA': 'nombre'}, inplace=True)
                df_imp_ren['nombre'] = df_imp_ren['nombre'].str.strip().str.upper()

                df_carnes_ren = df_carnes.copy()
                df_carnes_ren['nombre'] = df_carnes_ren['nombre'].str.strip().str.upper()

                # Merge left: mantiene todas las filas de df_carnes
                df_merged = pd.merge(
                    df_carnes_ren,
                    df_imp_ren[['nombre','KG NETOS','CAJAS']],
                    how='left',
                    on='nombre'
                )

                self.df = df_carnes
                self.df_import = df_imp
                self.df_merged = df_merged

                st.success("✅ Datos cargados exitosamente")
                return True
        except Exception as e:
            st.error(f"Error al cargar datos: {str(e)}")
            return False

    # -------------------------------------------------------------------------
    # 2) Cálculo de stock actual (cajas y kg)
    # -------------------------------------------------------------------------
    def calcular_stock_actual(self) -> pd.DataFrame:
        """
        Calcula el stock actual (cajas y kg) por almacén-producto-lote,
        considerando ENTRADAS, TRASPASOS y SALIDAS.
        """
        try:
            df = self.df_merged.copy()
            if df.empty:
                return pd.DataFrame()

            with st.spinner("Calculando stock actual..."):
                stock_data = []

                # Unidades únicas
                productos = df['nombre'].unique()
                lotes = df['lote'].unique()

                # Almacenes: cualquier almacén donde haya habido movimientos
                almacenes = pd.concat([df['almacen'], df['almacen actual']]).unique()
                almacenes = [a for a in almacenes if str(a).strip() != '']

                total_items = len(productos) * len(lotes) * len(almacenes)
                progress_bar = st.progress(0)
                current_item = 0

                # Iterar combinaciones
                for prod in productos:
                    for lote in lotes:
                        for alm in almacenes:
                            current_item += 1
                            progress_bar.progress(current_item / total_items)

                            df_fil = df[(df['nombre'] == prod) & (df['lote'] == lote)]

                            # ENTRADAS (almacen = alm)
                            df_ent = df_fil[(df_fil['movimiento'].str.upper() == 'ENTRADA') & (df_fil['almacen'] == alm)]
                            entradas_cajas = df_ent['cajas'].sum()
                            entradas_kg = df_ent['kg'].sum()

                            # TRASPASOS RECIBIDOS (almacen actual = alm)
                            df_t_rec = df_fil[(df_fil['movimiento'].str.upper() == 'TRASPASO') & (df_fil['almacen actual'] == alm)]
                            tr_rec_cajas = df_t_rec['cajas'].sum()
                            tr_rec_kg = df_t_rec['kg'].sum()

                            # TRASPASOS ENVIADOS (almacen = alm)
                            df_t_env = df_fil[(df_fil['movimiento'].str.upper() == 'TRASPASO') & (df_fil['almacen'] == alm)]
                            tr_env_cajas = df_t_env['cajas'].sum()
                            tr_env_kg = df_t_env['kg'].sum()

                            # SALIDAS (almacen = alm)
                            df_sal = df_fil[(df_fil['movimiento'].str.upper() == 'SALIDA') & (df_fil['almacen'] == alm)]
                            salidas_cajas = df_sal['cajas'].sum()
                            salidas_kg = df_sal['kg'].sum()
                            ventas_total = df_sal['precio total'].sum()

                            # Totales en Cajas
                            total_inicial_cajas = entradas_cajas + tr_rec_cajas
                            stock_cajas = total_inicial_cajas - tr_env_cajas - salidas_cajas

                            # Totales en KG
                            total_inicial_kg = entradas_kg + tr_rec_kg
                            stock_kg = total_inicial_kg - tr_env_kg - salidas_kg

                            # Porcentajes
                            pct_vendido = self.analytics.calcular_porcentaje(salidas_cajas, total_inicial_cajas)
                            pct_disp = self.analytics.calcular_porcentaje(stock_cajas, total_inicial_cajas)
                            rotacion = pct_vendido

                            # Estado Stock (por número de cajas)
                            estado = 'NORMAL'
                            for est, config in self.ESTADOS_STOCK.items():
                                if stock_cajas <= config['umbral']:
                                    estado = est
                                    break

                            # Llenar datos si hay algo de movimiento
                            if (total_inicial_cajas > 0) or (stock_cajas != 0):
                                # Info de importación (KG NETOS, CAJAS)
                                row_imp = df_fil.iloc[0]  # Toma la 1a fila del merge
                                kg_importados = row_imp.get('KG NETOS', 0.0) or 0.0
                                cajas_importadas = row_imp.get('CAJAS', 0.0) or 0.0

                                # Diferencia: stock_kg vs kg_importados
                                diferencia_kg = stock_kg - kg_importados
                                pct_utilizado = self.analytics.calcular_porcentaje(stock_kg, kg_importados)

                                stock_data.append({
                                    'Almacén': alm,
                                    'Producto': prod,
                                    'Lote': lote,
                                    'Stock (Cajas)': stock_cajas,
                                    'Stock (Kg)': round(stock_kg,2),
                                    'Total Inicial (Cajas)': total_inicial_cajas,
                                    'Entradas (Cajas)': entradas_cajas,
                                    'Salidas (Cajas)': salidas_cajas,
                                    'Traspasos Recibidos (Cajas)': tr_rec_cajas,
                                    'Traspasos Enviados (Cajas)': tr_env_cajas,
                                    'Ventas Total': ventas_total,
                                    '% Vendido': pct_vendido,
                                    '% Disponible': pct_disp,
                                    'Estado Stock': estado,
                                    'Rotación': rotacion,
                                    'KG Importados': kg_importados,
                                    'Cajas Importadas': cajas_importadas,
                                    'Diferencia Kg': diferencia_kg,
                                    '% Utilizado': pct_utilizado
                                })

                progress_bar.empty()
                df_stock = pd.DataFrame(stock_data).round(2)
                return df_stock

        except Exception as e:
            st.error(f"❌ Error en el cálculo de stock: {str(e)}")
            return pd.DataFrame()

    # -------------------------------------------------------------------------
    # 3) Métricas Generales
    # -------------------------------------------------------------------------
    def calcular_metricas_generales(self, stock_df: pd.DataFrame) -> dict:
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
                'Total Cajas en Stock': stock_df['Stock (Cajas)'].sum(),
                'Total Kg en Stock': stock_df['Stock (Kg)'].sum(),
                'Total Ventas ($)': stock_df['Ventas Total'].sum(),
                'Productos en Estado Crítico': len(stock_df[stock_df['Estado Stock'] == 'CRÍTICO']),
                'Rotación Promedio (%)': stock_df['Rotación'].mean()
            }
        except Exception as e:
            st.error(f"Error cálculo métricas generales: {e}")
            return {}

    def mostrar_metricas(self, metricas: dict, columnas=4):
        """
        Muestra métricas en tarjetas (cards) dentro de una fila con `columnas` columnas.
        """
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
    # 4) Generación de gráficas
    # -------------------------------------------------------------------------
    def generar_grafico_stock(self, stock_df: pd.DataFrame, tipo='barras', titulo='', key_suffix=''):
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
                y='Stock (Cajas)',
                color='Estado Stock',
                color_discrete_map={
                    'CRÍTICO': self.ESTADOS_STOCK['CRÍTICO']['color'],
                    'BAJO': self.ESTADOS_STOCK['BAJO']['color'],
                    'NORMAL': self.ESTADOS_STOCK['NORMAL']['color']
                },
                title=titulo or 'Stock (Cajas) por Producto'
            )
            fig.update_layout(**layout_config, xaxis_tickangle=-45, height=500, bargap=0.2)

        elif tipo == 'pie':
            fig = px.pie(
                stock_df,
                values='Stock (Cajas)',
                names='Almacén',
                title=titulo or 'Distribución por Almacén'
            )
            fig.update_traces(textposition='inside', textinfo='percent+label', hole=0.4)
            fig.update_layout(**layout_config)

        elif tipo == 'treemap':
            fig = px.treemap(
                stock_df,
                path=['Almacén', 'Producto'],
                values='Stock (Cajas)',
                color='Estado Stock',
                title=titulo or 'Distribución de Stock',
                color_discrete_map={
                    'CRÍTICO': self.ESTADOS_STOCK['CRÍTICO']['color'],
                    'BAJO': self.ESTADOS_STOCK['BAJO']['color'],
                    'NORMAL': self.ESTADOS_STOCK['NORMAL']['color']
                }
            )
            fig.update_layout(**layout_config)

        else:
            return None

        return fig

    def generar_grafico_entradas_vs_salidas(self, stock_df: pd.DataFrame, key_suffix=''):
        """
        Gráfico que compara la suma total de Entradas (Cajas) vs Salidas (Cajas) por producto,
        y muestra la línea de % Vendido (cajas vendidas / total inicial).
        """
        if stock_df.empty:
            st.warning("No hay datos para Entradas vs. Salidas")
            return

        df_group = stock_df.groupby('Producto').agg({
            'Entradas (Cajas)': 'sum',
            'Salidas (Cajas)': 'sum',
            'Total Inicial (Cajas)': 'sum'
        }).reset_index()

        df_group['% Vendido'] = df_group.apply(
            lambda row: self.analytics.calcular_porcentaje(row['Salidas (Cajas)'], row['Total Inicial (Cajas)']),
            axis=1
        )

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        fig.add_trace(
            go.Bar(
                x=df_group['Producto'],
                y=df_group['Entradas (Cajas)'],
                name='Entradas (Cajas)',
                marker_color=self.COLOR_SCHEME['success']
            ),
            secondary_y=False
        )
        fig.add_trace(
            go.Bar(
                x=df_group['Producto'],
                y=df_group['Salidas (Cajas)'],
                name='Salidas (Cajas)',
                marker_color=self.COLOR_SCHEME['warning']
            ),
            secondary_y=False
        )
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
            title_text="Entradas vs. Salidas y % Vendido (por Cajas)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(title="Producto", tickangle=-45),
            yaxis=dict(title="Cajas"),
            yaxis2=dict(title="% Vendido", overlaying='y', side='right'),
            hovermode="x unified",
            plot_bgcolor='white'
        )
        st.plotly_chart(fig, use_container_width=True, key=f"entradas_salidas_{key_suffix}")

    # -------------------------------------------------------------------------
    # 5) Vistas del Dashboard
    # -------------------------------------------------------------------------
    def stock_view(self):
        st.markdown(f"<h2 style='color: {self.COLOR_SCHEME['text']}; margin-bottom: 20px;'>📊 Vista General de Stock</h2>", 
                    unsafe_allow_html=True)

        stock_df = self.calcular_stock_actual()
        if stock_df.empty:
            st.warning("⚠️ No hay datos disponibles para mostrar")
            return

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

        # Aplicamos filtros
        df_filtered = stock_df.copy()
        if lote_filter:
            df_filtered = df_filtered[df_filtered['Lote'].isin(lote_filter)]
        if almacen_filter:
            df_filtered = df_filtered[df_filtered['Almacén'].isin(almacen_filter)]
        if estado_filter:
            df_filtered = df_filtered[df_filtered['Estado Stock'].isin(estado_filter)]

        st.markdown("### 📈 Métricas Principales")
        metricas = self.calcular_metricas_generales(df_filtered)
        self.mostrar_metricas(metricas)

        # Gráficas
        st.markdown("### 📊 Análisis Visual")
        colA, colB = st.columns(2)
        with colA:
            fig_stock = self.generar_grafico_stock(
                df_filtered, 
                tipo='barras', 
                titulo='Stock (Cajas) por Producto y Estado',
                key_suffix='stock_view_1'
            )
            if fig_stock:
                st.plotly_chart(fig_stock, use_container_width=True)

        with colB:
            fig_tree = self.generar_grafico_stock(
                df_filtered,
                tipo='treemap',
                titulo='Distribución de Stock',
                key_suffix='stock_view_2'
            )
            if fig_tree:
                st.plotly_chart(fig_tree, use_container_width=True)

        st.markdown("### 📋 Detalle de Stock")
        columns_to_display = [
            'Almacén','Producto','Lote',
            'Stock (Cajas)','Stock (Kg)',
            'KG Importados','Cajas Importadas',
            'Diferencia Kg','% Utilizado',
            'Estado Stock','% Disponible','Rotación'
        ]
        st.dataframe(
            df_filtered[columns_to_display],
            use_container_width=True,
            height=400
        )

        # Entradas vs Salidas
        st.markdown("### 📊 Entradas vs. Salidas (Cajas)")
        self.generar_grafico_entradas_vs_salidas(df_filtered, key_suffix='stock_view')

    def ventas_view(self):
        st.markdown(f"<h2 style='color: {self.COLOR_SCHEME['text']}; margin-bottom: 20px;'>💰 Análisis de Ventas</h2>", 
                    unsafe_allow_html=True)

        # Tomamos del DF original todas las filas con movimiento = SALIDA y precio>0
        df_ventas = self.df_merged.copy()
        df_ventas = df_ventas[df_ventas['movimiento'].str.upper() == 'SALIDA']
        df_ventas = df_ventas[df_ventas['precio'] > 0]

        if df_ventas.empty:
            st.warning("⚠️ No hay datos de ventas disponibles")
            return

        tabs = st.tabs(["📊 Resumen de Ventas", "👥 Análisis por Cliente", "📋 Detalle de Ventas"])

        # --- TAB 1: Resumen de Ventas
        with tabs[0]:
            total_ventas = df_ventas['precio total'].sum()
            total_kg = df_ventas['kg'].sum()
            total_cajas = df_ventas['cajas'].sum()
            precio_prom = total_ventas / total_kg if total_kg else 0

            metricas = {
                "Total Ventas ($)": total_ventas,
                "Total Kg Vendidos": total_kg,
                "Total Cajas Vendidas": total_cajas,
                "Precio Promedio/Kg": precio_prom
            }
            self.mostrar_metricas(metricas)

            st.markdown("### 📈 Top Ventas por Producto")
            col1, col2 = st.columns([3,2])
            with col1:
                ventas_prod = df_ventas.groupby(['nombre','lote']).agg({
                    'cajas':'sum',
                    'kg':'sum',
                    'precio total':'sum'
                }).round(2).sort_values('precio total', ascending=False)
                ventas_prod['% del Total'] = (ventas_prod['precio total'] / total_ventas * 100).round(2)
                ventas_prod['Precio/Kg'] = (ventas_prod['precio total'] / ventas_prod['kg']).round(2)
                st.dataframe(ventas_prod, use_container_width=True)

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

        # --- TAB 2: Análisis por Cliente
        with tabs[1]:
            st.markdown("### 👥 Análisis por Cliente")
            total_ventas = df_ventas['precio total'].sum()
            ventas_cliente = df_ventas.groupby('cliente').agg({
                'cajas': 'sum',
                'kg': 'sum',
                'precio total': 'sum'
            }).round(2).sort_values('precio total', ascending=False)
            if not ventas_cliente.empty:
                ventas_cliente['% del Total'] = (ventas_cliente['precio total'] / total_ventas * 100).round(2)
                ventas_cliente['Precio/Kg'] = (ventas_cliente['precio total'] / ventas_cliente['kg']).round(2)

            st.dataframe(ventas_cliente, use_container_width=True)

            st.markdown("### 🔍 Detalle por Cliente")
            clientes_disp = sorted(df_ventas['cliente'].dropna().unique())
            cliente_sel = st.selectbox(
                "Seleccionar Cliente",
                options=clientes_disp,
                key="ventas_cliente_select"
            )
            if cliente_sel:
                df_cliente = df_ventas[df_ventas['cliente'] == cliente_sel]
                total_cli = df_cliente['precio total'].sum()
                kg_cli = df_cliente['kg'].sum()

                metricas_cliente = {
                    "Total Compras ($)": total_cli,
                    "Total Kg": kg_cli,
                    "% del Total Ventas": (total_cli / total_ventas * 100) if total_ventas else 0,
                    "Precio Promedio/Kg": (total_cli / kg_cli) if kg_cli>0 else 0
                }
                self.mostrar_metricas(metricas_cliente, 2)

                cA, cB = st.columns(2)
                with cA:
                    fig_dist = px.pie(
                        df_cliente,
                        values='precio total',
                        names='nombre',
                        title=f"Distribución de Compras - {cliente_sel}",
                        hole=0.4
                    )
                    st.plotly_chart(fig_dist, use_container_width=True)

                with cB:
                    fig_bar = px.bar(
                        df_cliente,
                        x='nombre',
                        y=['cajas','kg'],
                        barmode='group',
                        title=f"Cajas y Kg por Producto - {cliente_sel}"
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

        # --- TAB 3: Detalle de Ventas
        with tabs[2]:
            st.markdown("### 📋 Detalle de Ventas")
            col1, col2, col3 = st.columns(3)
            with col1:
                cliente_filter = st.multiselect(
                    "Filtrar por Cliente",
                    options=sorted(df_ventas['cliente'].dropna().unique()),
                    key="ventas_cliente_filter"
                )
            with col2:
                producto_filter = st.multiselect(
                    "Filtrar por Producto",
                    options=sorted(df_ventas['nombre'].dropna().unique()),
                    key="ventas_producto_filter"
                )
            with col3:
                vendedor_filter = st.multiselect(
                    "Filtrar por Vendedor",
                    options=sorted(df_ventas['vendedor'].dropna().unique()),
                    key="ventas_vendedor_filter"
                )

            df_det = df_ventas.copy()
            if cliente_filter:
                df_det = df_det[df_det['cliente'].isin(cliente_filter)]
            if producto_filter:
                df_det = df_det[df_det['nombre'].isin(producto_filter)]
            if vendedor_filter:
                df_det = df_det[df_det['vendedor'].isin(vendedor_filter)]

            st.dataframe(
                df_det[['nombre','lote','cliente','vendedor','cajas','kg','precio','precio total']].sort_values(['cliente','nombre']),
                use_container_width=True,
                height=400
            )

    def vista_comercial(self):
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
                options=sorted(stock_df['Lote'].unique()),
                key="comercial_lote_filter"
            )
        with c2:
            alm_filter = st.multiselect(
                "Filtrar por Almacén",
                options=sorted(stock_df['Almacén'].unique()),
                key="comercial_almacen_filter"
            )
        with c3:
            est_filter = st.multiselect(
                "Filtrar por Estado",
                options=sorted(stock_df['Estado Stock'].unique()),
                key="comercial_estado_filter"
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

            colA, colB = st.columns(2)
            with colA:
                fig_stock = self.generar_grafico_stock(
                    df_f, tipo='barras', titulo='Stock (Cajas) por Producto y Estado'
                )
                if fig_stock:
                    st.plotly_chart(fig_stock, use_container_width=True)

            with colB:
                fig_tree = self.generar_grafico_stock(
                    df_f, tipo='treemap', titulo='Distribución de Stock'
                )
                if fig_tree:
                    st.plotly_chart(fig_tree, use_container_width=True)

            st.markdown("#### 📊 Entradas vs. Salidas y % Vendido (por Producto)")
            self.generar_grafico_entradas_vs_salidas(df_f, key_suffix='comercial_view')

        with tab2:
            st.markdown("### 🔍 Análisis Detallado por Producto")
            prods_disp = sorted(df_f['Producto'].unique())
            if not prods_disp:
                st.info("No hay productos disponibles.")
                return
            prod_sel = st.selectbox(
                "Seleccionar Producto",
                options=prods_disp,
                key="comercial_producto_select"
            )
            if prod_sel:
                df_prod = df_f[df_f['Producto'] == prod_sel]
                metricas_prod = {
                    "Stock Total (Cajas)": df_prod['Stock (Cajas)'].sum(),
                    "Kg Totales": df_prod['Stock (Kg)'].sum(),
                    "Ventas Totales ($)": df_prod['Ventas Total'].sum(),
                    "Rotación (%)": df_prod['Rotación'].mean()
                }
                self.mostrar_metricas(metricas_prod, columnas=2)

                st.markdown("#### 📋 Detalle por Almacén y Lote")
                st.dataframe(
                    df_prod[[
                        'Almacén','Lote','Stock (Cajas)','Stock (Kg)',
                        'Total Inicial (Cajas)','Salidas (Cajas)',
                        '% Vendido','% Disponible','Estado Stock'
                    ]].sort_values(['Almacén','Lote']),
                    use_container_width=True
                )

                cA, cB = st.columns(2)
                with cA:
                    fig_pie = px.pie(
                        df_prod,
                        values='Stock (Cajas)',
                        names='Almacén',
                        title=f"Distribución por Almacén - {prod_sel}",
                        hole=0.4
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
                
                with cB:
                    fig_bar = px.bar(
                        df_prod,
                        x='Lote',
                        y=['Stock (Cajas)','Salidas (Cajas)'],
                        title=f"Stock vs Salidas (Cajas) - {prod_sel}",
                        barmode='group'
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)

        with tab3:
            st.markdown("### 📍 Análisis Detallado por Almacén")
            almacenes_disp = sorted(df_f['Almacén'].unique())
            if not almacenes_disp:
                st.info("No hay almacenes disponibles.")
                return
            alm_sel = st.selectbox(
                "Seleccionar Almacén",
                options=almacenes_disp,
                key="comercial_almacen_select"
            )
            if alm_sel:
                df_alm = df_f[df_f['Almacén'] == alm_sel]
                metricas_alm = {
                    "Total Productos": len(df_alm['Producto'].unique()),
                    "Stock Total (Cajas)": df_alm['Stock (Cajas)'].sum(),
                    "Productos Críticos": len(df_alm[df_alm['Estado Stock'] == 'CRÍTICO'])
                }
                self.mostrar_metricas(metricas_alm, 3)

                st.markdown("#### 📊 Estado de Stock por Producto")
                resumen_stock = df_alm.groupby('Producto').agg({
                    'Stock (Cajas)': 'sum',
                    'Stock (Kg)': 'sum',
                    'Total Inicial (Cajas)': 'sum',
                    'Salidas (Cajas)': 'sum',
                    '% Vendido': 'mean',
                    '% Disponible': 'mean'
                }).reset_index().round(2)

                def definir_estado(stock_val):
                    for est, cfg in self.ESTADOS_STOCK.items():
                        if stock_val <= cfg['umbral']:
                            return est
                    return 'NORMAL'

                resumen_stock['Estado'] = resumen_stock['Stock (Cajas)'].apply(definir_estado)

                st.dataframe(resumen_stock, use_container_width=True)

                cA, cB = st.columns(2)
                with cA:
                    fig_stock_alm = px.bar(
                        df_alm,
                        x='Producto',
                        y='Stock (Cajas)',
                        color='Estado Stock',
                        title=f"Stock (Cajas) por Producto - {alm_sel}"
                    )
                    fig_stock_alm.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig_stock_alm, use_container_width=True)

                with cB:
                    fig_estados = px.pie(
                        df_alm,
                        names='Estado Stock',
                        values='Stock (Cajas)',
                        title=f"Distribución por Estado - {alm_sel}",
                        hole=0.4
                    )
                    st.plotly_chart(fig_estados, use_container_width=True)

    # -------------------------------------------------------------------------
    # 6) Ejecución del Dashboard
    # -------------------------------------------------------------------------
    def run_dashboard(self):
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