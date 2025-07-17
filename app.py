from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE_URL = "postgresql://gossip_user:wOKIGRFiLRjvGXm4HcK6yPEmIDjOwJZq@dpg-d1s9dvbuibrs73a5niv0-a.oregon-postgres.render.com/gossiping"

app = Flask(__name__)
app.secret_key = 'segredo'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def init_db():
    def get_db_connection():
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    
    conn = get_db_connection()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            content TEXT NOT NULL,
            image TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER REFERENCES users(id),
            post_id INTEGER REFERENCES posts(id),
            PRIMARY KEY (user_id, post_id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            post_id INTEGER REFERENCES posts(id),
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect('/login')

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    c = conn.cursor()

    c.execute('''
        SELECT posts.id, posts.content, posts.created_at, users.username, posts.image,
               (SELECT COUNT(*) FROM likes WHERE post_id = posts.id) AS like_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        ORDER BY posts.created_at DESC
    ''')
    posts = c.fetchall()

    post_comments = {}
    for post in posts:
        c.execute('''
            SELECT comments.content, comments.created_at, users.username
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.post_id = %s
            ORDER BY comments.created_at ASC
        ''', (post['id'],))
        post_comments[post['id']] = c.fetchall()

    conn.close()
    return render_template('index.html', posts=posts, comments=post_comments)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            error = "Usuário já existe!"
            conn.close()
            return render_template('register.html', error=error)
        conn.close()
        return redirect('/login')
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = username
            return redirect('/')
        else:
            error = "Usuário ou senha inválidos."

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/post', methods=['POST'])
def post():
    if 'user_id' not in session:
        return redirect('/login')

    content = request.form['content']
    image_path = None

    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            image_path = filepath

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    c = conn.cursor()
    c.execute("INSERT INTO posts (user_id, content, image) VALUES (%s, %s, %s)",
              (session['user_id'], content, image_path))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/like/<int:post_id>', methods=['POST'])
def like(post_id):
    if 'user_id' not in session:
        return redirect('/login')

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO likes (user_id, post_id) VALUES (%s, %s)", (session['user_id'], post_id))
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()  # já curtiu, ignora
    conn.close()
    return redirect('/')

@app.route('/comment/<int:post_id>', methods=['POST'])
def comment(post_id):
    if 'user_id' not in session:
        return redirect('/login')

    comment_text = request.form['comment']
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    c = conn.cursor()
    c.execute("INSERT INTO comments (user_id, post_id, content) VALUES (%s, %s, %s)",
              (session['user_id'], post_id, comment_text))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/user/<username>')
def user_profile(username):
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = c.fetchone()
    if not user:
        return "Usuário não encontrado"

    user_id = user['id']
    c.execute('''
        SELECT posts.content, posts.created_at, posts.image
        FROM posts
        WHERE user_id = %s
        ORDER BY created_at DESC
    ''', (user_id,))
    posts = c.fetchall()
    conn.close()
    return render_template('profile.html', username=username, posts=posts)

def reset_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    c = conn.cursor()
    
    try:
        c.execute("DROP TABLE IF EXISTS comments")
        c.execute("DROP TABLE IF EXISTS likes")
        c.execute("DROP TABLE IF EXISTS posts")
        c.execute("DROP TABLE IF EXISTS users")
        conn.commit()
        print("Tabelas apagadas com sucesso.")
    except Exception as e:
        print("Erro ao apagar tabelas:", e)
        conn.rollback()
    finally:
        conn.close()


if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # ⚠️ Executa a limpeza total do banco (comente essa linha após rodar 1 vez)
    #reset_db()

    # Recria as tabelas com estrutura correta
    init_db()

    # Inicia o servidor Flask
    app.run(debug=True)
