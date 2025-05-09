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
from PIL import Image  # Para convertir la imagen del QR a JPG

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
    
    # Guardar la imagen QR en un archivo temporal PNG
    temp_qr_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
    qr_img.save(temp_qr_file.name)
    temp_qr_file.close()
    
    # También guardar como JPG para descarga separada
    nombre_jpg = f"{datos['id']}_qr_code.jpg"
    ruta_jpg = os.path.join(app.config['OUTPUT_FOLDER'], nombre_jpg)
    
    # Convertir a JPG usando PIL
    img = Image.open(temp_qr_file.name)
    img = img.convert('RGB')  # Convertir a RGB ya que JPG no soporta transparencia
    img.save(ruta_jpg, "JPEG", quality=95)
    
    app.logger.info(f"QR generado con información del documento {datos['id']} y guardado como JPG en {ruta_jpg}")
    
    return temp_qr_file.name, qr_data, ruta_jpg

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
        
        # Usar los parámetros enviados para configurar el QR
        app.logger.info(f"Usando parámetros personalizados: qr_size={qr_size}, margin_x={margin_x}, margin_y={margin_y}")
        
        # Dibujar el QR con los valores de los parámetros
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

def procesar_archivos_pdf(carta_data, oficio_data, qr_separado=False, qr_size=80, margin_x=100, margin_y=260):
    """Procesa los dos archivos PDF recibidos"""
    app.logger.info(f"Procesando carta: {carta_data['nombre_original']}")
    app.logger.info(f"Procesando oficio: {oficio_data['nombre_original']}")
    app.logger.info(f"QR separado solicitado: {qr_separado}")
    app.logger.info(f"Parámetros QR: tamaño={qr_size}, margen_x={margin_x}, margen_y={margin_y}")
    
    try:
        # 1. Extraer información de la carta de estado
        # Los datos ya vienen extraídos, así que no es necesario hacerlo de nuevo
        
        # 2. Generar QR con la información relevante (ahora con ruta_jpg)
        qr_path, qr_data, qr_jpg_path = generar_qr_con_datos(carta_data)
        
        # 3. Guardar una copia local de la carta de estado (incluir ID en el nombre)
        nombre_con_id = f"{carta_data['id']}_{carta_data['nombre_original']}"
        ruta_copia_carta = os.path.join(app.config['OUTPUT_FOLDER'], nombre_con_id)
        
        with open(ruta_copia_carta, 'wb') as f:
            f.write(carta_data['pdf_data'])
        app.logger.info(f"Carta guardada en: {ruta_copia_carta}")
        
        # 4. Añadir el QR al oficio - ahora pasamos los parámetros de tamaño y posición
        ruta_oficio_con_qr = agregar_qr_a_oficio(oficio_data, qr_path, qr_data, qr_size, margin_x, margin_y)
        
        if not ruta_oficio_con_qr:
            return {
                "error": "Error al agregar QR al oficio",
                "success": False
            }
        
        # 5. Preparar datos para la base de datos
        nombre_sin_extension = os.path.splitext(oficio_data['nombre_original'])[0]
        
        # Nombre base del QR para URLs
        nombre_qr_jpg = os.path.basename(qr_jpg_path)
        
        datos_bd = {
            "id": carta_data["id"],
            "nombre_original": carta_data['nombre_original'],  # Guardar nombre original sin ID
            "nombre_con_qr": oficio_data['nombre_original'],   # Guardar nombre original sin ID
            "s3_key": f"cartas/{carta_data['id']}/{nombre_con_id}",
            "s3_url": f"https://menuidac.com/api/descargar/documento/{carta_data['id']}",
            "tamano_bytes": carta_data["tamano_bytes"],
            "qr_data": qr_data,
            "descripcion": f"Carta de estado para oficio: {oficio_data['nombre_original']}",
            "metadata": {
                "ruta_carta": ruta_copia_carta,
                "nombre_interno_carta": nombre_con_id,
                "oficio_relacionado": oficio_data['nombre_original'],
                "ruta_oficio_con_qr": ruta_oficio_con_qr,
                "nombre_interno_oficio": f"{carta_data['id']}_{nombre_sin_extension}_con_QR.pdf",
                "ruta_qr_jpg": qr_jpg_path if qr_separado else None,
                "fecha_procesamiento": datetime.datetime.now().isoformat(),
                "parametros_qr": {
                    "qr_size": qr_size,
                    "margin_x": margin_x,
                    "margin_y": margin_y
                }
            }
        }
        
        # 6. Guardar en base de datos
        bd_resultado = guardar_datos_bd(datos_bd)
        
        if bd_resultado:
            app.logger.info("Ambos archivos procesados y datos guardados correctamente")
            
            resultado = {
                "carta_guardada": ruta_copia_carta,
                "oficio_con_qr": ruta_oficio_con_qr,
                "id_documento": carta_data["id"],
                "success": True
            }
            
            # Añadir información del QR JPG si se solicitó
            if qr_separado:
                resultado["qr_jpg_path"] = qr_jpg_path
                resultado["qr_jpg_url"] = f"/api/descargar/qr/{carta_data['id']}"
            
            return resultado
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
        
        # Obtener parámetro para generar QR separado (checkbox)
        qr_separado = request.form.get('qr_separado', 'false').lower() == 'true'
        
        # NUEVO: Obtener los parámetros de los sliders enviados desde Unity
        # Si no se envían, usar valores predeterminados
        try:
            qr_size = int(request.form.get('qr_size', '80'))
            margin_x = int(request.form.get('margin_x', '100'))
            margin_y = int(request.form.get('margin_y', '260'))
            
            # Registrar en el log los valores recibidos
            app.logger.info(f"Parámetros recibidos de Unity: qr_size={qr_size}, margin_x={margin_x}, margin_y={margin_y}")
            
        except ValueError as e:
            app.logger.error(f"Error al convertir los parámetros de los sliders: {e}")
            # Si hay error en la conversión, usar valores predeterminados
            qr_size = 80
            margin_x = 100
            margin_y = 260
            app.logger.info(f"Usando valores predeterminados: qr_size={qr_size}, margin_x={margin_x}, margin_y={margin_y}")
        
        # Extraer datos de la carta de estado
        carta_data = extraer_datos_carta_estado(archivo_carta)
        
        # Extraer datos del oficio
        oficio_data = {
            "nombre_original": secure_filename(archivo_oficio.filename),
            "pdf_data": archivo_oficio.read()
        }
        
        # Procesar los archivos con los nuevos parámetros
        resultado = procesar_archivos_pdf(carta_data, oficio_data, qr_separado, qr_size, margin_x, margin_y)
        
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

