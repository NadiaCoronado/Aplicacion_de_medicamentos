import streamlit as st
import pandas as pd
import plotly.express as px
from fpdf import FPDF
import os
from datetime import datetime

# --- NUEVA LIBRERÍA PARA SUPABASE ---
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN DEL SISTEMA Y SUPABASE ---
st.set_page_config(page_title="Gestión Clínica Aplicación de Médicamentos", layout="wide", page_icon="👁️")

# 👇 REEMPLAZA ESTO CON TUS CREDENCIALES DE SUPABASE 👇
# (Las encuentras en Supabase -> Project Settings -> API)
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
NOMBRE_TABLA = "RETINA" # Escribe el nombre exacto de la tabla que creaste

# Iniciar conexión a Supabase
@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

CARPETA_IMG = "temp_imagenes_oct"
if not os.path.exists(CARPETA_IMG):
    os.makedirs(CARPETA_IMG)

SNELLEN_MAP = {
    "20/20": 0.00, "20/25": 0.10, "20/30": 0.18, "20/40": 0.30,
    "20/50": 0.40, "20/60": 0.48, "20/70": 0.54, "20/80": 0.60,
    "20/100": 0.70, "20/125": 0.80, "20/150": 0.88, "20/200": 1.00,
    "20/400": 1.30, "Cuenta Dedos": 1.90, "Mov. Manos": 2.30, "PL": 3.00
}

# --- 2. MOTOR DE DECISIÓN (ALERTAS) ---
def analizar_protocolo(datos, av_previa=None):
    if datos.get('Atrofia') == "Sí" or datos.get('Fibrosis') == "Sí":
        return "SE SUGIERE SUSPENDER (Daño Estructural)", "rojo"
    
    if av_previa is not None:
        try:
            cambio = float(datos.get('AV_OD_LogMAR', 0)) - float(av_previa)
            if cambio >= 0.2:
                return f"ALERTA (Pérdida de {cambio:.2f} LogMAR)", "naranja"
        except: pass
        
    return "SE SUGIERE CONTINUAR TRATAMIENTO", "verde"

# --- 3. GESTIÓN DE DATOS (AHORA CONECTADO A SUPABASE) ---
def cargar_datos():
    try:
        # Traer todos los datos de Supabase
        respuesta = supabase.table(NOMBRE_TABLA).select("*").execute()
        
        # Si hay datos, los convertimos a un DataFrame de Pandas
        if respuesta.data:
            return pd.DataFrame(respuesta.data)
        else:
            return pd.DataFrame() # Retorna vacío si no hay datos
    except Exception as e:
        st.error(f"Error de conexión al cargar datos: {e}")
        return pd.DataFrame()

def guardar_datos(nuevo):
    try:
        # Enviar el nuevo registro a Supabase
        respuesta = supabase.table(NOMBRE_TABLA).insert(nuevo).execute()
        return True
    except Exception as e:
        st.error(f"Error de conexión al guardar en Supabase: {e}")
        return False

# --- 4. GENERADOR DE PDF CON SEMAFORIZACIÓN ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'REPORTE MEDICO DE INVESTIGACION - APLICACION DE MEDICAMENTOS', 0, 1, 'C')
        self.ln(5)

def generar_pdf(df_p, id_p, ruta_img=None):
    pdf = PDFReport()
    pdf.add_page()
    reg = df_p.iloc[-1]
    
    # Encabezado del Paciente
    pdf.set_fill_color(220, 230, 241)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"ID: {id_p} | MEDICO: {reg.get('Medico')} | GENERO: {reg.get('Genero')}", 1, 1, 'L', fill=True)
    pdf.ln(2)

    for i, row in df_p.iterrows():
        # Fondo para cada visita
        pdf.set_font("Arial", 'B', 11)
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(0, 8, f"VISITA: {row.get('Momento')} | FECHA: {row.get('Fecha_App')}", 1, 1, 'L', fill=True)
        
        # Datos Clínicos Solicitados
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 6, f"Agudeza Visual: OD {row.get('AV_OD_LogMAR')} LogMAR | OI {row.get('AV_OI_LogMAR')} LogMAR", 1, 1)
        pdf.cell(0, 6, f"Espesor Retina (CST): {row.get('CST')} um | Medicamento: {row.get('Medicamento')}", 1, 1)
        
        # Semaforización de la Alerta
        decision = str(row.get('Decision', ''))
        if "SE SUGIERE SUSPENDER" in decision or "rojo" in str(row.get('Color_Alerta')):
            pdf.set_text_color(200, 0, 0) # Rojo
        elif "SE SUGIERE CONTINUAR" in decision or "verde" in str(row.get('Color_Alerta')):
            pdf.set_text_color(0, 150, 0) # Verde
        else:
            pdf.set_text_color(255, 140, 0) # Naranja/Alerta
            
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 8, f"ESTADO: {decision}", 1, 1)
        pdf.set_text_color(0, 0, 0) # Reset color a negro
        pdf.ln(4)

    # Imagen OCT si existe
    if ruta_img and pd.notna(ruta_img) and os.path.exists(str(ruta_img)):
        pdf.add_page()
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "ANEXO: IMAGEN OCT AO", 0, 1, 'C')
        pdf.image(str(ruta_img), x=15, y=30, w=180)

    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 5. INTERFAZ ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

