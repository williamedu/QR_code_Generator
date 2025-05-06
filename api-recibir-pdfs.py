import os
import sys
import uuid
import datetime
import json
import tempfile
import shutil
from io import BytesIO
import pymysql
import qrcode
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

# Importaciones para la API REST
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename

# 📌 Configuración de la base de datos
DB_HOST = "americastowersimulator.c14c80caytj6.us-east-1.rds.amazonaws.com"
DB_USER = "admin"
DB_PASSWORD = "Controlador2929"
DB_NAME = "simulador(unity-access)"

# Configuración de la aplicación
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()  # Carpeta temporal para archivos subidos
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limitar tamaño de archivos a 16MB
app.config['OUTPUT_FOLDER'] = r"C:\Users\Administrator\Desktop\QR_code_Generator\documentos_procesados"  # Ruta específica

# Crear carpeta de salida si no existe
if not os.path.exists(app.config['OUTPUT_FOLDER']):
    os.makedirs(app.config['OUTPUT_FOLDER'])

# 📌 Función para conectar con la base de datos
def conectar_bd():
    try:
        conexion = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor
        )
        return conexion
    except pymysql.MySQLError as e:
        app.logger.error(f"Error al conectar con la base de datos: {e}")
        return None

def guardar_datos_bd(datos):
    """Guarda los datos en la base de datos"""
    conexion = conectar_bd()
    if not conexion:
        app.logger.error("No se pudo establecer conexión con la base de datos")
        return False
    
    try:
        with conexion.cursor() as cursor:
            # Insertar los datos en la tabla
            cursor.execute("""
            INSERT INTO documentos_qr (
                id, nombre_original, nombre_con_qr, s3_bucket, s3_key, 
                s3_url, tamano_archivo, qr_data, descripcion, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                datos["id"],
                datos["nombre_original"],
                datos["nombre_con_qr"],
                "docs-qr-bucket",  # Nombre del bucket (simulado por ahora)
                datos["s3_key"],
                datos["s3_url"],
                datos["tamano_bytes"],
                json.dumps(datos["qr_data"]),
                datos["descripcion"],
                json.dumps(datos["metadata"])
            ))
            
            conexion.commit()
            app.logger.info(f"Registro con ID {datos['id']} guardado exitosamente")
            return True
    except pymysql.MySQLError as e:
        app.logger.error(f"Error al insertar en la base de datos: {e}")
        return False
    finally:
        conexion.close()

def extraer_datos_carta_estado(archivo_pdf):
    """Extrae información relevante de la carta de estado"""
    # Generar un UUID para el documento
    documento_id = str(uuid.uuid4())
    
    # Obtener el nombre del archivo
    nombre_original = secure_filename(archivo_pdf.filename)
    
    # Leer información básica del PDF
    pdf_data = archivo_pdf.read()
    archivo_pdf.seek(0)  # Resetear el puntero para usos futuros
    
    # Crear un objeto BytesIO para leer el PDF
    pdf_bytes = BytesIO(pdf_data)
    pdf_reader = PdfReader(pdf_bytes)
    
    # Datos extraídos
    datos = {
        "id": documento_id,
        "nombre_original": nombre_original,
        "fecha_creacion": datetime.datetime.now().isoformat(),
        "tipo_documento": "Carta de Estado",
        "tamano_bytes": len(pdf_data),
        "paginas": len(pdf_reader.pages),
        "pdf_data": pdf_data  # Guardar los datos binarios para uso posterior
    }
    
    app.logger.info(f"Datos extraídos con ID generado {documento_id}")
    return datos

def generar_qr_con_datos(datos):
    """Genera un código QR con la información de la carta de estado"""
    # Crear la URL que iría en el QR con la IP y puerto del servidor
    url_base = "http://44.201.81.192:5000/api/descargar/documento/"
    url_documento = f"{url_base}{datos['id']}"
    
    # Crear datos para el QR
    qr_data = {
        "url": url_documento,
        "id": datos["id"],
        "tipo": datos["tipo_documento"],
        "nombre": datos["nombre_original"],
        "fecha": datos["fecha_creacion"]
    }
    
    # Convertir a JSON
    qr_json = json.dumps(qr_data)
    
    # Generar el código QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    
    # Añadir los datos al QR
    qr.add_data(qr_json)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Guardar la imagen QR en un archivo temporal
    temp_qr_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    qr_img.save(temp_qr_file.name)
    temp_qr_file.close()
    
    app.logger.info(f"QR generado con información del documento {datos['id']}")
    return temp_qr_file.name, qr_data

def agregar_qr_a_oficio(oficio_data, qr_image_path, qr_data):
    """Agrega un código QR al oficio y retorna el nuevo PDF"""
    # Nombre para el archivo resultante
    nombre_original = oficio_data["nombre_original"]
    nombre_sin_extension = os.path.splitext(nombre_original)[0]
    nombre_salida = f"{qr_data['id']}_{nombre_sin_extension}_con_QR.pdf"
    ruta_salida = os.path.join(app.config['OUTPUT_FOLDER'], nombre_salida)
    
    try:
        # Crear un objeto BytesIO para leer el PDF
        pdf_bytes = BytesIO(oficio_data["pdf_data"])
        pdf_reader = PdfReader(pdf_bytes)
        
        # Obtener dimensiones de la primera página
        first_page = pdf_reader.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)
        
        # Crear un PDF temporal con el código QR
        qr_buffer = BytesIO()
        qr_pdf = canvas.Canvas(qr_buffer, pagesize=(page_width, page_height))
        
        # Configurar tamaño y posición del QR
        qr_size = 80  # Tamaño del QR
        margin_x = 50  # Margen desde la derecha
        margin_y = 50  # Margen desde abajo
        
        # Dibujar el QR
        qr_pdf.drawImage(
            qr_image_path, 
            page_width - qr_size - margin_x,
            margin_y,
            width=qr_size, 
            height=qr_size
        )
        
        # Añadir información textual sobre el QR
        qr_pdf.setFont("Helvetica", 7)
        qr_pdf.drawString(
            page_width - qr_size - margin_x, 
            margin_y - 10, 
            f"ID: {qr_data['id'][:8]}..."
        )
        
        qr_pdf.save()
        
        # Combinar el PDF original con el PDF del QR
        qr_buffer.seek(0)
        qr_reader = PdfReader(qr_buffer)
        
        # Crear el PDF de salida
        pdf_writer = PdfWriter()
        
        # Combinar cada página
        for i in range(len(pdf_reader.pages)):
            # Obtener la página original
            page = pdf_reader.pages[i]
            
            # Si es la primera página, combinar con el QR
            if i == 0:
                page.merge_page(qr_reader.pages[0])
            
            # Añadir al PDF de salida
            pdf_writer.add_page(page)
        
        # Guardar el PDF resultante
        with open(ruta_salida, "wb") as output_file:
            pdf_writer.write(output_file)
        
        # Eliminar el archivo temporal del QR
        os.unlink(qr_image_path)
        
        app.logger.info(f"Oficio con QR guardado en {ruta_salida}")
        return ruta_salida
        
    except Exception as e:
        app.logger.error(f"Error al agregar QR: {str(e)}")
        # Limpiar
        if os.path.exists(qr_image_path):
            os.unlink(qr_image_path)
        return None

def procesar_archivos_pdf(carta_data, oficio_data):
    """Procesa los dos archivos PDF recibidos"""
    app.logger.info(f"Procesando carta: {carta_data['nombre_original']}")
    app.logger.info(f"Procesando oficio: {oficio_data['nombre_original']}")
    
    try:
        # 1. Extraer información de la carta de estado
        # Los datos ya vienen extraídos, así que no es necesario hacerlo de nuevo
        
        # 2. Generar QR con la información relevante
        qr_path, qr_data = generar_qr_con_datos(carta_data)
        
        # 3. Guardar una copia local de la carta de estado (incluir ID en el nombre)
        nombre_con_id = f"{carta_data['id']}_{carta_data['nombre_original']}"
        ruta_copia_carta = os.path.join(app.config['OUTPUT_FOLDER'], nombre_con_id)
        
        with open(ruta_copia_carta, 'wb') as f:
            f.write(carta_data['pdf_data'])
        app.logger.info(f"Carta guardada en: {ruta_copia_carta}")
        
        # 4. Añadir el QR al oficio
        ruta_oficio_con_qr = agregar_qr_a_oficio(oficio_data, qr_path, qr_data)
        
        if not ruta_oficio_con_qr:
            return {
                "error": "Error al agregar QR al oficio",
                "success": False
            }
        
        # 5. Preparar datos para la base de datos
        nombre_sin_extension = os.path.splitext(oficio_data['nombre_original'])[0]
        
        datos_bd = {
            "id": carta_data["id"],
            "nombre_original": nombre_con_id,  # Guardar con el nombre que incluye ID
            "nombre_con_qr": f"{carta_data['id']}_{nombre_sin_extension}_con_QR.pdf",
            "s3_key": f"cartas/{carta_data['id']}/{nombre_con_id}",
            "s3_url": f"http://44.201.81.192:5000/api/descargar/documento/{carta_data['id']}",
            "tamano_bytes": carta_data["tamano_bytes"],
            "qr_data": qr_data,
            "descripcion": f"Carta de estado para oficio: {oficio_data['nombre_original']}",
            "metadata": {
                "oficio_relacionado": oficio_data['nombre_original'],
                "ruta_oficio_con_qr": ruta_oficio_con_qr,
                "fecha_procesamiento": datetime.datetime.now().isoformat()
            }
        }
        
        # 6. Guardar en base de datos
        bd_resultado = guardar_datos_bd(datos_bd)
        
        if bd_resultado:
            app.logger.info("Ambos archivos procesados y datos guardados correctamente")
            return {
                "carta_guardada": ruta_copia_carta,
                "oficio_con_qr": ruta_oficio_con_qr,
                "id_documento": carta_data["id"],
                "success": True
            }
        else:
            app.logger.error("No se pudieron guardar los datos en la base de datos")
            return {
                "error": "Error al guardar en la base de datos",
                "success": False
            }
            
    except Exception as e:
        app.logger.error(f"Error en el procesamiento: {str(e)}")
        return {
            "error": str(e),
            "success": False
        }

# Ruta de verificación de salud
@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint para verificar que la API está funcionando"""
    return jsonify({"status": "ok", "message": "API funcionando correctamente"})

# Endpoint para procesar los PDFs
@app.route('/api/procesar', methods=['POST'])
def procesar_pdfs():
    """Endpoint para recibir y procesar dos archivos PDF"""
    try:
        # Verificar que se hayan enviado los dos archivos
        if 'carta' not in request.files or 'oficio' not in request.files:
            return jsonify({"error": "Se requieren ambos archivos: 'carta' y 'oficio'", "success": False}), 400
        
        archivo_carta = request.files['carta']
        archivo_oficio = request.files['oficio']
        
        # Verificar que los archivos tengan nombres
        if archivo_carta.filename == '' or archivo_oficio.filename == '':
            return jsonify({"error": "Ambos archivos deben tener un nombre", "success": False}), 400
        
        # Verificar que los archivos sean PDFs
        if not archivo_carta.filename.lower().endswith('.pdf') or not archivo_oficio.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Ambos archivos deben ser PDFs", "success": False}), 400
        
        # Extraer datos de la carta de estado
        carta_data = extraer_datos_carta_estado(archivo_carta)
        
        # Extraer datos del oficio
        oficio_data = {
            "nombre_original": secure_filename(archivo_oficio.filename),
            "pdf_data": archivo_oficio.read()
        }
        
        # Procesar los archivos
        resultado = procesar_archivos_pdf(carta_data, oficio_data)
        
        if resultado.get("success", False):
            # Para el caso de éxito, ofrecer también la descarga del oficio con QR
            oficio_con_qr = resultado.get("oficio_con_qr")
            
            # Reemplazar rutas locales con URLs relativas para la API
            nombre_oficio_qr = os.path.basename(oficio_con_qr)
            resultado["oficio_con_qr_url"] = f"/api/descargar/{nombre_oficio_qr}"
            
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 500
            
    except Exception as e:
        app.logger.error(f"Error en el endpoint: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 500

# Endpoint para descargar archivos procesados por nombre
@app.route('/api/descargar/<nombre_archivo>', methods=['GET'])
def descargar_archivo(nombre_archivo):
    """Permite descargar un archivo procesado por su nombre"""
    try:
        ruta_archivo = os.path.join(app.config['OUTPUT_FOLDER'], secure_filename(nombre_archivo))
        
        if not os.path.exists(ruta_archivo):
            app.logger.error(f"Archivo no encontrado: {ruta_archivo}")
            return jsonify({"error": "Archivo no encontrado", "success": False}), 404
            
        return send_file(ruta_archivo, as_attachment=True)
        
    except Exception as e:
        app.logger.error(f"Error al descargar archivo: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 500

# Endpoint para descargar por ID del documento
@app.route('/api/descargar/documento/<documento_id>', methods=['GET'])
def descargar_por_id(documento_id):
    """Permite descargar un documento por su ID"""
    try:
        app.logger.info(f"Buscando documento con ID: {documento_id}")
        
        # Buscar en el directorio configurado cualquier archivo que contenga el ID
        directorio = app.config['OUTPUT_FOLDER']
        
        try:
            # Listar todos los archivos en el directorio
            archivos = os.listdir(directorio)
            app.logger.info(f"Total de archivos en el directorio: {len(archivos)}")
            
            # Filtrar archivos que contengan el ID
            archivos_coincidentes = [archivo for archivo in archivos if documento_id in archivo]
            app.logger.info(f"Archivos que coinciden con el ID {documento_id}: {archivos_coincidentes}")
            
            if not archivos_coincidentes:
                app.logger.error(f"No se encontró ningún archivo con el ID: {documento_id}")
                return jsonify({"error": "Archivo no encontrado", "success": False}), 404
            
            # Usar el primer archivo que coincida
            archivo_encontrado = archivos_coincidentes[0]
            ruta_completa = os.path.join(directorio, archivo_encontrado)
            
            app.logger.info(f"Archivo encontrado: {ruta_completa}")
            
            # Verificar si el archivo existe
            if not os.path.exists(ruta_completa):
                app.logger.error(f"El archivo coincidente no existe: {ruta_completa}")
                return jsonify({"error": "Archivo existe en lista pero no en sistema", "success": False}), 404
            
            # Devolver el archivo
            return send_file(ruta_completa, as_attachment=True)
            
        except Exception as e:
            app.logger.error(f"Error al buscar en el directorio: {str(e)}")
            return jsonify({"error": f"Error al buscar en el directorio: {str(e)}", "success": False}), 500
        
    except Exception as e:
        app.logger.error(f"Error al buscar documento por ID: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 500

if __name__ == '__main__':
    # Configurar logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Puerto donde se ejecutará la API
    puerto = 5000
    
    print(f"Iniciando API en http://44.201.81.192:{puerto}")
    print("Endpoints disponibles:")
    print(f"  - GET http://44.201.81.192:{puerto}/api/health - Verificar si la API está funcionando")
    print(f"  - POST http://44.201.81.192:{puerto}/api/procesar - Procesar los archivos PDF")
    print(f"  - GET http://44.201.81.192:{puerto}/api/descargar/<nombre_archivo> - Descargar por nombre")
    print(f"  - GET http://44.201.81.192:{puerto}/api/descargar/documento/<documento_id> - Descargar por ID")
    
    # Usar waitress para producción
    from waitress import serve
    serve(app, host='0.0.0.0', port=puerto, threads=4)