from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///alergenos.db'
db = SQLAlchemy(app)

# Tabla de relación muchos a muchos
producto_alergeno = db.Table('producto_alergeno',
    db.Column('producto_id', db.Integer, db.ForeignKey('producto.id'), primary_key=True),
    db.Column('alergeno_id', db.Integer, db.ForeignKey('alergeno.id'), primary_key=True)
)

# Clase base para alérgenos
class Alergeno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255))
    
    def __str__(self):
        return f"{self.nombre}: {self.descripcion}"

# Clase derivada para productos usando herencia
class Producto(Alergeno):
    id = db.Column(db.Integer, db.ForeignKey('alergeno.id'), primary_key=True)
    lote = db.Column(db.String(50), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    alergenos_rel = db.relationship('Alergeno', secondary=producto_alergeno, backref='productos')
    
    def verificar_alergeno(self, alergeno_buscado):
        return alergeno_buscado in [a.nombre for a in self.alergenos_rel]
    
    def get_info(self):
        alergenos = ", ".join([a.nombre for a in self.alergenos_rel])
        return f"Producto: {self.nombre}\nLote: {self.lote}\nAlérgenos: {alergenos}"

# Clase para usuarios
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    productos = db.relationship('Producto', backref='usuario', lazy=True)

# Crear tablas en la base de datos e insertar datos iniciales
with app.app_context():
    db.create_all()
    
    # Insertar alérgenos comunes si no existen
    if not Alergeno.query.first():
        alergenos_comunes = [
            ("Gluten", "Proteína encontrada en trigo, centeno, cebada y avena."),
            ("Huevo", ""),
            ("Leche", ""),
            ("Soja", ""),
            ("Frutos secos", "Incluye almendras, avellanas, nueces, anacardos, etc."),
            ("Cacahuetes", ""),
            ("Mariscos", "")
        ]
        for nombre, desc in alergenos_comunes:
            db.session.add(Alergeno(nombre=nombre, descripcion=desc))
        db.session.commit()
    
    # Crear usuario predefinido
    if not Usuario.query.filter_by(username='admin').first():
        hashed_password = generate_password_hash('admin123', method='pbkdf2:sha256')
        admin_user = Usuario(username='admin', password=hashed_password)
        db.session.add(admin_user)
        db.session.commit()

# Clase principal que controla el flujo de la aplicación
class EscanerAlergenosApp:
    @staticmethod
    def get_alergenos_comunes():
        """Obtiene los alérgenos base """
        return Alergeno.query.filter(
            ~Alergeno.id.in_(db.session.query(Producto.id))
        ).all()
    
    @staticmethod
    def get_productos_usuario(usuario_id):
        return Producto.query.filter_by(usuario_id=usuario_id).all()

# Rutas de la aplicación
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('escanear'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = Usuario.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('escanear'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Las contraseñas no coinciden', 'danger')
            return redirect(url_for('register'))
        
        existing_user = Usuario.query.filter_by(username=username).first()
        if existing_user:
            flash('El nombre de usuario ya existe', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = Usuario(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registro exitoso. Por favor, inicia sesión.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/escanear', methods=['GET', 'POST'])
def escanear():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    app_control = EscanerAlergenosApp()
    productos = app_control.get_productos_usuario(session['user_id'])
    alergenos_comunes = app_control.get_alergenos_comunes()
    resultado = None
    
    if request.method == 'POST':
        producto_id = request.form['producto']
        alergeno_id = request.form['alergeno']
        
        producto = Producto.query.get(producto_id)
        alergeno = Alergeno.query.get(alergeno_id)
        
        if producto and alergeno:
            contiene = producto.verificar_alergeno(alergeno.nombre)
            resultado = {
                'producto': producto.nombre,
                'alergeno': alergeno.nombre,
                'contiene': contiene
            }
    
    return render_template('escanear.html', 
                         productos=productos, 
                         alergenos=alergenos_comunes,
                         resultado=resultado)

@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    alergenos_comunes = EscanerAlergenosApp.get_alergenos_comunes()
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        lote = request.form['lote']
        alergenos_ids = request.form.getlist('alergenos')
        
        # Crear nuevo producto
        nuevo_producto = Producto(
            nombre=nombre, 
            lote=lote,
            usuario_id=session['user_id']
        )
        db.session.add(nuevo_producto)
        db.session.commit()
        
        # Añadir relaciones con alérgenos
        for id in alergenos_ids:
            alergeno = Alergeno.query.get(id)
            if alergeno:
                nuevo_producto.alergenos_rel.append(alergeno)
        db.session.commit()
        
        flash('Producto registrado con éxito', 'success')
        return redirect(url_for('registrar'))
    
    return render_template('registrar.html', alergenos=alergenos_comunes)

if __name__ == '__main__':
    app.run(debug=True)