# Función para obtener el nombre original de un documento
def obtener_nombre_original(id_documento, nombre_archivo_completo=""):
    """Obtiene el nombre original del documento desde la base de datos"""
    conexion = conectar_bd()
    if not conexion:
        app.logger.warning(f"No se pudo conectar a la BD para obtener el nombre original")
        return nombre_archivo_completo
    
    try:
        with conexion.cursor() as cursor:
            # Consultar los datos del documento
            cursor.execute("SELECT nombre_original, nombre_con_qr, metadata FROM documentos_qr WHERE id = %s", (id_documento,))
            documento = cursor.fetchone()
            
            if documento:
                # Si el nombre de archivo está vacío, siempre devolver el de la carta
                if not nombre_archivo_completo:
                    return documento["nombre_original"]  # Nombre original de la carta
                    
                # Determinar si estamos buscando la carta o el oficio con QR
                if "_con_QR.pdf" in nombre_archivo_completo:
                    return documento["nombre_con_qr"]  # Nombre original del oficio
                else:
                    return documento["nombre_original"]  # Nombre original de la carta
            
            app.logger.warning(f"No se encontró el documento con ID {id_documento} en la base de datos")
    
    except pymysql.MySQLError as e:
        app.logger.error(f"Error al consultar la base de datos: {e}")
    finally:
        conexion.close()
    
    # Si hay algún problema y tenemos un nombre de archivo, intentar extraer el nombre
    if nombre_archivo_completo:
        partes = nombre_archivo_completo.split('_', 1)
        if len(partes) > 1:
            return partes[1]  # Retorna el nombre sin el ID
    
    return nombre_archivo_completo

