import streamlit as st
import pandas as pd
import plotly.express as px
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path

class InventarioDashboard:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        self.SPREADSHEET_ID = '1acGspGuv-i0KSA5Q8owZpFJb1ytgm1xljBLZoa2cSN8'
        self.RANGE_NAME = 'Carnes!A1:L'
        self.df = None

    def get_credentials(self):
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'client_secret.json', self.SCOPES)
                creds = flow.run_local_server(port=8080)
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        return creds

    def load_data(self):
        creds = self.get_credentials()
        try:
            service = build('sheets', 'v4', credentials=creds)
            sheet = service.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=self.SPREADSHEET_ID,
                range=self.RANGE_NAME
            ).execute()
            values = result.get('values', [])
            
            if not values:
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
        Calcula el stock actual con porcentajes de venta
        """
        stock_data = []
        
        # Lista de todos los productos únicos (22 cortes)
        todos_productos = self.df['nombre'].unique()
        
        # Procesar cada almacén
        for almacen in self.df['almacen'].unique():
            # Procesar cada producto
            for producto in todos_productos:
                # 1. Entradas directas
                entradas = self.df[
                    (self.df['movimiento'] == 'ENTRADA') & 
                    (self.df['almacen'] == almacen) & 
                    (self.df['nombre'] == producto)
                ]['cajas'].sum()
                
                # 2. Traspasos recibidos
                traspasos_recibidos_df = self.df[
                    (self.df['movimiento'] == 'TRASPASO') & 
                    (self.df['almacen actual'] == almacen) & 
                    (self.df['nombre'] == producto)
                ]
                traspasos_recibidos = traspasos_recibidos_df['cajas'].sum()
                kg_traspasos_recibidos = traspasos_recibidos_df['kg'].sum()
                
                # 3. Traspasos enviados
                traspasos_enviados_df = self.df[
                    (self.df['movimiento'] == 'TRASPASO') & 
                    (self.df['almacen'] == almacen) & 
                    (self.df['nombre'] == producto)
                ]
                traspasos_enviados = traspasos_enviados_df['cajas'].sum()
                kg_traspasos_enviados = traspasos_enviados_df['kg'].sum()
                
                # 4. Salidas (ventas)
                salidas_df = self.df[
                    (self.df['movimiento'] == 'SALIDA') & 
                    (self.df['almacen'] == almacen) & 
                    (self.df['nombre'] == producto)
                ]
                salidas = salidas_df['cajas'].sum()
                kg_salidas = salidas_df['kg'].sum()
                
                # Calcular stock final
                stock = entradas + traspasos_recibidos - traspasos_enviados - salidas
                
                # Calcular kg totales
                kg_total = kg_traspasos_recibidos - kg_traspasos_enviados - kg_salidas
                
                # Calcular total inicial y porcentajes
                total_inicial = entradas + traspasos_recibidos
                if total_inicial > 0:
                    porcentaje_vendido = (salidas / total_inicial) * 100
                    porcentaje_disponible = (stock / total_inicial) * 100
                else:
                    porcentaje_vendido = 0
                    porcentaje_disponible = 0
                
                if stock != 0 or total_inicial > 0:  # Incluir productos con historial
                    stock_data.append({
                        'Almacén': almacen,
                        'Producto': producto,
                        'Stock': stock,
                        'Kg Total': kg_total,
                        'Total Inicial': total_inicial,
                        'Entradas': entradas,
                        'Traspasos Recibidos': traspasos_recibidos,
                        'Traspasos Enviados': traspasos_enviados,
                        'Salidas': salidas,
                        'Kg por Traspasos': kg_traspasos_recibidos,
                        'Kg por Salidas': kg_salidas,
                        '% Vendido': round(porcentaje_vendido, 2),
                        '% Disponible': round(porcentaje_disponible, 2)
                    })
        
        return pd.DataFrame(stock_data)
    def vista_comercial(self):
        """Vista específica para el equipo comercial"""
        st.subheader("Vista Comercial - Stock por Corte")
        
        # Obtener stock actual
        stock_df = self.calcular_stock_actual()
        
        # Crear tabs para diferentes vistas
        tab1, tab2 = st.tabs(["Resumen General", "Análisis por Producto"])
        
        with tab1:
            # Resumen general
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Stock y Porcentajes de Venta")
                resumen = stock_df.groupby('Producto').agg({
                    'Total Inicial': 'sum',
                    'Stock': 'sum',
                    'Salidas': 'sum'
                }).round(2)
                
                # Calcular porcentajes totales
                resumen['% Vendido'] = (resumen['Salidas'] / resumen['Total Inicial'] * 100).round(2)
                resumen['% Disponible'] = (resumen['Stock'] / resumen['Total Inicial'] * 100).round(2)
                
                st.dataframe(resumen.sort_values('% Vendido', ascending=False))
            
            with col2:
                st.markdown("### Distribución de Ventas vs Stock")
                fig = px.bar(resumen, 
                            x=resumen.index, 
                            y=['% Vendido', '% Disponible'],
                            title="Porcentaje Vendido vs Disponible por Producto",
                            barmode='stack')
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
            cols = ['Almacén', 'Stock', 'Total Inicial', 'Salidas', '% Vendido', '% Disponible']
            st.dataframe(detalle_producto[cols])

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
                resumen.columns = ['Total Cajas', 'Productos Diferentes', 'Total Kg']
                st.dataframe(resumen)
            
            with col2:
                st.markdown("### Distribución de Stock")
                fig = px.pie(stock_df, values='Stock', names='Almacén')
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            # Selector de almacén
            almacen_seleccionado = st.selectbox(
                "Seleccionar Almacén",
                options=sorted(stock_df['Almacén'].unique())
            )
            
            # Mostrar detalle del almacén seleccionado
            stock_almacen = stock_df[stock_df['Almacén'] == almacen_seleccionado]
            
            st.markdown(f"### Detalle de Stock en {almacen_seleccionado}")
            detalle_cols = ['Producto', 'Stock', 'Total Inicial', 'Salidas', '% Vendido', '% Disponible']
            st.dataframe(stock_almacen[detalle_cols].sort_values('Stock', ascending=False))
            
            # Gráfico de barras del stock por producto
            fig = px.bar(stock_almacen, x='Producto', y='Stock',
                        title=f'Stock por Producto en {almacen_seleccionado}')
            st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            # Mostrar movimientos detallados
            st.markdown("### Movimientos Detallados")
            movimientos = self.df[self.df['almacen'] == almacen_seleccionado].copy()
            st.dataframe(movimientos[['nombre', 'movimiento', 'almacen', 'almacen actual', 
                                    'cajas', 'kg', 'cliente']])

    def ventas_view(self):
        st.subheader("Análisis de Ventas")
        
        ventas = self.df[self.df['movimiento'] == 'SALIDA'].copy()
        ventas = ventas[ventas['precio'] > 0]

        if not ventas.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Top Ventas por Monto")
                ventas_producto = ventas.groupby('nombre').agg({
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

    def movimientos_view(self):
        st.subheader("Registro de Movimientos")
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            tipo_movimiento = st.multiselect(
                "Tipo de Movimiento",
                options=sorted(self.df['movimiento'].unique())
            )
        with col2:
            almacen_select = st.multiselect(
                "Almacén",
                options=sorted(self.df['almacen'].unique())
            )
        
        # Aplicar filtros
        df_mov = self.df.copy()
        if tipo_movimiento:
            df_mov = df_mov[df_mov['movimiento'].isin(tipo_movimiento)]
        if almacen_select:
            df_mov = df_mov[df_mov['almacen'].isin(almacen_select)]
        
        # Mostrar movimientos
        st.dataframe(
            df_mov[['id', 'nombre', 'movimiento', 'almacen', 'almacen actual', 
                    'cajas', 'kg', 'vendedor', 'cliente']].sort_values('id'),
            use_container_width=True
        )

    def run_dashboard(self):
        st.set_page_config(page_title="Inventario COHESA", layout="wide")
        st.title("Dashboard de Inventario COHESA")

        if not self.load_data():
            st.error("Error al cargar los datos")
            return

        # Tabs principales
        tab1, tab2, tab3, tab4 = st.tabs(["Vista Comercial", "Stock", "Ventas", "Movimientos"])
        
        with tab1:
            self.vista_comercial()
        
        with tab2:
            self.stock_view()
        
        with tab3:
            self.ventas_view()
        
        with tab4:
            self.movimientos_view()

if __name__ == '__main__':
    dashboard = InventarioDashboard()
    dashboard.run_dashboard()
