from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory
import sqlite3
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = 'segredo'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Banco de dados
def init_db():
    conn = sqlite3.connect('twitter.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    content TEXT NOT NULL,
                    image TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS likes (
                    user_id INTEGER,
                    post_id INTEGER,
                    PRIMARY KEY (user_id, post_id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    post_id INTEGER,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (post_id) REFERENCES posts(id)
                )''')
    
    conn.commit()
    conn.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('twitter.db')
    c = conn.cursor()

    c.execute('''
        SELECT posts.id, posts.content, posts.created_at, users.username, posts.image,
               (SELECT COUNT(*) FROM likes WHERE post_id = posts.id) AS like_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        ORDER BY posts.created_at DESC
    ''')
    posts = c.fetchall()

    # Pegar comentários para cada post
    post_comments = {}
    for post in posts:
        c.execute('''
            SELECT comments.content, comments.created_at, users.username
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.post_id = ?
            ORDER BY comments.created_at ASC
        ''', (post[0],))
        post_comments[post[0]] = c.fetchall()

    conn.close()
    return render_template('index.html', posts=posts, comments=post_comments)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])

        conn = sqlite3.connect('twitter.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
        except sqlite3.IntegrityError:
            return "Usuário já existe!"
        conn.close()
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('twitter.db')
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
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

    conn = sqlite3.connect('twitter.db')
    c = conn.cursor()
    c.execute("INSERT INTO posts (user_id, content, image) VALUES (?, ?, ?)",
              (session['user_id'], content, image_path))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/like/<int:post_id>', methods=['POST'])
def like(post_id):
    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('twitter.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO likes (user_id, post_id) VALUES (?, ?)", (session['user_id'], post_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect('/')

@app.route('/comment/<int:post_id>', methods=['POST'])
def comment(post_id):
    if 'user_id' not in session:
        return redirect('/login')

    comment = request.form['comment']
    conn = sqlite3.connect('twitter.db')
    c = conn.cursor()
    c.execute("INSERT INTO comments (user_id, post_id, content) VALUES (?, ?, ?)",
              (session['user_id'], post_id, comment))
    conn.commit()
    conn.close()
    return redirect('/')

@app.route('/user/<username>')
def user_profile(username):
    conn = sqlite3.connect('twitter.db')
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        return "Usuário não encontrado"

    user_id = user[0]
    c.execute('''
        SELECT posts.content, posts.created_at, posts.image
        FROM posts
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,))
    posts = c.fetchall()
    conn.close()
    return render_template('profile.html', username=username, posts=posts)

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    app.run(debug=True)
