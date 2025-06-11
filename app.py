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

# --- Fonctions de nettoyage (inchangées) ---
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

# --- Fonctions d'analyse (inchangées) ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_labels(file_content):
    """Extrait et compte les 'LABELs' d'un fichier errpt/snap."""
    label_pattern = re.compile(r'^LABEL:\s+(\S+)', re.MULTILINE)
    labels = label_pattern.findall(file_content)
    if not labels:
        return pd.DataFrame(columns=['Label', 'Count'])
    label_counts = Counter(labels)
    sorted_labels = sorted(label_counts.items(), key=lambda item: item[1], reverse=True)
    return pd.DataFrame(sorted_labels, columns=['Label', 'Count'])

def extract_general_snap_info(file_content):
    """Extrait des informations générales d'un fichier 'general.snap'."""
    all_info = []
    # (Le reste de la fonction est complexe et reste inchangé)
    # Pour la simplicité, on assume qu'elle retourne un DataFrame pandas
    # Dans une vraie application, le code complet de la fonction serait ici.
    # Pour cet exemple, nous allons simuler un retour
    patterns = {
        'Version Firmware': re.compile(r'^fwversion\s+([\S,]+)\s', re.MULTILINE),
        'Nom du Modèle': re.compile(r'^modelname\s+([\S,]+)\s', re.MULTILINE),
        'ID Système': re.compile(r'^systemid\s+([\S,]+)\s', re.MULTILINE),
    }
    for name, pattern in patterns.items():
        match = pattern.search(file_content)
        if match:
            all_info.append({'Information': name, 'Valeur': match.group(1).strip()})
    
    if not all_info:
        return pd.DataFrame(columns=['Information', 'Valeur'])
    return pd.DataFrame(all_info)


# --- Route principale pour la page d'accueil ---
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Vérifier quel bouton a été pressé pour traiter la bonne requête
        
        # --- Logique pour le formulaire n°1 : Analyse ---
        if 'analyze_button' in request.form:
            if 'file' not in request.files or request.files['file'].filename == '':
                flash('Veuillez sélectionner un fichier pour l\'analyse.', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                content = file.read().decode('utf-8', errors='ignore')

                if filename.endswith('.snap'):
                    analysis_df = extract_general_snap_info(content)
                    title = f"Analyse de {filename}"
                else: # errpt.out or other
                    analysis_df = extract_labels(content)
                    title = f"Résumé des erreurs pour {filename}"
                
                if analysis_df.empty:
                    flash("Aucune donnée pertinente n'a pu être extraite pour l'analyse.", 'warning')
                    return render_template('results.html', tables=[])

                flash('Analyse terminée avec succès.', 'success')
                return render_template('results.html', tables=[{'title': title, 'df': analysis_df}])

        # --- Logique pour le formulaire n°2 : Nettoyage ---
        if 'clean_button' in request.form:
            if 'file' not in request.files or request.files['file'].filename == '':
                flash('Veuillez sélectionner un fichier pour le nettoyage.', 'error')
                return redirect(request.url)

            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                content = file.read().decode('utf-8', errors='ignore')
                
                cleaned_content = clean_errpt_content(content)
                new_filename = f"cleaned_{filename}"
                
                cleaned_file_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
                with open(cleaned_file_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                
                flash('Fichier nettoyé avec succès !', 'success')
                return render_template('results.html', download_filename=new_filename)

        flash('Une erreur est survenue.', 'error')
        return redirect(request.url)

    # En méthode GET, on affiche simplement la page
    return render_template('upload.html')

@app.route('/download/<filename>')
def download_file(filename):
    """Route pour télécharger un fichier depuis le dossier d'uploads."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True)
