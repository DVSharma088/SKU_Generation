# main.py
import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length

# ----- App setup -----
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ----- Models -----
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)

class ProductType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Collection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Color(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class SKURecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(32), nullable=False)
    product_name = db.Column(db.String(150))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# ----- Forms -----
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Length(max=150)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Length(max=150)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Register')

# ----- Auth -----
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----- Utility: SKU building helpers -----
def first_letters_of_words(s: str, num_words: int, letters_each=1):
    """
    Return concatenation of first letters_each letters for each of the first num_words words.
    If s is empty or has fewer words, underscores are used to pad.
    """
    if not s:
        return ''.join(['_' * letters_each for _ in range(num_words)])
    parts = [p for p in s.strip().split() if p]
    out = []
    for i in range(num_words):
        if i < len(parts):
            part = parts[i]
            take = part[:letters_each].upper()
            # If word shorter than letters_each, pad with underscores
            take = take.ljust(letters_each, '_')
            out.append(take)
        else:
            out.append('_' * letters_each)
    return ''.join(out)

def first_n_letters(s: str, n: int):
    """
    Return first n letters of s uppercased, padded with underscores if shorter, or '_'*n if empty.
    """
    if not s:
        return '_' * n
    s = s.strip().upper()
    out = s[:n]
    if len(out) < n:
        out = out.ljust(n, '_')
    return out

def build_sku(product_type, collection, product_name, color, size):
    """
    Build SKU with the updated rules:
      - First 2 chars: first letter of up to 2 words of product_type => 2 chars
      - Next 2 chars: first letter of up to 2 words of collection => 2 chars
      - Next 3 chars: first 3 letters of product_name (pad with '_' if shorter) => 3 chars
      - Next 2 chars: first letter of up to 2 words of color => 2 chars
      - Last char: size (single character)
    Final SKU length = 10 (2+2+3+2+1). Internal pieces are padded with underscores as needed.
    Size is appended directly as last character (no underscore inserted before size).
    """
    pt = first_letters_of_words(product_type, num_words=2, letters_each=1)   # 2 chars
    coll = first_letters_of_words(collection, num_words=2, letters_each=1)    # 2 chars
    pname = first_n_letters(product_name, 3)                                 # 3 chars
    col = first_letters_of_words(color, num_words=2, letters_each=1)         # 2 chars
    size_char = str(size)[0] if size is not None else '_'

    sku_body = f"{pt}{coll}{pname}{col}"   # expected to be 9 chars (2+2+3+2)
    # Ensure body is exactly 9 chars (pad with underscores or truncate)
    if len(sku_body) < 9:
        sku_body = sku_body.ljust(9, '_')
    elif len(sku_body) > 9:
        sku_body = sku_body[:9]

    sku = f"{sku_body}{size_char}"  # final 10 chars: body (9) + size (1)
    return sku

# ----- Routes -----
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('create_data'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data.lower()).first()
        if existing:
            flash('User already exists. Please login.', 'warning')
            return redirect(url_for('login'))
        u = User(email=form.email.data.lower())
        u.set_password(form.password.data)
        db.session.add(u)
        db.session.commit()
        login_user(u)
        flash('Registered and logged in.', 'success')
        return redirect(url_for('create_data'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        u = User.query.filter_by(email=form.email.data.lower()).first()
        if u and u.check_password(form.password.data):
            login_user(u)
            flash('Logged in.', 'success')
            return redirect(url_for('create_data'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/create-data', methods=['GET', 'POST'])
@login_required
def create_data():
    """
    Create Data page: allows adding Product Type, Collection, Color.
    Product Name is NOT added here (user types Product Name in Generate SKU page).
    """
    if request.method == 'POST':
        what = request.form.get('what')
        value = request.form.get('value', '').strip()
        if not value:
            flash('Please enter a value.', 'warning')
            return redirect(url_for('create_data'))

        if what == 'product_type':
            db.session.add(ProductType(name=value, user_id=current_user.id))
        elif what == 'collection':
            db.session.add(Collection(name=value, user_id=current_user.id))
        elif what == 'color':
            db.session.add(Color(name=value, user_id=current_user.id))
        else:
            flash('Unknown type', 'danger')
            return redirect(url_for('create_data'))
        db.session.commit()
        flash(f'{what.replace("_"," ").title()} added.', 'success')
        return redirect(url_for('create_data'))

    # GET: load user's data
    product_types = ProductType.query.filter_by(user_id=current_user.id).all()
    collections = Collection.query.filter_by(user_id=current_user.id).all()
    colors = Color.query.filter_by(user_id=current_user.id).all()
    sku_records = SKURecord.query.filter_by(user_id=current_user.id).order_by(SKURecord.id.desc()).limit(10).all()
    return render_template('create_data.html',
                           product_types=product_types,
                           collections=collections,
                           colors=colors,
                           sku_records=sku_records)

@app.route('/generate-sku', methods=['GET', 'POST'])
@login_required
def generate_sku():
    # Load user's current options for dropdowns
    product_types = ProductType.query.filter_by(user_id=current_user.id).all()
    collections = Collection.query.filter_by(user_id=current_user.id).all()
    colors = Color.query.filter_by(user_id=current_user.id).all()
    sizes = ['1','2','3','4']

    if request.method == 'POST':
        # Product name is typed in as free text (required)
        product_name_text = request.form.get('product_name','').strip()
        ptype_id = request.form.get('product_type')
        coll_id = request.form.get('collection')
        color_id = request.form.get('color')
        size = request.form.get('size')

        if not product_name_text:
            flash('Please enter Product Name (type it).', 'warning')
            return redirect(url_for('generate_sku'))

        # Resolve selected IDs to names safely (ensure they belong to current user)
        ptype = None
        coll = None
        color = None
        try:
            if ptype_id:
                ptype = ProductType.query.filter_by(id=int(ptype_id), user_id=current_user.id).first()
        except (ValueError, TypeError):
            ptype = None
        try:
            if coll_id:
                coll = Collection.query.filter_by(id=int(coll_id), user_id=current_user.id).first()
        except (ValueError, TypeError):
            coll = None
        try:
            if color_id:
                color = Color.query.filter_by(id=int(color_id), user_id=current_user.id).first()
        except (ValueError, TypeError):
            color = None

        ptype_text = ptype.name if ptype else ''
        coll_text = coll.name if coll else ''
        color_text = color.name if color else ''

        sku = build_sku(ptype_text, coll_text, product_name_text, color_text, size)
        # Save generated sku record
        rec = SKURecord(sku=sku, product_name=product_name_text, user_id=current_user.id)
        db.session.add(rec)
        db.session.commit()
        flash(f'SKU generated: {sku}', 'success')
        return redirect(url_for('create_data'))

    return render_template('generate_sku.html',
                           product_types=product_types,
                           collections=collections,
                           colors=colors,
                           sizes=sizes)

# ----- CLI helper to init DB -----
@app.cli.command('init-db')
def init_db():
    db.create_all()
    print("DB initialized (tables created).")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
