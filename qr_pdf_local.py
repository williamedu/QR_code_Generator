import os
import sys
import tkinter as tk
from tkinter import filedialog
import qrcode
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from io import BytesIO
import tempfile

def seleccionar_pdf():
    """Abre una ventana para seleccionar un archivo PDF"""
    root = tk.Tk()
    root.withdraw()  # Oculta la ventana principal
    root.attributes('-topmost', True)  # Hacer que el diálogo sea visible sobre otras ventanas
    
    # Imprimir mensaje para que Unity sepa que estamos esperando selección
    print("ESPERANDO_SELECCION_PDF")
    
    archivo_pdf = filedialog.askopenfilename(
        title="Selecciona un archivo PDF",
        filetypes=[("Archivos PDF", "*.pdf")]
    )
    
    # Informar resultado de la selección para que Unity lo detecte
    if archivo_pdf:
        print(f"PDF_SELECCIONADO:{archivo_pdf}")
    else:
        print("SELECCION_CANCELADA")
        
    return archivo_pdf

def agregar_qr_a_pdf(pdf_path):
    """Agrega un código QR al PDF y guarda una nueva versión con el sufijo _QR"""
    if not pdf_path:
        print("No se seleccionó ningún archivo. Terminando ejecución.")
        return

    # Obtener el nombre del archivo sin ruta
    nombre_base = os.path.basename(pdf_path)
    nombre_sin_extension = os.path.splitext(nombre_base)[0]
    
    # Obtener el directorio donde se está ejecutando el script
    directorio_script = os.path.dirname(os.path.abspath(__file__))
    
    # Definir nombre del archivo de salida en el directorio del script
    output_name = f"{nombre_sin_extension}_QR"
    output_path = os.path.join(directorio_script, f"{output_name}.pdf")
    
    print(f"PROCESANDO_ARCHIVO:{pdf_path}")
    print(f"NOMBRE_SALIDA:{output_name}")
    print(f"RUTA_GUARDADO:{directorio_script}")
    
    try:
        # Generar el código QR
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        # El QR contiene el nombre del archivo
        qr.add_data(f"Documento: {nombre_sin_extension}")
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Guardar la imagen QR en un archivo temporal
        temp_qr_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        qr_img.save(temp_qr_file.name)
        temp_qr_file.close()
        
        # Obtener las dimensiones del PDF original
        pdf_reader = PdfReader(pdf_path)
        first_page = pdf_reader.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)
        
        # Crear un PDF temporal con el código QR
        qr_buffer = BytesIO()
        qr_pdf = canvas.Canvas(qr_buffer, pagesize=(page_width, page_height))
        
        # AJUSTES: Reducir el tamaño del QR y ponerlo en la posición especificada
        qr_size = 80  # Tamaño reducido del QR
        margin_x = 100  # Margen desde la derecha
        margin_y = 260  # Margen desde abajo - Para subir el QR
        
        qr_pdf.drawImage(
            temp_qr_file.name, 
            page_width - qr_size - margin_x,  # Posición X (desde la izquierda)
            margin_y,  # Posición Y (desde abajo)
            width=qr_size, 
            height=qr_size
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
            
            # Combinar con la página del QR (usamos siempre la misma página del QR)
            page.merge_page(qr_reader.pages[0])
            
            # Añadir al PDF de salida
            pdf_writer.add_page(page)
        
        # Guardar el PDF resultante
        with open(output_path, "wb") as output_file:
            pdf_writer.write(output_file)
        
        # Eliminar el archivo temporal
        os.unlink(temp_qr_file.name)
        
        print(f"PROCESO_COMPLETADO:{output_path}")
        print(f"RUTA_COMPLETA:{os.path.abspath(output_path)}")
        
        # Mostrar un mensaje de éxito con una pequeña interfaz gráfica
        root = tk.Tk()
        root.title("Proceso Completado")
        root.geometry("400x200")
        root.attributes('-topmost', True)  # Hacer ventana visible
        
        label = tk.Label(
            root, 
            text=f"PDF con QR generado exitosamente:\n{output_name}.pdf\n\nGuardado en la carpeta del script:\n{directorio_script}", 
            padx=20, 
            pady=20
        )
        label.pack()
        
        def cerrar():
            root.destroy()
            print("VENTANA_CERRADA")  # Señal para Unity
        
        boton = tk.Button(root, text="Aceptar", command=cerrar)
        boton.pack(pady=10)
        
        root.mainloop()
        
    except Exception as e:
        error_msg = str(e)
        print(f"ERROR_PROCESAMIENTO:{error_msg}")
        
        # Mostrar un mensaje de error
        root = tk.Tk()
        root.title("Error")
        root.geometry("400x150")
        root.attributes('-topmost', True)  # Hacer ventana visible
        
        label = tk.Label(root, text=f"Error al procesar el PDF:\n{error_msg}", padx=20, pady=20)
        label.pack()
        
        def cerrar():
            root.destroy()
            print("VENTANA_ERROR_CERRADA")  # Señal para Unity
        
        boton = tk.Button(root, text="Aceptar", command=cerrar)
        boton.pack(pady=10)
        
        root.mainloop()

def main():
    """Función principal del programa"""
    print("INICIANDO_SCRIPT")
    pdf_path = seleccionar_pdf()
    
    if pdf_path:
        agregar_qr_a_pdf(pdf_path)
    else:
        print("SELECCION_CANCELADA_FINAL")
        
        # Mostrar mensaje de cancelación
        root = tk.Tk()
        root.title("Operación Cancelada")
        root.geometry("300x100")
        root.attributes('-topmost', True)  # Hacer ventana visible
        
        label = tk.Label(root, text="Operación cancelada. No se seleccionó ningún archivo.", padx=20, pady=20)
        label.pack()
        
        def cerrar():
            root.destroy()
            print("VENTANA_CANCELACION_CERRADA")  # Señal para Unity
        
        boton = tk.Button(root, text="Aceptar", command=cerrar)
        boton.pack(pady=10)
        
        root.mainloop()

if __name__ == "__main__":
    main()