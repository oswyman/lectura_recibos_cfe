from flask import Flask, request, render_template, redirect, url_for, flash, send_file, session, send_from_directory
import PyPDF2
import openai
import os
import pandas as pd
from io import BytesIO
from dotenv import load_dotenv
import time
from pdf2image import convert_from_path

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Cargar las variables de entorno desde el archivo cfe.env
load_dotenv('cfe.env')
openai.api_key = os.getenv('OPENAI_API_KEY')

# Carpeta para guardar los archivos subidos
UPLOAD_FOLDER = 'uploads'
IMAGE_FOLDER = 'static/images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(IMAGE_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['IMAGE_FOLDER'] = IMAGE_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf'}

def process_pdf(file_path):
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"

        if not text:
            raise ValueError("No se pudo extraer texto del PDF.")

        for attempt in range(3):  # Intentar hasta 3 veces
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Extrae todos los datos del PDF de CFE, incluyendo consumo histórico y desglose de pago. Organiza los datos en una lista estructurada."},
                        {"role": "user", "content": text}
                    ]
                )
                data = response['choices'][0]['message']['content']

                # Parse the data returned by GPT-3
                structured_data = []
                period = "Periodo no encontrado"
                for line in data.split('\n'):
                    if ': ' in line:
                        field, value = line.split(': ', 1)
                        structured_data.append({'Campo': field.strip(), 'Valor': value.strip()})
                        if 'Periodo facturado' in field:
                            period = value.strip()
                    else:
                        structured_data.append({'Campo': line.strip(), 'Valor': ''})

                # Orden esperado de los campos del recibo de CFE
                expected_fields_order = [
                    'Periodo facturado', 'Número de servicio', 'Fecha de emisión', 'Fecha límite de pago', 
                    'Consumo kWh', 'Importe total', 'Desglose de pago', 'Consumo histórico'
                ]
                ordered_data = sorted(structured_data, key=lambda x: expected_fields_order.index(x['Campo']) if x['Campo'] in expected_fields_order else len(expected_fields_order))

                # Depuración: imprimir los datos extraídos
                print("Datos extraídos:", ordered_data)

                return {'period': period, 'data': ordered_data}
            except Exception as e:
                time.sleep(10)  # Esperar 10 segundos antes de reintentar
                print("Error procesando el archivo:", str(e))  # Depuración
                return {'period': "Error", 'data': [{'Campo': 'Error procesando el archivo', 'Valor': str(e)}]}

        print("Error procesando el archivo: Exceeded retry attempts.")  # Depuración
        return {'period': "Error", 'data': [{'Campo': 'Error procesando el archivo', 'Valor': 'Exceeded retry attempts. Please try again later.'}]}
    
    except Exception as e:
        print("Error procesando el archivo:", str(e))  # Depuración
        return [{'Campo': 'Error procesando el archivo', 'Valor': str(e)}]

def convert_pdf_to_images(pdf_path, output_folder):
    images = convert_from_path(pdf_path)
    image_paths = []
    for i, image in enumerate(images):
        image_path = os.path.join(output_folder, f"{os.path.basename(pdf_path).rsplit('.', 1)[0]}_page_{i + 1}.png")
        image.save(image_path, 'PNG')
        image_paths.append(image_path)
    return image_paths

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/select_files', methods=['POST'])
def select_files():
    num_files = int(request.form['num_files'])
    session['num_files'] = num_files
    return redirect(url_for('upload_files'))

@app.route('/upload_files')
def upload_files():
    num_files = session.get('num_files', 0)
    if num_files == 0:
        return redirect(url_for('index'))
    return render_template('upload_files.html', num_files=num_files)

@app.route('/upload', methods=['POST'])
def upload_file():
    files = request.files.getlist('files')
    num_files = session.get('num_files', 0)

    if len(files) != num_files:
        flash(f"Debe cargar {num_files} archivos.", "danger")
        return redirect(url_for('upload_files'))

    all_data = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filename)
            data = process_pdf(filename)
            image_paths = convert_pdf_to_images(filename, app.config['IMAGE_FOLDER'])
            if data['data'][0]['Campo'] == 'Error procesando el archivo':
                flash(data['data'][0]['Valor'], "danger")
                return redirect(url_for('upload_files'))
            all_data.append({'filename': file.filename, 'data': data, 'image_paths': image_paths})
        else:
            flash("Tipo de archivo no permitido. Solo se aceptan archivos PDF.", "danger")
            return redirect(url_for('upload_files'))

    session['data'] = all_data  # Save data to session
    return redirect(url_for('result'))

@app.route('/result')
def result():
    data = session.get('data')
    if not data:
        flash("No hay datos para mostrar.", "danger")
        return redirect(url_for('index'))

    # Depuración: imprimir los datos que se pasan a la plantilla
    print("Datos que se pasan a la plantilla:", data)

    return render_template('result.html', data=data)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/files')
def files():
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('files.html', files=files)

if __name__ == '__main__':
    app.run(debug=True)
