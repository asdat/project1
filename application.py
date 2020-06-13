import os, hashlib

from flask import Flask, render_template, request, redirect, url_for, session
from flask_session import Session
from sqlalchemy import create_engine, or_, asc
from sqlalchemy.orm import sessionmaker

from models import *

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"), echo=False)
db_session = sessionmaker(bind=engine)()


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session['user']:
        return redirect(url_for('home'))

    if request.method == 'POST':
        name = request.form.get("name")
        login = request.form.get("login")
        password = request.form.get("password")

        user = db_session.query(User).filter_by(login=login).first()
        if user:
            return render_template("register.html", message=f"User with login '{login}' already exists.", name=name, login=login, password=password)
        else:
            if not login or not password:
                return render_template("register.html", message="Login and password are required fields.", name=name, login=login, password=password)

            try:
                db.db_session.add(User(name=name, login=login, password=hashlib.sha1(password.encode()).hexdigest()))
                print(f"Added user {name} ({login}) by {password}.")
                db.db_session.commit()
            except Exception:
                return render_template("register.html", message="Error creating user, please try again later.", name=name, login=login, password=password)

        return redirect(url_for('login'))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session['user']:
        return redirect(url_for('home'))

    if request.method == 'POST':
        login = request.form.get("login")
        password = request.form.get("password")

        if not login:
            return render_template("login.html", message="Login is missing.")

        if not password:
            return render_template("login.html", message="Password is missing.")

        user = db_session.query(User).filter_by(login=login).first()
        if user.password == hashlib.sha1(password.encode()).hexdigest():
            session['user'] = user
            return redirect(url_for('home'))
        else:
            return render_template("login.html", message="Password incorrect.")

    return render_template("login.html")


@app.route("/logout", methods=["GET"])
def logout():
    session['user'] = None
    return redirect(url_for('home'))


@app.route("/book/<isbn>", methods=["GET"])
def book(isbn):
    if not session['user']:
        return redirect(url_for('home'))

    if not isbn:
        return render_template("book.html", message="No ISBN was provided")

    book_item = db_session.query(Book).filter_by(isbn=isbn).first()

    if not book_item:
        return render_template("book.html", message=f"No book fo ISBN {isbn} was found")

    return render_template("book.html", book=book_item)


@app.route("/search", methods=["GET"])
def search():
    if not session['user']:
        return redirect(url_for('home'))

    search = request.args.get("search")

    if not search:
        return render_template("search.html", message="No search was provided")

    books_list = db_session.query(Book).filter(or_(
        Book.isbn.like(f'%{search}%'),
        Book.title.like(f'%{search}%'),
        Book.author.like(f'%{search}%'))
    ).order_by(asc(Book.isbn))

    if books_list.count() > 0:
        return render_template("search.html", search=search, books=books_list)

    else:
        return render_template("search.html", search=search, message=f"No book for search request '{search}' was found")


