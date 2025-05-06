import os
import sys
import uuid
import datetime
import json
import tempfile
import shutil
from io import BytesIO
# recibe 2 rutas pdf locales
# Importaciones para PDF
import qrcode
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

# Importaciones para base de datos
import pymysql

# Importaciones para la API REST
from flask import Flask, request, jsonify

# 📌 Configuración de la base de datos
DB_HOST = "americastowersimulator.c14c80caytj6.us-east-1.rds.amazonaws.com"
DB_USER = "admin"
DB_PASSWORD = "Controlador2929"
DB_NAME = "simulador(unity-access)"

# Directorio para guardar los archivos procesados
DIRECTORIO_SALIDA = os.path.dirname(os.path.abspath(__file__))

# Crear aplicación Flask
app = Flask(__name__)

# 📌 Función para conectar con la base de datos
def conectar_bd():
    try:
        conexion = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor  # Devuelve los resultados como diccionarios
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
                "docs-qr-bucket",  # Nombre del bucket (por ahora simulado)
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

def extraer_datos_carta_estado(pdf_path):
    """Extrae información relevante de la carta de estado"""
    # Obtener el nombre del archivo sin ruta
    nombre_base = os.path.basename(pdf_path)
    nombre_sin_extension = os.path.splitext(nombre_base)[0]
    
    # Generar un UUID para el documento
    documento_id = str(uuid.uuid4())
    
    # Leer información básica del PDF
    pdf_reader = PdfReader(pdf_path)
    
    # Datos que normalmente extraerías del PDF
    datos = {
        "id": documento_id,
        "nombre_original": nombre_base,
        "fecha_creacion": datetime.datetime.now().isoformat(),
        "tipo_documento": "Carta de Estado",
        "tamano_bytes": os.path.getsize(pdf_path),
        "paginas": len(pdf_reader.pages)
    }
    
    app.logger.info(f"Datos extraídos con ID generado {documento_id}")
    return datos

def generar_qr_con_datos(datos):
    """Genera un código QR con la información de la carta de estado"""
    # Crear la URL que iría en el QR (por ahora es una URL simulada)
    url_base = "https://documentos.ejemplo.com/descargar/"
    url_documento = f"{url_base}{datos['id']}"
    
    # Crear una cadena JSON con información adicional
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
        error_correction=qrcode.constants.ERROR_CORRECT_M,  # Mayor corrección de errores
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

def agregar_qr_a_oficio(oficio_path, qr_image_path, qr_data):
    """Agrega un código QR al oficio y guarda una nueva versión"""
    # Obtener el nombre del archivo sin ruta
    nombre_base = os.path.basename(oficio_path)
    nombre_sin_extension = os.path.splitext(nombre_base)[0]
    
    # Definir nombre del archivo de salida
    output_name = f"{nombre_sin_extension}_con_QR"
    output_path = os.path.join(DIRECTORIO_SALIDA, f"{output_name}.pdf")
    
    try:
        # Obtener las dimensiones del PDF original
        pdf_reader = PdfReader(oficio_path)
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
        with open(output_path, "wb") as output_file:
            pdf_writer.write(output_file)
        
        # Eliminar el archivo temporal del QR
        os.unlink(qr_image_path)
        
        app.logger.info(f"Oficio con QR guardado en {output_path}")
        return output_path
        
    except Exception as e:
        app.logger.error(f"Error al agregar QR: {str(e)}")
        # Limpiar
        if os.path.exists(qr_image_path):
            os.unlink(qr_image_path)
        return None

def procesar_archivos(ruta_carta, ruta_oficio):
    """Procesa los dos archivos: carta de estado y oficio"""
    app.logger.info(f"Procesando carta: {ruta_carta}")
    app.logger.info(f"Procesando oficio: {ruta_oficio}")
    
    try:
        # 1. Extraer información de la carta de estado
        datos_carta = extraer_datos_carta_estado(ruta_carta)
        
        # 2. Generar QR con la información relevante
        qr_path, qr_data = generar_qr_con_datos(datos_carta)
        
        # 3. Guardar una copia local de la carta de estado (simulando S3)
        nombre_base_carta = os.path.basename(ruta_carta)
        ruta_copia_carta = os.path.join(DIRECTORIO_SALIDA, nombre_base_carta)
        
        # Copiar la carta si no es el mismo archivo
        if ruta_carta != ruta_copia_carta:
            shutil.copy2(ruta_carta, ruta_copia_carta)
            app.logger.info(f"Carta guardada en: {ruta_copia_carta}")
        
        # 4. Añadir el QR al oficio
        ruta_oficio_con_qr = agregar_qr_a_oficio(ruta_oficio, qr_path, qr_data)
        
        # 5. Preparar datos para la base de datos
        nombre_base_oficio = os.path.basename(ruta_oficio)
        nombre_sin_extension = os.path.splitext(nombre_base_oficio)[0]
        
        datos_bd = {
            "id": datos_carta["id"],
            "nombre_original": nombre_base_carta,
            "nombre_con_qr": f"{nombre_sin_extension}_con_QR.pdf",
            "s3_key": f"cartas/{datos_carta['id']}/{nombre_base_carta}",
            "s3_url": f"https://docs-qr-bucket.s3.amazonaws.com/cartas/{datos_carta['id']}/{nombre_base_carta}",
            "tamano_bytes": os.path.getsize(ruta_carta),
            "qr_data": qr_data,
            "descripcion": f"Carta de estado para oficio: {nombre_sin_extension}",
            "metadata": {
                "oficio_relacionado": nombre_base_oficio,
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
                "id_documento": datos_carta["id"],
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

# Rutas de la API
@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint para verificar que la API está funcionando"""
    return jsonify({"status": "ok", "message": "API funcionando correctamente"})

@app.route('/api/procesar', methods=['POST'])
def procesar_endpoint():
    """Endpoint para procesar los archivos PDF"""
    try:
        # Verificar que se recibieron las rutas
        data = request.json
        if not data:
            return jsonify({"error": "No se recibieron datos", "success": False}), 400
        
        ruta_carta = data.get('ruta_carta')
        ruta_oficio = data.get('ruta_oficio')
        
        if not ruta_carta or not ruta_oficio:
            return jsonify({"error": "Se requieren las rutas de ambos archivos", "success": False}), 400
        
        # Verificar que los archivos existen
        if not os.path.exists(ruta_carta):
            return jsonify({"error": f"No se encontró el archivo carta: {ruta_carta}", "success": False}), 404
        
        if not os.path.exists(ruta_oficio):
            return jsonify({"error": f"No se encontró el archivo oficio: {ruta_oficio}", "success": False}), 404
        
        # Procesar los archivos
        resultado = procesar_archivos(ruta_carta, ruta_oficio)
        
        if resultado and resultado.get("success", False):
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 500
    
    except Exception as e:
        app.logger.error(f"Error en el endpoint: {str(e)}")
        return jsonify({"error": str(e), "success": False}), 500

if __name__ == '__main__':
    # Configurar el logger
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Imprimir mensaje de inicio
    print("Iniciando API en http://127.0.0.1:5000")
    print("Endpoints disponibles:")
    print("  - GET /api/health - Verificar si la API está funcionando")
    print("  - POST /api/procesar - Procesar los archivos PDF (requiere JSON con rutas)")
    print("Ejemplo de uso:")
    print("""
    curl -X POST http://127.0.0.1:5000/api/procesar 
      -H "Content-Type: application/json" 
      -d '{"ruta_carta":"/ruta/a/carta.pdf", "ruta_oficio":"/ruta/a/oficio.pdf"}'
    """)
    
    # Iniciar el servidor
    app.run(debug=True)