# Endpoint para descargar archivos procesados por nombre (internamente con ID)
@app.route('/api/descargar/<nombre_archivo>', methods=['GET'])
def descargar_archivo(nombre_archivo):
    """Permite descargar un archivo procesado por su nombre (interno con ID)"""
    try:
        ruta_archivo = os.path.join(app.config['OUTPUT_FOLDER'], secure_filename(nombre_archivo))
        
        if not os.path.exists(ruta_archivo):
            app.logger.error(f"Archivo no encontrado: {ruta_archivo}")
            return jsonify({"error": "Archivo no encontrado", "success": False}), 404
            
        # Extraer el ID del nombre del archivo
        partes = nombre_archivo.split('_', 1)  # Separar el ID del resto del nombre
        if len(partes) > 1:
            id_documento = partes[0]
            
            # Buscar en la base de datos el nombre original
            nombre_descarga = obtener_nombre_original(id_documento, nombre_archivo)
            
            # Enviar el archivo con el nombre original
            return send_file(ruta_archivo, as_attachment=True, download_name=nombre_descarga)
        
        # Si no se pudo extraer un ID, usar el nombre tal cual
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
            archivos_coincidentes = [archivo for archivo in archivos if documento_id in archivo and archivo.endswith('.pdf')]
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
            
            # Obtener el nombre original del documento
            nombre_descarga = obtener_nombre_original(documento_id, archivo_encontrado)
            
            # Devolver el archivo con el nombre original
            return send_file(ruta_completa, as_attachment=True, download_name=nombre_descarga)
            
        except Exception as e:
            app.logger.error(f"Error al buscar en el directorio: {str(e)}")
            return jsonify({"error": f"Error al buscar en el directorio: {str(e)}", "success": False}), 500
        
    except Exception as e:
        app.logger.error(f"Error al buscar documento por ID: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 500

# Endpoint para descargar sólo el QR como imagen
@app.route('/api/descargar/qr/<documento_id>', methods=['GET'])
def descargar_qr_imagen(documento_id):
    """Permite descargar la imagen del QR por el ID del documento"""
    try:
        app.logger.info(f"Buscando imagen QR con ID: {documento_id}")
        
        # Buscar la imagen QR en el directorio configurado
        nombre_qr = f"{documento_id}_qr_code.jpg"
        ruta_qr = os.path.join(app.config['OUTPUT_FOLDER'], nombre_qr)
        
        if not os.path.exists(ruta_qr):
            app.logger.error(f"Imagen QR no encontrada: {ruta_qr}")
            
            # Buscar alternativas si existe el ID pero no el archivo específico
            directorio = app.config['OUTPUT_FOLDER']
            archivos_coincidentes = [archivo for archivo in os.listdir(directorio) 
                                 if documento_id in archivo and archivo.endswith(('.jpg', '.jpeg', '.png'))]
            
            if archivos_coincidentes:
                # Usar el primer archivo QR encontrado
                ruta_qr = os.path.join(directorio, archivos_coincidentes[0])
                app.logger.info(f"Se encontró imagen QR alternativa: {ruta_qr}")
            else:
                return jsonify({"error": "Imagen QR no encontrada", "success": False}), 404
        
        # Obtener el nombre de la carta de estado de la base de datos
        nombre_carta = obtener_nombre_original(documento_id, "")  # El segundo parámetro está vacío ya que solo nos interesa la carta
        if nombre_carta:
            # Extraer el nombre base sin extensión y añadir sufijo QR
            nombre_base, extension = os.path.splitext(nombre_carta)
            nombre_descarga = f"{nombre_base}_QR.jpg"
        else:
            # Fallback a los primeros 5 caracteres del ID si no se encuentra el nombre
            nombre_descarga = f"{documento_id[:5]}_QR.jpg"
        
        return send_file(ruta_qr, mimetype='image/jpeg', as_attachment=True, 
                        download_name=nombre_descarga)
        
    except Exception as e:
        app.logger.error(f"Error al descargar imagen QR: {str(e)}")
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
    print(f"  - GET https://menuidac.com/api/descargar/qr/<documento_id> - Descargar solo el QR como imagen")
    
    # Usar waitress para producción
    from waitress import serve
    serve(app, host='0.0.0.0', port=puerto, threads=4)