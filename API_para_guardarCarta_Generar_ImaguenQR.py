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
from PyPDF2 import PdfReader
from PIL import Image  # Para convertir la imagen del QR

# Importaciones para la API REST
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
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
                datos["nombre_original"],  # Ya no hay un segundo documento, usamos el mismo nombre
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

# Cambios en la función generar_qr_con_datos para guardar siempre el ID en el nombre del archivo
# Modificación de la función generar_qr_con_datos para eliminar el sufijo _QR
def generar_qr_con_datos(datos, nombre_personalizado=None):
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
    
    # Guardar una versión personalizada - sin el sufijo _QR
    if nombre_personalizado:
        nombre_personalizado_qr = f"{nombre_personalizado}.png"
        ruta_personalizada = os.path.join(app.config['OUTPUT_FOLDER'], nombre_personalizado_qr)
        qr_img.save(ruta_personalizada)
        app.logger.info(f"QR guardado con nombre personalizado en {ruta_personalizada}")
    
    # Siempre guardar una versión con el ID para poder acceder por API - sin sufijo _QR
    nombre_con_id = f"{datos['id']}.png"
    ruta_con_id = os.path.join(app.config['OUTPUT_FOLDER'], nombre_con_id)
    qr_img.save(ruta_con_id)
    
    app.logger.info(f"QR generado con información del documento {datos['id']} y guardado como PNG")
    
    # Ruta a retornar (la personalizada o la estándar con ID)
    ruta_principal = ruta_personalizada if nombre_personalizado else ruta_con_id
    return ruta_principal, qr_data

def procesar_carta_estado(carta_data, nombre_personalizado=None):
    """Procesa un solo archivo PDF (carta de estado) y genera QR"""
    app.logger.info(f"Procesando carta: {carta_data['nombre_original']}")
    
    try:
        # 1. Generar QR con la información relevante
        ruta_qr_png, qr_data = generar_qr_con_datos(carta_data, nombre_personalizado)
        
        # 2. Guardar una copia local de la carta de estado (incluir ID en el nombre)
        nombre_con_id = f"{carta_data['id']}_{carta_data['nombre_original']}"
        ruta_copia_carta = os.path.join(app.config['OUTPUT_FOLDER'], nombre_con_id)
        
        with open(ruta_copia_carta, 'wb') as f:
            f.write(carta_data['pdf_data'])
        app.logger.info(f"Carta guardada en: {ruta_copia_carta}")
        
        # 3. Preparar datos para la base de datos
        nombre_base, extension = os.path.splitext(carta_data['nombre_original'])
        
        # Nombre base del QR
        nombre_qr_png = os.path.basename(ruta_qr_png)
        qr_url = f"/api/descargar/qr/{carta_data['id']}"
        
        datos_bd = {
            "id": carta_data["id"],
            "nombre_original": carta_data['nombre_original'],
            "s3_key": f"cartas/{carta_data['id']}/{nombre_con_id}",
            "s3_url": f"https://menuidac.com/api/descargar/documento/{carta_data['id']}",
            "tamano_bytes": carta_data["tamano_bytes"],
            "qr_data": qr_data,
            "descripcion": f"Carta de estado: {carta_data['nombre_original']}",
            "metadata": {
                "ruta_carta": ruta_copia_carta,
                "nombre_interno_carta": nombre_con_id,
                "ruta_qr_png": ruta_qr_png,
                "qr_url": qr_url,
                "nombre_personalizado": nombre_personalizado,
                "fecha_procesamiento": datetime.datetime.now().isoformat()
            }
        }
        
        # 4. Guardar en base de datos
        bd_resultado = guardar_datos_bd(datos_bd)
        
        if bd_resultado:
            app.logger.info("Carta procesada y datos guardados correctamente")
            
            resultado = {
                "carta_guardada": ruta_copia_carta,
                "id_documento": carta_data["id"],
                "qr_png_path": ruta_qr_png,
                "qr_png_url": qr_url,
                "qr_personalizado": nombre_personalizado is not None,
                "success": True
            }
            
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

# Endpoint para procesar carta de estado
@app.route('/api/procesar', methods=['POST'])
def procesar_carta():
    """Endpoint para recibir y procesar un archivo PDF (carta de estado)"""
    try:
        # Verificar que se haya enviado el archivo
        if 'carta' not in request.files:
            return jsonify({"error": "Se requiere el archivo 'carta'", "success": False}), 400
        
        archivo_carta = request.files['carta']
        
        # Verificar que el archivo tenga nombre
        if archivo_carta.filename == '':
            return jsonify({"error": "El archivo debe tener un nombre", "success": False}), 400
        
        # Verificar que el archivo sea PDF
        if not archivo_carta.filename.lower().endswith('.pdf'):
            return jsonify({"error": "El archivo debe ser PDF", "success": False}), 400
        
        # Obtener el nombre personalizado si se proporcionó
        nombre_personalizado = request.form.get('nombre_qr_personalizado', None)
        if nombre_personalizado:
            app.logger.info(f"Nombre personalizado recibido: {nombre_personalizado}")
        
        # Extraer datos de la carta de estado
        carta_data = extraer_datos_carta_estado(archivo_carta)
        
        # Procesar la carta de estado con el nombre personalizado si existe
        resultado = procesar_carta_estado(carta_data, nombre_personalizado)
        
        if resultado.get("success", False):
            app.logger.info(f"Documento procesado correctamente, enviando respuesta a cliente")
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
            cursor.execute("SELECT nombre_original, metadata FROM documentos_qr WHERE id = %s", (id_documento,))
            documento = cursor.fetchone()
            
            if documento:
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
            
            # Filtrar archivos que contengan el ID y sean PDF (carta original)
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

