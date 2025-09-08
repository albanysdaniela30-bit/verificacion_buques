from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "buques_secret_key"

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

DB_FILE = "buques.db"
EXCEL_FILE = "buques.xlsx"

USUARIO = "autoridad acuática"
CONTRASENA = "buquesvzla"

# ----------------- Usuario -----------------
class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# ----------------- Inicializar BD -----------------
def inicializar_bd():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS buques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            matricula TEXT UNIQUE,
            tipo_buque TEXT,
            propietario TEXT,
            cedula TEXT,
            documento TEXT,
            fecha_expedicion TEXT,
            fecha_refrendo TEXT,
            fecha_vencimiento TEXT
        )
    ''')
    conn.commit()
    conn.close()

def cargar_excel():
    df = pd.read_excel(EXCEL_FILE, engine='openpyxl')
    for col in ['fecha_expedicion','fecha_refrendo','fecha_vencimiento']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
    siglas = {
        "PE":"PESCA","CA":"CARGA","SE":"SERVICIO","RE":"RECREO",
        "TU":"TURISMO","AC":"ACCESORIO DE NAVEGACIÓN","PJ":"PASAJES","DE":"DEPORTIVO"
    }
    tipo_list = []
    for matricula in df['matricula']:
        try:
            codigo = matricula.split("-")[1]
            tipo_list.append(siglas.get(codigo, "DESCONOCIDO"))
        except:
            tipo_list.append("DESCONOCIDO")
    df['tipo_buque'] = tipo_list
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for _, row in df.iterrows():
        c.execute('''
            INSERT OR IGNORE INTO buques 
            (nombre, matricula, tipo_buque, propietario, cedula, documento, fecha_expedicion, fecha_refrendo, fecha_vencimiento)
            VALUES (?,?,?,?,?,?,?,?,?)
        ''', (
            row.get('nombre'),
            row.get('matricula'),
            row.get('tipo_buque'),
            row.get('propietario'),
            row.get('cedula'),
            "Licencia de navegación",
            str(row.get('fecha_expedicion')),
            str(row.get('fecha_refrendo')) if pd.notnull(row.get('fecha_refrendo')) else None,
            str(row.get('fecha_vencimiento'))
        ))
    conn.commit()
    conn.close()

# ----------------- Verificar Refrendo -----------------
def verificar_refrendo(fecha_expedicion, fecha_refrendo, fecha_vencimiento=None):
    hoy = datetime.today().date()
    if not fecha_expedicion:
        return "No válido", "Fecha de expedición inválida"
    
    fecha_exped = datetime.strptime(fecha_expedicion, "%Y-%m-%d").date()
    
    # Convertir fecha de vencimiento si existe
    if fecha_vencimiento:
        fecha_venc = datetime.strptime(fecha_vencimiento, "%Y-%m-%d").date()
    else:
        fecha_venc = fecha_exped + timedelta(days=365+90)  # fallback si no hay vencimiento
    
    # Calcular límite de refrendo (expedición + 1 año + 90 días)
    limite = fecha_exped + timedelta(days=365+90)
    
    if not fecha_refrendo:
        # Sin refrendo, verificar si ya pasó el límite
        if hoy > limite:
            return "Vencido", "Debe renovar su Licencia de Navegación"
        else:
            return "Vigente", "Debe realizar el reconocimiento anual (refrendo) ante la autoridad acuática"
    else:
        fecha_ref = datetime.strptime(fecha_refrendo, "%Y-%m-%d").date()
        
        # Estado según fecha de vencimiento real
        if hoy > fecha_venc:
            estado = "Vencido"
            nota = "Debe renovar su Licencia de Navegación"  # Ajuste solicitado
        else:
            estado = "Vigente"
            # Nota según refrendo
            if fecha_ref <= limite:
                nota = "Refrendo dentro del plazo"
            else:
                nota = "Refrendo fuera de plazo"
        
        return estado, nota

# ----------------- Página Principal -----------------
@app.route("/", methods=["GET","POST"])
def index():
    resultado = None
    nota_refrendo = ""
    if request.method == "POST":
        matricula = request.form.get("matricula","").strip().upper()
        if len(matricula.split("-")) != 3:
            flash("Ingrese una matrícula correcta", "error")
            return redirect(url_for("index"))
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM buques WHERE matricula = ?", (matricula,))
        buque = c.fetchone()
        conn.close()
        if not buque:
            flash("No existe ningún buque asociado a esa matrícula", "error")
        else:
            resultado = dict(buque)
            resultado["fecha_refrendo"] = buque['fecha_refrendo'] if buque['fecha_refrendo'] else ""
            estado, nota_refrendo = verificar_refrendo(buque['fecha_expedicion'], buque['fecha_refrendo'])
            resultado["estado"] = estado
    return render_template("index.html", resultado=resultado, nota_refrendo=nota_refrendo)

# ----------------- Login -----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario","").strip().lower()
        contrasena = request.form.get("contrasena","").strip()
        if usuario == USUARIO.lower() and contrasena == CONTRASENA:
            user = User(1)
            login_user(user)
            flash("Inicio de sesión exitoso", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Usuario o contraseña incorrecta", "error")
    return render_template("login.html")

# ----------------- Logout -----------------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Has cerrado sesión", "success")
    return redirect(url_for("index"))

# ----------------- Dashboard -----------------
@app.route("/dashboard")
@login_required
def dashboard():
    buscar = request.args.get('buscar', '').strip()
    tipo_filtro = request.args.get('tipo_buque', '').strip()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    query = "SELECT * FROM buques"
    condiciones = []
    params = []
    if buscar:
        condiciones.append("(matricula LIKE ? OR cedula LIKE ?)")
        params.extend([f"%{buscar}%", f"%{buscar}%"])
    if tipo_filtro:
        condiciones.append("tipo_buque = ?")
        params.append(tipo_filtro)
    if condiciones:
        query += " WHERE " + " AND ".join(condiciones)
    c.execute(query, params)
    buques = c.fetchall()
    c.execute("SELECT DISTINCT tipo_buque FROM buques")
    tipos_buque = [row['tipo_buque'] for row in c.fetchall()]
    conn.close()
    return render_template("dashboard.html", buques=buques, tipos_buque=tipos_buque)

# ----------------- Agregar Buque -----------------
@app.route("/agregar_buque", methods=["GET","POST"])
@login_required
def agregar_buque():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        matricula = request.form.get("matricula").upper()
        propietario = request.form.get("propietario")
        cedula = request.form.get("cedula")
        fecha_expedicion = request.form.get("fecha_expedicion")
        fecha_refrendo = request.form.get("fecha_refrendo") or None
        fecha_vencimiento = request.form.get("fecha_vencimiento")
        siglas = {
            "PE":"PESCA","CA":"CARGA","SE":"SERVICIO","RE":"RECREO",
            "TU":"TURISMO","AC":"ACCESORIO DE NAVEGACIÓN","PJ":"PASAJES","DE":"DEPORTIVO"
        }
        try:
            codigo = matricula.split("-")[1]
            tipo_buque = siglas.get(codigo, "DESCONOCIDO")
        except:
            tipo_buque = "DESCONOCIDO"
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO buques 
            (nombre, matricula, tipo_buque, propietario, cedula, documento, fecha_expedicion, fecha_refrendo, fecha_vencimiento)
            VALUES (?,?,?,?,?,?,?,?,?)
        ''',(nombre, matricula, tipo_buque, propietario, cedula, "Licencia de navegación", fecha_expedicion, fecha_refrendo, fecha_vencimiento))
        conn.commit()
        conn.close()
        flash("Buque agregado correctamente", "success")
        return redirect(url_for("dashboard"))
    return render_template("agregar_buque.html", buque=None)

# ----------------- Editar Buque -----------------
@app.route("/editar_buque/<int:id>", methods=["GET","POST"])
@login_required
def editar_buque(id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM buques WHERE id = ?", (id,))
    buque = c.fetchone()
    if request.method == "POST":
        nombre = request.form.get("nombre")
        propietario = request.form.get("propietario")
        cedula = request.form.get("cedula")
        fecha_expedicion = request.form.get("fecha_expedicion")
        fecha_refrendo = request.form.get("fecha_refrendo") or None
        fecha_vencimiento = request.form.get("fecha_vencimiento")
        c.execute('''
            UPDATE buques SET nombre=?, propietario=?, cedula=?, fecha_expedicion=?, fecha_refrendo=?, fecha_vencimiento=?
            WHERE id=?
        ''', (nombre, propietario, cedula, fecha_expedicion, fecha_refrendo, fecha_vencimiento, id))
        conn.commit()
        conn.close()
        flash("Buque actualizado correctamente", "success")
        return redirect(url_for("dashboard"))
    conn.close()
    return render_template("agregar_buque.html", buque=buque)

# ----------------- Run App -----------------
if __name__ == "__main__":
    inicializar_bd()
    cargar_excel()
    app.run(debug=True)
