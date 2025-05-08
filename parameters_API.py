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
from flask_cors import CORS  # Nueva importación para CORS
from werkzeug.utils import secure_filename

# 📌 Configuración de la base de datos
DB_HOST = "americastowersimulator.c14c80caytj6.us-east-1.rds.amazonaws.com"
DB_USER = "admin"
DB_PASSWORD = "Controlador2929"
DB_NAME = "simulador(unity-access)"

# Configuración de la aplicación
app = Flask(__name__)
CORS(app)  # Habilitar CORS para todas las rutas

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
            # Ya no intentamos crear la columna porque ya existe
            # Ahora simplemente insertamos los datos
            
            # Insertar los datos en la tabla
            cursor.execute("""
            INSERT INTO documentos_qr (
                id, nombre_original, nombre_original_sin_id, nombre_con_qr, s3_bucket, s3_key, 
                s3_url, tamano_archivo, qr_data, descripcion, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                datos["id"],
                datos["nombre_original"],         # Nombre con ID para sistema
                datos["nombre_original_sin_id"],  # Nombre original sin ID
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
    url_base = "https://menuidac.com/api/descargar/documento/"
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

def agregar_qr_a_oficio(oficio_data, qr_image_path, qr_data, qr_size=80, margin_x=100, margin_y=260):
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
        
        # Usar los parámetros recibidos para configurar tamaño y posición del QR
        
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

def procesar_archivos_pdf(carta_data, oficio_data, qr_size=80, margin_x=100, margin_y=260):
    """Procesa los dos archivos PDF recibidos"""
    app.logger.info(f"Procesando carta: {carta_data['nombre_original']}")
    app.logger.info(f"Procesando oficio: {oficio_data['nombre_original']}")
    app.logger.info(f"Parámetros QR: tamaño={qr_size}, margen-x={margin_x}, margen-y={margin_y}")
    
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
        ruta_oficio_con_qr = agregar_qr_a_oficio(oficio_data, qr_path, qr_data, qr_size, margin_x, margin_y)
        
        if not ruta_oficio_con_qr:
            return {
                "error": "Error al agregar QR al oficio",
                "success": False
            }
        
        # 5. Preparar datos para la base de datos
        nombre_sin_extension = os.path.splitext(oficio_data['nombre_original'])[0]
        
        # Guardar el nombre original sin ID para uso posterior
        nombre_oficio_sin_id = oficio_data['nombre_original']
        nombre_carta_sin_id = carta_data['nombre_original']
        
        datos_bd = {
            "id": carta_data["id"],
            "nombre_original": nombre_con_id,  # Guardar con el nombre que incluye ID
            "nombre_original_sin_id": carta_data["nombre_original"],  # Nombre original sin ID
            "nombre_con_qr": f"{carta_data['id']}_{nombre_sin_extension}_con_QR.pdf",
            "s3_key": f"cartas/{carta_data['id']}/{nombre_con_id}",
            "s3_url": f"https://menuidac.com/api/descargar/documento/{carta_data['id']}",
            "tamano_bytes": carta_data["tamano_bytes"],
            "qr_data": qr_data,
            "descripcion": f"Carta de estado para oficio: {oficio_data['nombre_original']}",
            "metadata": {
                "oficio_relacionado": oficio_data['nombre_original'],
                "oficio_relacionado_sin_id": nombre_oficio_sin_id,
                "ruta_oficio_con_qr": ruta_oficio_con_qr,
                "fecha_procesamiento": datetime.datetime.now().isoformat(),
                "configuracion_qr": {
                    "tamano": qr_size,
                    "margen_x": margin_x,
                    "margen_y": margin_y
                }
            }
        }
        
        # 6. Guardar en base de datos
        bd_resultado = guardar_datos_bd(datos_bd)
        
        if bd_resultado:
            app.logger.info("Ambos archivos procesados y datos guardados correctamente")
            return {
                "carta_guardada": ruta_copia_carta,
                "oficio_con_qr": ruta_oficio_con_qr,
                "oficio_con_qr_url": f"/api/descargar/{os.path.basename(ruta_oficio_con_qr)}",
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
        
        # Obtener parámetros del QR (usando valores predeterminados si no se proporcionan)
        qr_size = int(request.form.get('qr_size', 80))
        margin_x = int(request.form.get('margin_x', 100))
        margin_y = int(request.form.get('margin_y', 260))
        
        # Validar los rangos
        qr_size = max(40, min(150, qr_size))  # Entre 40 y 150
        margin_x = max(50, min(300, margin_x))  # Entre 50 y 300
        margin_y = max(50, min(400, margin_y))  # Entre 50 y 400
        
        # Registrar los parámetros recibidos
        app.logger.info(f"Parámetros QR recibidos: tamaño={qr_size}, margen-x={margin_x}, margen-y={margin_y}")
        
        # Extraer datos de la carta de estado
        carta_data = extraer_datos_carta_estado(archivo_carta)
        
        # Extraer datos del oficio
        oficio_data = {
            "nombre_original": secure_filename(archivo_oficio.filename),
            "pdf_data": archivo_oficio.read()
        }
        
        # Procesar los archivos con los parámetros del QR
        resultado = procesar_archivos_pdf(carta_data, oficio_data, qr_size, margin_x, margin_y)
        
        if resultado.get("success", False):
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
        # Asegurar que el nombre del archivo es seguro
        nombre_seguro = secure_filename(nombre_archivo)
        ruta_archivo = os.path.join(app.config['OUTPUT_FOLDER'], nombre_seguro)
        
        if not os.path.exists(ruta_archivo):
            app.logger.error(f"Archivo no encontrado: {ruta_archivo}")
            return jsonify({"error": "Archivo no encontrado", "success": False}), 404
        
        # Extraer el ID del nombre del archivo (si existe)
        partes = nombre_seguro.split('_', 1)
        if len(partes) > 1:
            id_documento = partes[0]
            
            # Intentar obtener el nombre original de la base de datos
            conexion = conectar_bd()
            if conexion:
                with conexion.cursor() as cursor:
                    cursor.execute("""
                    SELECT nombre_original_sin_id, metadata 
                    FROM documentos_qr WHERE id = %s
                    """, (id_documento,))
                    resultado = cursor.fetchone()
                    conexion.close()
                    
                    if resultado:
                        # Determinar si es un oficio con QR o una carta
                        if "_con_QR.pdf" in nombre_seguro:
                            # Es un oficio con QR
                            # Extraer del metadata
                            metadata = json.loads(resultado['metadata']) if resultado['metadata'] else {}
                            oficio_original = metadata.get('oficio_relacionado_sin_id', None)
                            if oficio_original:
                                nombre_mostrar = f"{os.path.splitext(oficio_original)[0]}_con_QR.pdf"
                            else:
                                # Fallback: usar el nombre original pero quitar el ID
                                nombre_mostrar = nombre_seguro.split('_', 1)[1] if '_' in nombre_seguro else nombre_seguro
                        else:
                            # Es una carta
                            nombre_mostrar = resultado['nombre_original_sin_id'] if resultado['nombre_original_sin_id'] else nombre_seguro.split('_', 1)[1]
                    else:
                        # No se encontró en la base de datos, usar el nombre sin el ID
                        nombre_mostrar = nombre_seguro.split('_', 1)[1] if '_' in nombre_seguro else nombre_seguro
            else:
                # No se pudo conectar a la BD, usar el nombre sin el ID
                nombre_mostrar = nombre_seguro.split('_', 1)[1] if '_' in nombre_seguro else nombre_seguro
        else:
            # No tiene formato con ID, usar el nombre tal cual
            nombre_mostrar = nombre_seguro
            
        app.logger.info(f"Enviando archivo: {ruta_archivo} con nombre: {nombre_mostrar}")
        return send_file(ruta_archivo, as_attachment=True, download_name=nombre_mostrar)
        
    except Exception as e:
        app.logger.error(f"Error al descargar archivo: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 500

# Endpoint para descargar por ID del documento
@app.route('/api/descargar/documento/<documento_id>', methods=['GET'])
def descargar_por_id(documento_id):
    """Permite descargar un documento por su ID"""
    try:
        app.logger.info(f"Buscando documento con ID: {documento_id}")
        
        # Primero intentar obtener información de la base de datos
        conexion = conectar_bd()
        nombre_mostrar = None
        
        if conexion:
            with conexion.cursor() as cursor:
                cursor.execute("""
                SELECT nombre_original, nombre_original_sin_id, nombre_con_qr, metadata 
                FROM documentos_qr WHERE id = %s
                """, (documento_id,))
                resultado = cursor.fetchone()
                conexion.close()
                
                if resultado:
                    # Para la descarga por ID, por defecto damos el oficio con QR (más útil)
                    nombre_bd = resultado['nombre_con_qr']
                    
                    # Extraer del metadata
                    metadata = json.loads(resultado['metadata']) if resultado['metadata'] else {}
                    oficio_original = metadata.get('oficio_relacionado_sin_id', None)
                    if oficio_original:
                        nombre_mostrar = f"{os.path.splitext(oficio_original)[0]}_con_QR.pdf"
                    else:
                        # Fallback: usar el nombre pero intentar quitar el ID
                        partes = nombre_bd.split('_', 1)
                        nombre_mostrar = partes[1] if len(partes) > 1 else nombre_bd
        
        # Buscar el archivo en el sistema
        directorio = app.config['OUTPUT_FOLDER']
        archivos = os.listdir(directorio)
        archivos_coincidentes = [archivo for archivo in archivos if documento_id in archivo and "_con_QR.pdf" in archivo]
        
        # Si no hay oficio con QR, buscar cualquier archivo con el ID
        if not archivos_coincidentes:
            archivos_coincidentes = [archivo for archivo in archivos if documento_id in archivo]
        
        if not archivos_coincidentes:
            app.logger.error(f"No se encontró ningún archivo con el ID: {documento_id}")
            return jsonify({"error": "Archivo no encontrado", "success": False}), 404
        
        # Usar el primer archivo que coincida
        archivo_encontrado = archivos_coincidentes[0]
        ruta_completa = os.path.join(directorio, archivo_encontrado)
        
        # Si no tenemos un nombre para mostrar, extraer del nombre del archivo
        if not nombre_mostrar:
            partes = archivo_encontrado.split('_', 1)
            nombre_mostrar = partes[1] if len(partes) > 1 else archivo_encontrado
        
        app.logger.info(f"Enviando archivo: {ruta_completa} con nombre: {nombre_mostrar}")
        return send_file(ruta_completa, as_attachment=True, download_name=nombre_mostrar)
        
    except Exception as e:
        app.logger.error(f"Error al buscar documento por ID: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 500

if __name__ == '__main__':
    # Configurar logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Puerto donde se ejecutará la API
    puerto = 5000
    
    print(f"Iniciando API en http://0.0.0.0:{puerto}")
    print("Endpoints disponibles:")
    print(f"  - GET https://menuidac.com/api/health - Verificar si la API está funcionando")
    print(f"  - POST https://menuidac.com/api/procesar - Procesar los archivos PDF")
    print(f"  - GET https://menuidac.com/api/descargar/<nombre_archivo> - Descargar por nombre")
    print(f"  - GET https://menuidac.com/api/descargar/documento/<documento_id> - Descargar por ID")
    
    # Usar waitress para producción
    from waitress import serve
    serve(app, host='0.0.0.0', port=puerto, threads=4)