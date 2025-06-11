import re
from collections import Counter
import pandas as pd
import os
import logging
from flask import Flask, request, redirect, url_for, render_template, flash
from werkzeug.utils import secure_filename

# --- Configuration pour Render ---
# Le chemin du disque persistant sur Render est fourni par une variable d'environnement.
# On utilise '/var/data/uploads' comme chemin par défaut si la variable n'est pas définie.
UPLOAD_FOLDER = os.environ.get('RENDER_DISK_PATH', 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'out', 'snap'}

# Initialisation de l'application Flask
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Il est crucial de définir une clé secrète pour utiliser les 'flash messages'
app.secret_key = os.urandom(24) 

# Configuration du logging
logging.basicConfig(level=logging.INFO)

# Crée le dossier d'upload s'il n'existe pas.
# C'est particulièrement important pour la première utilisation du disque persistant.
if not os.path.exists(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER)
        logging.info(f"Dossier d'upload créé à l'emplacement : {UPLOAD_FOLDER}")
    except OSError as e:
        logging.error(f"Erreur lors de la création du dossier {UPLOAD_FOLDER}: {e}")


# --- Fonctions de traitement des fichiers (inchangées) ---

def allowed_file(filename):
    """Vérifie si l'extension du fichier est autorisée."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_labels(file_path):
    """Extrait les 'LABELs' d'un fichier et les compte."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
        
        label_pattern = re.compile(r'^LABEL:\s+(\S+)', re.MULTILINE)
        labels = label_pattern.findall(content)
        
        if not labels:
            return pd.DataFrame(columns=['Label', 'Count'])
            
        label_counts = Counter(labels)
        sorted_labels = sorted(label_counts.items(), key=lambda item: item[1], reverse=True)
        return pd.DataFrame(sorted_labels, columns=['Label', 'Count'])

    except Exception as e:
        logging.error(f"Erreur lors de l'extraction des labels : {e}")
        return pd.DataFrame(columns=['Label', 'Count'])

def extract_possible_fru(file_path):
    """Extrait les 'FRU' (Field Replaceable Unit) et leur localisation."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            
        fru_location_pattern = re.compile(r'FRU:\s+(\S+)\s+(\S+)')
        fru_location_data = fru_location_pattern.findall(content)
        
        if not fru_location_data:
            return pd.DataFrame(columns=['Possible FRU', 'Location', 'Count'])

        fru_location_df = pd.DataFrame(fru_location_data, columns=['Possible FRU', 'Location'])
        fru_location_counts = fru_location_df.value_counts().reset_index(name='Count')
        return fru_location_counts
        
    except Exception as e:
        logging.error(f"Erreur lors de l'extraction des FRUs : {e}")
        return pd.DataFrame(columns=['Possible FRU', 'Location', 'Count'])

def extract_general_snap_info(file_path):
    """Extrait des informations générales d'un fichier 'general.snap'."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            file_content = file.read()

        all_info = []
        patterns = {
            'Version Firmware': re.compile(r'^fwversion\s+([\S,]+)\s', re.MULTILINE),
            'Nom du Modèle': re.compile(r'^modelname\s+([\S,]+)\s', re.MULTILINE),
            'ID Système': re.compile(r'^systemid\s+([\S,]+)\s', re.MULTILINE),
            'Entrées Système (sys0)': re.compile(r'^sys0!system:(.+)$', re.MULTILINE),
        }
        for name, pattern in patterns.items():
            match = pattern.search(file_content)
            if match:
                all_info.append({'Catégorie': name, 'Valeur': match.group(1).strip()})
        
        component_pattern = re.compile(r'^(sissas\d+|fcs\d+|ent\d+|pdisk\d+|hdisk\d+)!([\w\d.?\-]+)', re.MULTILINE)
        components = component_pattern.findall(file_content)
        for component_type, component_value in components:
            all_info.append({'Catégorie': f'Composant ({component_type})', 'Valeur': component_value})
        
        if not all_info:
            return pd.DataFrame(columns=['Information', 'Valeur'])

        df_extracted_info = pd.DataFrame(all_info)
        df_extracted_info.columns = ['Information', 'Valeur']
        return df_extracted_info
        
    except Exception as e:
        logging.error(f"Erreur lors de l'extraction des infos SNAP : {e}")
        return pd.DataFrame(columns=['Information', 'Valeur'])


# --- Routes de l'application (inchangées) ---

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    """Gère la page d'upload et le traitement du fichier envoyé."""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Aucun fichier sélectionné dans la requête.', 'error')
            return redirect(request.url)
            
        file = request.files['file']
        
        if file.filename == '':
            flash('Aucun fichier sélectionné.', 'error')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Utilise le chemin du dossier d'upload configuré pour Render
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            try:
                file.save(file_path)
                logging.info(f"Fichier {filename} sauvegardé dans {file_path}.")
                flash(f"Fichier '{filename}' analysé avec succès.", 'success')

                if filename.endswith('.snap'):
                    snap_info_df = extract_general_snap_info(file_path)
                    return render_template('results.html', label_counts=snap_info_df, fru_location_counts=None)
                else:
                    label_counts_df = extract_labels(file_path)
                    fru_location_counts_df = extract_possible_fru(file_path)
                    return render_template('results.html', 
                                           label_counts=label_counts_df, 
                                           fru_location_counts=fru_location_counts_df)

            except Exception as e:
                logging.error(f"Une erreur est survenue : {e}")
                flash(f"Une erreur est survenue lors du traitement du fichier : {e}", "error")
                return redirect(request.url)

        else:
            flash('Type de fichier non autorisé. Veuillez utiliser .txt, .out, or .snap', 'error')
            return redirect(request.url)
            
    return render_template('upload.html')

# Ce bloc n'est exécuté que si on lance le script directement (`python app.py`)
# Gunicorn/Render n'utilisera pas cette partie.
if __name__ == '__main__':
    app.run(debug=True)
