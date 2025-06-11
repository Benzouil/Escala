import re
from collections import Counter
import pandas as pd
import os
import logging
from flask import Flask, request, redirect, url_for, render_template, flash, send_from_directory
from werkzeug.utils import secure_filename
import io

# --- Configuration ---
UPLOAD_FOLDER = os.environ.get('RENDER_DISK_PATH', 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'out', 'snap', 'log'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = os.urandom(24)

logging.basicConfig(level=logging.INFO)

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Logique de nettoyage de errpt.py ---
def clean_errpt_content(text_content):
    """Nettoie le contenu d'un errpt en supprimant les blocs Detail/Sense Data."""
    output = io.StringIO()
    skipping = False
    hex_word_pattern = re.compile(r"^[0-9A-Fa-f]{4}$")

    def is_hex_line(line):
        toks = line.strip().split()
        return bool(toks) and all(hex_word_pattern.fullmatch(tok) for tok in toks)

    for line in text_content.splitlines():
        stripped_line = line.strip().lower()
        if stripped_line in {"detail data", "sense data"}:
            skipping = True
            continue
        
        if skipping:
            if is_hex_line(line) or not line.strip():
                continue
            skipping = False
        
        output.write(line + '\n')
    return output.getvalue()

# --- Logique de nettoyage de EventLogs.py ---
def clean_eventlog_content(text_content):
    """Nettoie le contenu d'un log ASMI en supprimant les blocs Log Hex Dump."""
    hex_line_pattern = re.compile(r'^\s*[0-9A-Fa-f]{8}\s')
    output_lines = []
    skip_hex = False
    blank_seen = False

    for raw_line in text_content.splitlines():
        line = raw_line.rstrip("\n\r")

        if skip_hex:
            if not line.strip():
                skip_hex = False
                continue
            if hex_line_pattern.match(line):
                continue
            skip_hex = False

        if line.lstrip().startswith("Log Hex Dump"):
            skip_hex = True
            continue

        if not line.strip():
            if blank_seen:
                continue
            output_lines.append("")
            blank_seen = True
        else:
            output_lines.append(line)
            blank_seen = False

    return "\n".join(output_lines) + "\n"


# --- Fonctions de l'application Flask d'origine (extract_labels, etc.) ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_labels(file_content):
    label_pattern = re.compile(r'^LABEL:\s+(\S+)', re.MULTILINE)
    labels = label_pattern.findall(file_content)
    if not labels:
        return pd.DataFrame(columns=['Label', 'Count'])
    label_counts = Counter(labels)
    sorted_labels = sorted(label_counts.items(), key=lambda item: item[1], reverse=True)
    return pd.DataFrame(sorted_labels, columns=['Label', 'Count'])


@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Aucun fichier sélectionné.', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        clean_type = request.form.get('clean_type', 'none') # Récupère le type de nettoyage

        if file.filename == '':
            flash('Aucun fichier sélectionné.', 'error')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            logging.info(f"Fichier {filename} sauvegardé.")

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Appliquer le nettoyage si demandé
                if clean_type == 'errpt':
                    cleaned_content = clean_errpt_content(content)
                    new_filename = f"cleaned_{filename}"
                elif clean_type == 'eventlog':
                    cleaned_content = clean_eventlog_content(content)
                    new_filename = f"cleaned_{filename}"
                else: # 'analyse' ou 'none'
                    # Si c'est juste une analyse, on ne modifie pas le contenu pour l'analyse
                    label_counts_df = extract_labels(content)
                    if label_counts_df.empty:
                        flash("Aucun 'LABEL' trouvé dans le fichier.", "warning")
                        return render_template('results.html', tables=[])
                    
                    flash(f"Analyse de '{filename}' terminée.", 'success')
                    return render_template('results.html', tables=[{'title': 'Comptage des Labels', 'df': label_counts_df}])

                # Sauvegarder le fichier nettoyé et proposer le téléchargement
                cleaned_file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                with open(cleaned_file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                
                flash(f"Fichier '{filename}' nettoyé avec succès !", 'success')
                return render_template('results.html', download_filename=new_filename)

            except Exception as e:
                logging.error(f"Erreur lors du traitement du fichier: {e}")
                flash(f"Une erreur est survenue: {e}", "error")
                return redirect(request.url)
        else:
            flash('Type de fichier non autorisé.', 'error')
            return redirect(request.url)

    return render_template('upload.html')

@app.route('/download/<filename>')
def download_file(filename):
    """Route pour télécharger un fichier depuis le dossier d'uploads."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True)