if not st.session_state.password_correct:
    st.title("🔒 Acceso Seguro - Retina")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if u == "admin" and p == "admin123":
            st.session_state.password_correct = True
            st.rerun()
else:
    menu = st.sidebar.radio("Menú", ["📝 Registro Clínico", "📊 Tablero & PDF", "🤖 IA"])

    if menu == "📝 Registro Clínico":
        st.title("📝 Ficha Clínica Integral")
        df_hist = cargar_datos()
        
        c1, c2 = st.columns(2)
        id_paciente = c1.text_input("Identificación (ID)*")
        momento = c2.selectbox("Número de Aplicación (Visita)", ["Basal"] + [f"Inyección #{i}" for i in range(1, 13)])

        av_previa = None
        if id_paciente and not df_hist.empty:
            p_hist = df_hist[df_hist['ID'].astype(str) == str(id_paciente)]
            if not p_hist.empty:
                av_previa = p_hist.iloc[-1].get('AV_OD_LogMAR')
                st.info(f"📋 Registro Anterior OD: {av_previa} LogMAR")

        tabs = st.tabs(["👤 Filiación", "🏥 Antecedentes", "💊 Tx & Dx", "👁️ Visión", "🔬 OCT", "🧬 Biomarc.", "❤️ Vida/IMC"])
        
        with tabs[0]: # FILIACIÓN
            col1, col2, col3 = st.columns(3)
            filiacion = col1.text_input("Nombre / Iniciales")
            etnia = col2.selectbox("Etnia", ["Mestizo", "Caucásico", "Afrodescendiente", "Indígena", "Otro"])
            genero = col3.radio("Género", ["F", "M"], horizontal=True)
            medico = st.text_input("Médico Tratante")
            entidad = st.text_input("Entidad (EPS)")
            regimen = st.selectbox("Régimen", ["Contributivo", "Subsidiado", "Especial/Otro"])
            fecha_app = st.date_input("Fecha de Aplicación")

        with tabs[1]: # ANTECEDENTES
            cA, cB = st.columns(2)
            coronaria = cA.selectbox("Enf. Coronaria", ["No", "Sí"])
            hta = cA.selectbox("HTA", ["No", "Sí"])
            anos_hta = cA.number_input("Años HTA", 0, disabled=(hta=="No"))
            disli = cB.selectbox("Dislipidemia", ["No", "Sí"])
            diabetes = cB.selectbox("Diabetes", ["No", "Sí - IR", "Sí - NIR", "Sin Tx"])
            anos_dm = cB.number_input("Años con Diabetes", 0, disabled=(diabetes=="No"))
            tabaquismo = cA.selectbox("Tabaquismo", ["No", "Sí"])
            ant_qx = st.multiselect("Cirugías previas", ["Catarata", "Glaucoma", "Vitrectomía", "DMRE contralateral"])

        with tabs[2]: # TX & DX
            dx_p = st.text_input("Dx Principal")
            med_tx = st.selectbox("Medicamento", ["Aflibercept", "Ranibizumab", "Bevacizumab", "Faricimab"])
            dos_tx = st.text_input("Dosis", "0.05 ml")

        with tabs[3]: # VISIÓN
            col_od, col_oi = st.columns(2)
            s_od = col_od.selectbox("Snellen OD", list(SNELLEN_MAP.keys()), index=3)
            s_oi = col_oi.selectbox("Snellen OI", list(SNELLEN_MAP.keys()), index=3)
            log_od, log_oi = SNELLEN_MAP[s_od], SNELLEN_MAP[s_oi]
            v_cc = st.text_input("Cc (Con corrección)")
            v_ph = st.text_input("Ph (Pinhole)")

        with tabs[4]: # OCT
            fecha_oct = st.date_input("Fecha Toma OCT")
            foto_oct = st.file_uploader("📷 Imagen OCT AO", type=["jpg", "png", "jpeg"])
            ruta_img_local = None
            if foto_oct:
                st.image(foto_oct, width=300)
                ruta_img_local = os.path.join(CARPETA_IMG, f"oct_{id_paciente}_{datetime.now().strftime('%H%M%S')}.jpg")
                with open(ruta_img_local, "wb") as f:
                    f.write(foto_oct.getbuffer())

            cst_g = st.number_input("CST Grosor Macular (um)", 0)
            col_o1, col_o2 = st.columns(2)
            esp_od = col_o1.number_input("Espesor OD", 0)
            sqi_od = col_o1.number_input("SQI OD", 0.0)
            ssi_od = col_o1.number_input("SSI OD", 0.0)
            esp_oi = col_o2.number_input("Espesor OI", 0)
            sqi_oi = col_o2.number_input("SQI OI", 0.0)
            ssi_oi = col_o2.number_input("SSI OI", 0.0)

        with tabs[5]: # BIOMARCADORES
            st.subheader("Signos y Biomarcadores")
            col_b1, col_b2 = st.columns(2)
            b_atr = col_b1.checkbox("Atrofia")
            b_fib = col_b1.checkbox("Fibrosis")
            b_hem = col_b2.checkbox("Hemorragia")
            b_qui = col_b2.checkbox("Quistes")
            b_srf = col_b1.checkbox("SRF")
            b_irf = col_b2.checkbox("IRF")

        with tabs[6]: # VIDA / IMC / VF-14
            cp, ct = st.columns(2)
            peso_val = cp.number_input("Peso (kg)", 0.0)
            talla_val = ct.number_input("Talla (m)", 0.0)
            imc_val = round(peso_val/(talla_val**2), 2) if talla_val > 0 else 0.0
            st.metric("IMC", imc_val)
            
            preg = ["Leer letras pequeñas", "Leer periódico", "Titulares", "Reconocer personas", "subir Escalones", "Identificar Señales de transito", "Realizar Trabajos manuales", "Firmar Cheques", "Jugar Bingo", "Realizar Deportes", "Cocinar", "Ver TV", "Conducir día", "Conducir noche"]
            vf_res = []
            for p in preg:
                vf_res.append(st.radio(p, [0,1,2,3,4], horizontal=True, index=4, key=p))

        st.divider()
        if st.button("💾 GUARDAR TODO EN SUPABASE", type="primary", use_container_width=True):
            if not id_paciente: st.error("ID Obligatorio")
            else:
                d_alert = {'Atrofia': "Sí" if b_atr else "No", 'Fibrosis': "Sí" if b_fib else "No", 'AV_OD_LogMAR': log_od}
                msg, color = analizar_protocolo(d_alert, av_previa)
                
                if color == "rojo": st.error(msg)
                elif color == "naranja": st.warning(msg)
                else: st.success(msg)

                nuevo = {
                    "ID": id_paciente, "Filiacion": filiacion, "Medico": medico, "Momento": momento,
                    "Fecha_App": str(fecha_app), "Dx_Ppal": dx_p, "Medicamento": med_tx,
                    "AV_OD_LogMAR": log_od, "AV_OI_LogMAR": log_oi, "CST": cst_g,
                    "Espesor_OD": esp_od, "SQI_OD": sqi_od, "SSI_OD": ssi_od,
                    "Atrofia": "Sí" if b_atr else "No", "Fibrosis": "Sí" if b_fib else "No",
                    "IMC": imc_val, "VF14_Total": sum(vf_res), "Decision": msg, "Color_Alerta": color,
                    "Ruta_Imagen": ruta_img_local if foto_oct else ""
                }
                
                # Intentamos guardar con la nueva función de Supabase
                if guardar_datos(nuevo):
                    st.toast("✅ Registro guardado exitosamente en la Nube ☁️")
                    st.balloons()

    elif menu == "📊 Tablero & PDF":
        df = cargar_datos()
        if not df.empty:
            st.dataframe(df)
            sel_id = st.selectbox("Paciente para Reporte", df['ID'].unique())
            if st.button("📄 GENERAR PDF"):
                r_img = df[df['ID'].astype(str) == str(sel_id)].iloc[-1].get('Ruta_Imagen')
                pdf_b = generar_pdf(df[df['ID'].astype(str) == str(sel_id)], sel_id, r_img)
                st.download_button("📥 Descargar Reporte", pdf_b, f"Reporte_{sel_id}.pdf")
        else:
            st.info("Aún no hay datos en la base de datos de Supabase.")

    elif menu == "🤖 IA":
        df = cargar_datos()
        if not df.empty and len(df) > 1:
            x_ax = st.selectbox("X", ["CST", "IMC", "VF14_Total"])
            y_ax = st.selectbox("Y", ["AV_OD_LogMAR"])
            fig = px.scatter(df, x=x_ax, y=y_ax, trendline="ols")
            st.plotly_chart(fig)
        else:
            st.info("Se necesitan al menos 2 registros en Supabase para generar gráficos.")