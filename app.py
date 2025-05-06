import os
import qrcode
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import tempfile
from flask import Flask, request, send_file, jsonify
import werkzeug.utils

app = Flask(__name__)

@app.route('/add-qr', methods=['POST'])
def add_qr_to_pdf():
    # Check if a file was uploaded
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    pdf_file = request.files['file']
    
    # Check if the file is a PDF
    if not pdf_file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "File must be a PDF"}), 400
    
    # Generate safe filename and add _QR suffix
    original_filename = werkzeug.utils.secure_filename(pdf_file.filename)
    filename_without_ext = os.path.splitext(original_filename)[0]
    output_filename = f"{filename_without_ext}_QR.pdf"
    
    # Create a temporary file for the input PDF
    temp_input_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    pdf_file.save(temp_input_pdf.name)
    temp_input_pdf.close()
    
    try:
        # Generate QR code with the filename
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(f"Documento: {filename_without_ext}")
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Save QR image to temporary file
        temp_qr_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        qr_img.save(temp_qr_file.name)
        temp_qr_file.close()
        
        # Get dimensions of original PDF
        pdf_reader = PdfReader(temp_input_pdf.name)
        first_page = pdf_reader.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)
        
        # Create temporary PDF with QR code
        qr_buffer = BytesIO()
        qr_pdf = canvas.Canvas(qr_buffer, pagesize=(page_width, page_height))
        
        # Add QR code with reduced size, positioned near top
        qr_size = 60
        margin_x = 100
        margin_y = 290
        
        qr_pdf.drawImage(
            temp_qr_file.name,
            page_width - qr_size - margin_x,
            margin_y,
            width=qr_size,
            height=qr_size
        )
        
        qr_pdf.save()
        
        # Combine original PDF with QR code PDF
        qr_buffer.seek(0)
        qr_reader = PdfReader(qr_buffer)
        
        # Create output PDF
        pdf_writer = PdfWriter()
        
        # Combine each page
        for i in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[i]
            page.merge_page(qr_reader.pages[0])
            pdf_writer.add_page(page)
        
        # Create temporary output file
        temp_output_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        
        # Write the combined PDF
        with open(temp_output_pdf.name, "wb") as output_file:
            pdf_writer.write(output_file)
        
        # Send the file to the client
        return send_file(
            temp_output_pdf.name,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=output_filename
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    finally:
        # Clean up temporary files
        if os.path.exists(temp_input_pdf.name):
            os.unlink(temp_input_pdf.name)
        if os.path.exists(temp_qr_file.name):
            os.unlink(temp_qr_file.name)
        if 'temp_output_pdf' in locals() and os.path.exists(temp_output_pdf.name):
            os.unlink(temp_output_pdf.name)

# Run the app if executed directly
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)