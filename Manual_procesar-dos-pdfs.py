import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import qrcode
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from io import BytesIO
import tempfile
import uuid
import datetime
import json
import pymysql
import shutil

# 📌 Configuración de la base de datos
DB_HOST = "americastowersimulator.c14c80caytj6.us-east-1.rds.amazonaws.com"
DB_USER = "admin"
DB_PASSWORD = "Controlador2929"
DB_NAME = "simulador(unity-access)"

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
        print(f"ERROR_BD_CONEXION:{e}")
        return None

def seleccionar_pdf(titulo="Selecciona un archivo PDF"):
    """Abre una ventana para seleccionar un archivo PDF"""
    root = tk.Tk()
    root.withdraw()  # Oculta la ventana principal
    root.attributes('-topmost', True)  # Hacer que el diálogo sea visible sobre otras ventanas
    
    archivo_pdf = filedialog.askopenfilename(
        title=titulo,
        filetypes=[("Archivos PDF", "*.pdf")]
    )
    
    # Informar resultado de la selección
    if archivo_pdf:
        return archivo_pdf
    else:
        return None

def guardar_datos_bd(datos):
    """Guarda los datos en la base de datos"""
    conexion = conectar_bd()
    if not conexion:
        print("ERROR_BD:No se pudo establecer conexión con la base de datos")
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
            print(f"DATOS_GUARDADOS_BD:Registro con ID {datos['id']} guardado exitosamente")
            return True
    except pymysql.MySQLError as e:
        print(f"ERROR_BD_INSERCION:{e}")
        return False
    finally:
        conexion.close()

def procesar_archivos(ruta_carta, ruta_oficio):
    """Procesa los dos archivos: carta de estado y oficio"""
    print(f"PROCESANDO_CARTA:{ruta_carta}")
    print(f"PROCESANDO_OFICIO:{ruta_oficio}")
    
    try:
        # 1. Extraer información de la carta de estado
        datos_carta = extraer_datos_carta_estado(ruta_carta)
        
        # 2. Generar QR con la información relevante
        qr_path, qr_data = generar_qr_con_datos(datos_carta)
        
        # 3. Guardar una copia local de la carta de estado (simulando S3)
        directorio_script = os.path.dirname(os.path.abspath(__file__))
        nombre_base_carta = os.path.basename(ruta_carta)
        ruta_copia_carta = os.path.join(directorio_script, nombre_base_carta)
        
        # Copiar la carta si no es el mismo archivo
        if ruta_carta != ruta_copia_carta:
            shutil.copy2(ruta_carta, ruta_copia_carta)
            print(f"CARTA_GUARDADA:{ruta_copia_carta}")
        
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
            print("PROCESO_COMPLETADO:Ambos archivos procesados y datos guardados correctamente")
            return {
                "carta_guardada": ruta_copia_carta,
                "oficio_con_qr": ruta_oficio_con_qr,
                "id_documento": datos_carta["id"]
            }
        else:
            print("ERROR_BD_GUARDADO:No se pudieron guardar los datos en la base de datos")
            return None
            
    except Exception as e:
        print(f"ERROR_PROCESAMIENTO:{str(e)}")
        return None

def extraer_datos_carta_estado(pdf_path):
    """Extrae información relevante de la carta de estado"""
    # En un caso real, aquí extraerías datos específicos del PDF
    # Para este ejemplo, creamos datos de muestra
    
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
    
    print(f"DATOS_EXTRAIDOS:ID generado {documento_id}")
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
    
    print(f"QR_GENERADO:Contiene información del documento {datos['id']}")
    return temp_qr_file.name, qr_data

def agregar_qr_a_oficio(oficio_path, qr_image_path, qr_data):
    """Agrega un código QR al oficio y guarda una nueva versión"""
    # Obtener el nombre del archivo sin ruta
    nombre_base = os.path.basename(oficio_path)
    nombre_sin_extension = os.path.splitext(nombre_base)[0]
    
    # Obtener el directorio donde se está ejecutando el script
    directorio_script = os.path.dirname(os.path.abspath(__file__))
    
    # Definir nombre del archivo de salida
    output_name = f"{nombre_sin_extension}_con_QR"
    output_path = os.path.join(directorio_script, f"{output_name}.pdf")
    
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
        
        print(f"QR_AGREGADO:Oficio con QR guardado en {output_path}")
        return output_path
        
    except Exception as e:
        print(f"ERROR_QR:{str(e)}")
        # Limpiar
        if os.path.exists(qr_image_path):
            os.unlink(qr_image_path)
        return None

def mostrar_resultado(resultado):
    """Muestra una ventana con el resultado del proceso"""
    root = tk.Tk()
    root.title("Proceso Completado")
    root.geometry("500x300")
    root.attributes('-topmost', True)
    
    if resultado:
        # Mostrar mensaje de éxito
        mensaje = f"Proceso completado exitosamente:\n\n" \
                 f"ID del documento: {resultado['id_documento']}\n\n" \
                 f"Archivo carta guardado en:\n{resultado['carta_guardada']}\n\n" \
                 f"Oficio con QR guardado en:\n{resultado['oficio_con_qr']}"
        color = "#4CAF50"  # Verde
    else:
        # Mostrar mensaje de error
        mensaje = "Error al procesar los archivos.\nRevisa los mensajes de consola para más detalles."
        color = "#F44336"  # Rojo
    
    # Marco principal
    frame = tk.Frame(root, padx=20, pady=20)
    frame.pack(fill=tk.BOTH, expand=True)
    
    # Etiqueta con el mensaje
    label = tk.Label(
        frame,
        text=mensaje,
        padx=10,
        pady=10,
        justify=tk.LEFT,
        bg=color,
        fg="white",
        wraplength=450
    )
    label.pack(fill=tk.BOTH, expand=True)
    
    # Botón para cerrar
    def cerrar():
        root.destroy()
        print("VENTANA_CERRADA")
    
    boton = tk.Button(frame, text="Aceptar", command=cerrar, width=10, height=1)
    boton.pack(pady=10)
    
    root.mainloop()

def main(ruta_carta=None, ruta_oficio=None):
    """Función principal del programa"""
    print("INICIANDO_SCRIPT")
    
    # Si no se proporcionaron rutas, pedir selección
    if not ruta_carta:
        print("ESPERANDO_SELECCION_CARTA")
        ruta_carta = seleccionar_pdf("Selecciona la Carta de Estado")
        if not ruta_carta:
            print("SELECCION_CARTA_CANCELADA")
            return
        print(f"CARTA_SELECCIONADA:{ruta_carta}")
    
    if not ruta_oficio:
        print("ESPERANDO_SELECCION_OFICIO")
        ruta_oficio = seleccionar_pdf("Selecciona el Oficio")
        if not ruta_oficio:
            print("SELECCION_OFICIO_CANCELADA")
            return
        print(f"OFICIO_SELECCIONADO:{ruta_oficio}")
    
    # Procesar los archivos
    resultado = procesar_archivos(ruta_carta, ruta_oficio)
    
    # Mostrar resultado
    mostrar_resultado(resultado)

if __name__ == "__main__":
    # Verificar si se pasaron argumentos (rutas de archivos)
    if len(sys.argv) == 3:
        main(sys.argv[1], sys.argv[2])
    else:
        main()