# Modificación del endpoint /api/descargar/qr/<documento_id> para usar nombres sin sufijo _QR
@app.route('/api/descargar/qr/<documento_id>', methods=['GET'])
def descargar_qr_imagen(documento_id):
    """Permite descargar la imagen del QR por el ID del documento"""
    try:
        app.logger.info(f"Buscando imagen QR con ID: {documento_id}")
        
        # Primero, intentar encontrar el archivo con el nombre exacto ID.png (sin sufijo _QR)
        nombre_qr_estandar = f"{documento_id}.png"
        ruta_qr_estandar = os.path.join(app.config['OUTPUT_FOLDER'], nombre_qr_estandar)
        
        if os.path.exists(ruta_qr_estandar):
            app.logger.info(f"Imagen QR encontrada con nombre estándar: {ruta_qr_estandar}")
            ruta_qr = ruta_qr_estandar
        else:
            # Intentar con el formato antiguo por compatibilidad
            nombre_qr_antiguo = f"{documento_id}_QR.png"
            ruta_qr_antiguo = os.path.join(app.config['OUTPUT_FOLDER'], nombre_qr_antiguo)
            
            if os.path.exists(ruta_qr_antiguo):
                app.logger.info(f"Imagen QR encontrada con formato antiguo: {ruta_qr_antiguo}")
                ruta_qr = ruta_qr_antiguo
            else:
                # Si no existe, buscar cualquier imagen que contenga el ID
                directorio = app.config['OUTPUT_FOLDER']
                archivos_coincidentes = [archivo for archivo in os.listdir(directorio) 
                                    if documento_id in archivo and archivo.endswith(('.png', '.jpg', '.jpeg'))]
                
                if not archivos_coincidentes:
                    # Última opción: buscar en la base de datos para obtener la ruta exacta
                    ruta_qr = None
                    conexion = conectar_bd()
                    
                    if conexion:
                        try:
                            with conexion.cursor() as cursor:
                                cursor.execute("SELECT metadata FROM documentos_qr WHERE id = %s", (documento_id,))
                                documento = cursor.fetchone()
                                
                                if documento:
                                    metadata = json.loads(documento["metadata"])
                                    ruta_qr = metadata.get("ruta_qr_png")
                                    
                                    if ruta_qr and os.path.exists(ruta_qr):
                                        app.logger.info(f"Imagen QR encontrada mediante metadata: {ruta_qr}")
                                    else:
                                        ruta_qr = None
                        except Exception as e:
                            app.logger.error(f"Error al consultar la base de datos: {e}")
                        finally:
                            conexion.close()
                    
                    if not ruta_qr:
                        app.logger.error(f"No se encontró imagen QR para el ID: {documento_id}")
                        return jsonify({"error": "Imagen QR no encontrada", "success": False}), 404
                else:
                    # Usar el primer archivo QR encontrado
                    ruta_qr = os.path.join(directorio, archivos_coincidentes[0])
                    app.logger.info(f"Imagen QR encontrada mediante búsqueda: {ruta_qr}")
        
        # Obtener información del documento incluyendo si hay nombre personalizado
        conexion = conectar_bd()
        nombre_descarga = None
        
        if conexion:
            try:
                with conexion.cursor() as cursor:
                    cursor.execute("SELECT nombre_original, metadata FROM documentos_qr WHERE id = %s", (documento_id,))
                    documento = cursor.fetchone()
                    
                    if documento:
                        metadata = json.loads(documento["metadata"])
                        nombre_personalizado = metadata.get("nombre_personalizado", None)
                        
                        if nombre_personalizado:
                            # Sin sufijo _QR
                            nombre_descarga = f"{nombre_personalizado}.png"
                        else:
                            nombre_base, extension = os.path.splitext(documento["nombre_original"])
                            # Sin sufijo _QR
                            nombre_descarga = f"{nombre_base}.png"
            except Exception as e:
                app.logger.error(f"Error al buscar nombre personalizado: {e}")
            finally:
                conexion.close()
        
        # Si no se pudo obtener el nombre de la BD, usar el nombre del archivo
        if not nombre_descarga:
            # Eliminar sufijos si existen
            nombre_base = os.path.basename(ruta_qr)
            if "_QR" in nombre_base:
                nombre_base = nombre_base.replace("_QR", "")
            nombre_descarga = nombre_base
        
        # Determinar el tipo MIME basado en la extensión del archivo
        mimetype = 'image/png' if ruta_qr.lower().endswith('.png') else 'image/jpeg'
        
        # Forzar descarga con attachment=True y nombre personalizado
        response = send_file(ruta_qr, mimetype=mimetype, as_attachment=True, 
                           download_name=nombre_descarga)
                           
        # Añadir cabeceras para forzar descarga
        response.headers["Content-Disposition"] = f"attachment; filename={nombre_descarga}"
        response.headers["Content-Type"] = mimetype
        
        return response
        
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
    print(f"  - POST https://menuidac.com/api/procesar - Procesar la carta de estado")
    print(f"  - GET https://menuidac.com/api/descargar/<nombre_archivo> - Descargar por nombre")
    print(f"  - GET https://menuidac.com/api/descargar/documento/<documento_id> - Descargar por ID")
    print(f"  - GET https://menuidac.com/api/descargar/qr/<documento_id> - Descargar solo el QR como imagen")
    
    # Usar waitress para producción
    from waitress import serve
    serve(app, host='0.0.0.0', port=puerto, threads=4)