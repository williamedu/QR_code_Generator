import os
import tkinter as tk
from tkinter import filedialog

def seleccionar_pdf():
    """Abre una ventana para seleccionar un archivo PDF y devuelve la ruta"""
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
        
    root.destroy()
    return archivo_pdf

def main():
    """Función principal del programa"""
    print("INICIANDO_SCRIPT")
    seleccionar_pdf()

if __name__ == "__main__":
    main()
