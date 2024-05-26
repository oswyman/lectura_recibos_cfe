from flask import Flask, request, render_template, redirect, url_for, flash, send_file, session
import PyPDF2
import openai
import time
import os
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.secret_key = os.urandom(24)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf'}

def process_pdf(file_stream):
    try:
        reader = PyPDF2.PdfReader(file_stream)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"

        if not text:
            raise ValueError("No se pudo extraer texto del PDF.")

        openai.api_key = "sk-proj-tfuCm7bGgk8JjtkE4YdMT3BlbkFJ7B7A3qJO0dn2PNDLiy8a"
        client = openai.OpenAI(api_key=openai.api_key)

        for attempt in range(3):  # Intentar hasta 3 veces
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Extract detailed data from CFE PDF, including historical consumption and payment breakdown. Organize the data in a structured list format."},
                        {"role": "user", "content": text}
                    ]
                )
                data = response.choices[0].message.content

                # Parse the data returned by GPT-3
                structured_data = []
                for line in data.split('\n'):
                    if ': ' in line:
                        field, value = line.split(': ', 1)
                        structured_data.append({'Campo': field.strip(), 'Valor': value.strip()})
                    else:
                        structured_data.append({'Campo': line.strip(), 'Valor': ''})

                return structured_data
            except openai.error.RateLimitError:
                time.sleep(10)  # Esperar 10 segundos antes de reintentar
            except openai.error.OpenAIError as e:
                raise ValueError(f"Error de OpenAI: {e}")

        raise ValueError("Exceeded retry attempts. Please try again later.")
    
    except Exception as e:
        return [{'Campo': 'Error procesando el archivo', 'Valor': str(e)}]

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash("No se ha seleccionado ningún archivo.", "danger")
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash("No se ha seleccionado ningún archivo.", "danger")
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        try:
            data = process_pdf(file.stream)
            if data[0]['Campo'] == 'Error procesando el archivo':
                flash(data[0]['Valor'], "danger")
                return redirect(url_for('index'))
            session['data'] = data  # Save data to session
            return redirect(url_for('result'))
        except Exception as e:
            flash(f"Error procesando el archivo: {str(e)}", "danger")
            return redirect(url_for('index'))
    
    flash("Tipo de archivo no permitido. Solo se aceptan archivos PDF.", "danger")
    return redirect(url_for('index'))

@app.route('/result')
def result():
    data = session.get('data')
    if not data:
        flash("No hay datos para mostrar.", "danger")
        return redirect(url_for('index'))

    return render_template('result.html', data=data)

@app.route('/download/<file_type>')
def download_file(file_type):
    data = session.get('data')
    if not data:
        flash("No hay datos para descargar.", "danger")
        return redirect(url_for('index'))

    df = pd.DataFrame(data)

    if file_type == 'csv':
        output = BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(output, mimetype='text/csv', as_attachment=True, download_name='datos.csv')

    elif file_type == 'xlsx':
        output = BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='datos.xlsx')

    flash("Formato de archivo no soportado.", "danger")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
