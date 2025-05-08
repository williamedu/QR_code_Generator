import os
import sys
import tkinter as tk
from tkinter import filedialog
from PyPDF2 import PdfReader

def seleccionar_pdf():
    """Abre una ventana para seleccionar un archivo PDF"""
    root = tk.Tk()
    root.withdraw()  # Oculta la ventana principal
    root.attributes('-topmost', True)  # Hacer que el diálogo sea visible sobre otras ventanas
    
    # Imprimir mensaje para consola
    print("ESPERANDO_SELECCION_PDF")
    
    archivo_pdf = filedialog.askopenfilename(
        title="Selecciona un archivo PDF",
        filetypes=[("Archivos PDF", "*.pdf")]
    )
    
    # Informar resultado de la selección
    if archivo_pdf:
        print(f"PDF_SELECCIONADO:{archivo_pdf}")
        return archivo_pdf
    else:
        print("SELECCION_CANCELADA")
        return None

def obtener_tamano_pdf(pdf_path):
    """Obtiene y muestra el tamaño de la primera hoja del PDF"""
    if not pdf_path:
        print("No se seleccionó ningún archivo. Terminando ejecución.")
        return

    try:
        # Abrir el PDF y obtener la primera página
        pdf_reader = PdfReader(pdf_path)
        first_page = pdf_reader.pages[0]
        
        # Obtener dimensiones
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)
        
        # Imprimir dimensiones en puntos
        print(f"DIMENSIONES_PUNTOS: Ancho={page_width} pts, Alto={page_height} pts")
        
        # Convertir a milímetros (1 punto = 0.352778 mm)
        width_mm = page_width * 0.352778
        height_mm = page_height * 0.352778
        print(f"DIMENSIONES_MM: Ancho={width_mm:.2f} mm, Alto={height_mm:.2f} mm")
        
        # Convertir a centímetros
        width_cm = width_mm / 10
        height_cm = height_mm / 10
        print(f"DIMENSIONES_CM: Ancho={width_cm:.2f} cm, Alto={height_cm:.2f} cm")
        
        # Convertir a pulgadas (1 punto = 1/72 pulgadas)
        width_inch = page_width / 72
        height_inch = page_height / 72
        print(f"DIMENSIONES_PULGADAS: Ancho={width_inch:.2f} in, Alto={height_inch:.2f} in")
        
        # Identificar formato de papel aproximado
        formatos_estandar = {
            "A4": (595, 842),
            "Carta": (612, 792),
            "Legal": (612, 1008),
            "A3": (842, 1191),
            "A5": (420, 595),
            "B5": (499, 709)
        }
        
        formato_detectado = "Personalizado"
        for nombre, dimensiones in formatos_estandar.items():
            # Margen de error de ±5 puntos
            if (abs(page_width - dimensiones[0]) <= 5 and 
                abs(page_height - dimensiones[1]) <= 5):
                formato_detectado = nombre
                break
            # Comprobar también en orientación horizontal
            elif (abs(page_width - dimensiones[1]) <= 5 and 
                  abs(page_height - dimensiones[0]) <= 5):
                formato_detectado = f"{nombre} (Horizontal)"
                break
                
        print(f"FORMATO_DETECTADO: {formato_detectado}")
        
        # Mostrar mensaje con los resultados
        mostrar_resultados(page_width, page_height, formato_detectado)
        
    except Exception as e:
        error_msg = str(e)
        print(f"ERROR_PROCESAMIENTO:{error_msg}")
        
        # Mostrar un mensaje de error
        root = tk.Tk()
        root.title("Error")
        root.geometry("400x150")
        root.attributes('-topmost', True)
        
        label = tk.Label(root, text=f"Error al procesar el PDF:\n{error_msg}", padx=20, pady=20)
        label.pack()
        
        def cerrar():
            root.destroy()
            
        boton = tk.Button(root, text="Aceptar", command=cerrar)
        boton.pack(pady=10)
        
        root.mainloop()

def mostrar_resultados(ancho, alto, formato):
    """Muestra los resultados en una ventana emergente"""
    root = tk.Tk()
    root.title("Tamaño del PDF")
    root.geometry("400x200")
    root.attributes('-topmost', True)
    
    mensaje = (
        f"Dimensiones de la primera página:\n\n"
        f"Ancho: {ancho:.2f} puntos ({ancho/72:.2f} pulgadas)\n"
        f"Alto: {alto:.2f} puntos ({alto/72:.2f} pulgadas)\n\n"
        f"Formato detectado: {formato}"
    )
    
    label = tk.Label(root, text=mensaje, padx=20, pady=20)
    label.pack()
    
    def cerrar():
        root.destroy()
        print("VENTANA_RESULTADOS_CERRADA")
        
    boton = tk.Button(root, text="Aceptar", command=cerrar)
    boton.pack(pady=10)
    
    root.mainloop()

def main():
    """Función principal del programa"""
    print("INICIANDO_SCRIPT")
    pdf_path = seleccionar_pdf()
    
    if pdf_path:
        obtener_tamano_pdf(pdf_path)
    else:
        print("SELECCION_CANCELADA_FINAL")
        
        # Mostrar mensaje de cancelación
        root = tk.Tk()
        root.title("Operación Cancelada")
        root.geometry("300x100")
        root.attributes('-topmost', True)
        
        label = tk.Label(root, text="Operación cancelada. No se seleccionó ningún archivo.", padx=20, pady=20)
        label.pack()
        
        def cerrar():
            root.destroy()
            print("VENTANA_CANCELACION_CERRADA")
        
        boton = tk.Button(root, text="Aceptar", command=cerrar)
        boton.pack(pady=10)
        
        root.mainloop()

if __name__ == "__main__":
    main()