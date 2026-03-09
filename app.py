import os
import cv2
import numpy as np
import io
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_contours_and_angle(image_bytes):
    """Leest een afbeelding, vindt contouren en berekent de automatische rotatiehoek."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None, 0, img.shape[1], img.shape[0]

    quadrilaterals = []
    for cnt in contours:
        perimeter = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * perimeter, True)
        if len(approx) == 4:
            quadrilaterals.append(cnt)

    if not quadrilaterals:
        reference_contour = max(contours, key=cv2.contourArea)
    else:
        reference_contour = max(quadrilaterals, key=cv2.contourArea)

    rect = cv2.minAreaRect(reference_contour)
    angle = rect[2]
    box_width, box_height = rect[1]

    if box_width < box_height:
        angle += 90

    return contours, angle, img.shape[1], img.shape[0]

def get_contours_from_rotated_image(image_bytes, angle):
    """Roteert een afbeelding en retourneert de contouren van de objecten."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    height, width = img.shape[:2]
    center = (width // 2, height // 2)

    rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated_img = cv2.warpAffine(img, rot_mat, (width, height), borderValue=(255, 255, 255))

    gray = cv2.cvtColor(rotated_img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    return contours, width, height

def generate_preview(image_bytes, angle):
    """Genereert een PNG-preview van de geroteerde contouren."""
    contours, width, height = get_contours_from_rotated_image(image_bytes, angle)
    
    preview_img = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.drawContours(preview_img, contours, -1, (0, 0, 0), thickness=cv2.FILLED)

    _, buffer = cv2.imencode('.png', preview_img)
    return buffer.tobytes()

def generate_svg(image_bytes, angle):
    """Genereert de uiteindelijke SVG op basis van de contouren van de geroteerde afbeelding."""
    contours, width, height = get_contours_from_rotated_image(image_bytes, angle)

    svg_header = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
    svg_paths = []

    for cnt in contours:
        if cv2.contourArea(cnt) < 50:
            continue
        path_data = "M " + " L ".join([f"{p[0][0]} {p[0][1]}" for p in cnt]) + " Z"
        svg_paths.append(f'<path d="{path_data}" fill="black" />')

    svg_content = svg_header + "".join(svg_paths) + "</svg>"
    return svg_content

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files or request.files['file'].filename == '':
            return render_template('index.html', error="Geen bestand geselecteerd.")
        
        file = request.files['file']
        filename = file.filename

        # Controleer of het een PDF is en converteer naar PNG
        if filename.lower().endswith('.pdf'):
            from pdf2image import convert_from_bytes
            from pdf2image.exceptions import PDFInfoNotInstalledError

            # Genereer een nieuwe bestandsnaam met .png extensie
            png_filename = os.path.splitext(filename)[0] + '.png'
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], png_filename)

            try:
                images = convert_from_bytes(file.read(), first_page=1, last_page=1)
                if images:
                    images[0].save(filepath, 'PNG')
                    filename = png_filename # Gebruik de nieuwe png-naam voor de preview
                else:
                    return render_template('index.html', error="Kon geen afbeelding uit de PDF halen.")
            except PDFInfoNotInstalledError:
                 return render_template('index.html', error="PDF conversie fout: Poppler is niet geïnstalleerd op het systeem.")
        else:
            # Sla het geüploade bestand direct op als het geen PDF is
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

        return render_template('preview.html', filename=filename)

    return render_template('index.html')

@app.route('/preview-img/<filename>')
def preview_img(filename):
    """Genereert de preview-afbeelding en de berekende hoek."""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(filepath, 'rb') as f:
        image_bytes = f.read()

    _, angle, _, _ = get_contours_and_angle(image_bytes)
    preview_bytes = generate_preview(image_bytes, angle)
    
    import base64
    base64_encoded_data = base64.b64encode(preview_bytes).decode('utf-8')
    
    return jsonify({'angle': angle, 'preview_src': f'data:image/png;base64,{base64_encoded_data}'})

@app.route('/finalize', methods=['POST'])
def finalize():
    """Genereert de definitieve SVG met de (aangepaste) rotatiehoek."""
    data = request.get_json()
    filename = data['filename']
    angle = float(data['angle'])
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(filepath, 'rb') as f:
        image_bytes = f.read()

    svg_data = generate_svg(image_bytes, angle)
    os.remove(filepath) # Ruim het tijdelijke bestand op

    return send_file(
        io.BytesIO(svg_data.encode()),
        mimetype='image/svg+xml',
        as_attachment=True,
        download_name='silhouette_final.svg'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)