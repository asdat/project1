import os, hashlib, requests, json
from math import ceil

from flask import Flask, render_template, request, redirect, url_for, session
from flask_session import Session
from sqlalchemy import create_engine, or_, asc, func
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
            return render_template("register.html", message=f"User with login '{login}' already exists.", name=name,
                                   login=login, password=password)
        else:
            if not login or not password:
                return render_template("register.html", message="Login and password are required fields.", name=name,
                                       login=login, password=password)

            try:
                db.session.add(User(name=name, login=login, password=hashlib.sha1(password.encode()).hexdigest()))
                print(f"Added user {name} ({login}) by {password}.")
                db.session.commit()
            except Exception:
                return render_template("register.html", message="Error creating user, please try again later.",
                                       name=name, login=login, password=password)

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

    has_review = db_session.query(Review).filter_by(book_id=book_item.id).filter_by(user_id=session['user'].id).first()
    rating = db_session.query(func.avg(Review.rating)).filter_by(book_id=book_item.id).scalar()
    count = db_session.query(func.count(Review.rating)).filter_by(book_id=book_item.id).scalar()

    res = requests.get("https://www.goodreads.com/book/review_counts.json",
                       params={"key": os.getenv("GOODREADS_KEY"), "isbns": isbn})
    if res.status_code == 200:
        goodreads_rating = res.json().get('books', [{'average_rating': False}])[0].get('average_rating')
    else:
        goodreads_rating = None

    return render_template("book.html", book=book_item, has_review=has_review, rating=rating, count=count,
                           goodreads=goodreads_rating)


@app.route("/review", methods=["POST"])
def review():
    if not session['user']:
        return redirect(url_for('home'))

    rating = request.form.get("rating")
    comment = request.form.get("comment")
    isbn = request.form.get("isbn")

    book_item = db_session.query(Book).filter_by(isbn=isbn).first()
    if not book_item:
        return render_template("book.html", message=f"No book fo ISBN {isbn} was found")

    review_item = db_session.query(Review).filter_by(book_id=book_item.id).filter_by(user_id=session['user'].id).first()
    if review_item:
        return render_template("book.html", message="You already left review for this book")

    if not rating:
        return render_template("book.html", message="No rating was provided", book=book_item, rating=rating,
                               comment=comment)

    try:
        db.session.add(Review(rating=rating, comment=comment, book_id=book_item.id, user_id=session['user'].id))
        print(
            f"Added review {rating} with comment {comment} by {session['user'].name} ({session['user'].login}) for book {book_item.title} ({isbn}).")
        db.session.commit()
    except Exception:
        return render_template("book.html", message="Error creating review, please try again later.", book=book_item,
                               rating=rating, comment=comment)

    return redirect(url_for('book', isbn=isbn))


@app.route("/search", methods=["GET"])
def search():
    if not session['user']:
        return redirect(url_for('home'))

    per_page = 10
    page = int(request.args.get("page", 1))
    search = request.args.get("search")

    if not search:
        return render_template("search.html")

    query = db_session.query(Book).filter(or_(
        Book.isbn.like(f'%{search}%'),
        Book.title.like(f'%{search}%'),
        Book.author.like(f'%{search}%'))
    )
    count = query.count()
    books_list = query.order_by(asc(Book.isbn)).limit(per_page).offset(per_page * (page - 1))

    if books_list.count() > 0:
        return render_template("search.html", search=search, books=books_list, pages=ceil(count / per_page),
                               count=count, page=page, per_page=per_page)

    else:
        return render_template("search.html", search=search, message=f"No book for search request '{search}' was found")
