import os, hashlib, requests, datetime
from math import ceil

from flask import Flask, flash, render_template, request, redirect, url_for, session
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"), echo=False)
db = scoped_session(sessionmaker(engine))
per_page = 10


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get('user_id'):
        flash("You already logged in")
        return redirect(url_for('home'))

    if request.method == 'POST':
        name = request.form.get("name")
        login = request.form.get("login")
        password = request.form.get("password")

        user = db.execute("SELECT id FROM users WHERE login = :login", {"login": login}).fetchone()
        if user:
            return render_template("register.html", message=f"User with login '{login}' already exists.", name=name,
                                   login=login, password=password)
        else:
            if not login or not password:
                return render_template("register.html", message="Login and password are required fields.", name=name,
                                       login=login, password=password)

            try:
                db.execute("INSERT INTO users (name, login, password) VALUES (:name, :login, :password)",
                           {"name": name, "login": login,
                            "password": hashlib.sha1(password.encode()).hexdigest()})
                db.commit()
                flash("Registered successful")
            except Exception:
                return render_template("register.html", message="Error creating user, please try again later.",
                                       name=name, login=login, password=password)

        return redirect(url_for('login'))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get('user_id'):
        flash("You already logged in")
        return redirect(url_for('home'))

    if request.method == 'POST':
        login = request.form.get("login")
        password = request.form.get("password")

        if not login:
            return render_template("login.html", message="Login is missing.", login=login, password=password)

        if not password:
            return render_template("login.html", message="Password is missing.", login=login, password=password)

        user = db.execute("SELECT id, name, login, password FROM users WHERE login = :login",
                          {"login": login}).fetchone()
        if user.password == hashlib.sha1(password.encode()).hexdigest():
            session['user_id'] = user.id
            session['user_name'] = f"{user.name} ({user.login})"
            return redirect(url_for('home'))
        else:
            return render_template("login.html", message="Password incorrect.", login=login, password=password)

    return render_template("login.html")


@app.route("/logout", methods=["GET"])
def logout():
    session['user_id'] = None
    session['user_name'] = ''
    return redirect(url_for('home'))


@app.route("/book/<isbn>", methods=["GET"])
def book(isbn):
    if not session.get('user_id'):
        flash("Please login first")
        return redirect(url_for('home'))

    if not isbn:
        return render_template("book.html", message="No ISBN was provided")

    book_item = db.execute("SELECT id, title, isbn, author, year FROM books WHERE isbn = :isbn",
                           {"isbn": isbn}).fetchone()

    if not book_item:
        return render_template("404.html"), 404

    book_reviews = db.execute(
        "SELECT r.rating, r.comment, u.name, u.login "
        "FROM reviews AS r "
        "INNER JOIN users AS u ON u.id = r.user_id "
        "WHERE r.book_id = :book_id",
        {"book_id": book_item.id}).fetchall()

    has_review = db.execute(
        "SELECT COUNT(*) as cnt FROM reviews WHERE book_id = :book_id AND user_id = :user_id",
        {"user_id": session['user_id'], "book_id": book_item.id}).fetchone().cnt > 0

    rating = db.execute(
        "SELECT AVG(rating) as average, COUNT(*) as count FROM reviews WHERE book_id = :book_id",
        {"book_id": book_item.id}).fetchone()

    res = requests.get("https://www.goodreads.com/book/review_counts.json",
                       params={"key": os.getenv("GOODREADS_KEY"), "isbns": isbn})
    goodreads = {
        'count': 0,
        'rating': 0
    }

    if res.status_code == 200:
        data = res.json().get('books')[0]
        goodreads['count'] = data.get('work_ratings_count')
        goodreads['rating'] = data.get('average_rating')

    return render_template("book.html", book=book_item, has_review=has_review, reviews=book_reviews, rating=rating,
                           goodreads=goodreads)


@app.route("/api/<isbn>", methods=["GET"])
def api(isbn):
    book_item = db.execute("SELECT id, title, isbn, author, year FROM books WHERE isbn = :isbn",
                           {"isbn": isbn}).fetchone()

    if not book_item:
        return {'error': f"no book for ISBN {isbn} was found"}, 404

    rating = db.execute(
        "SELECT AVG(rating) as average, COUNT(*) as count FROM reviews WHERE book_id = :book_id",
        {"book_id": book_item.id}).fetchone()

    return {
        'title': book_item.title,
        'author': book_item.author,
        'year': book_item.year,
        'isbn': book_item.isbn,
        'review_count': rating.count,
        'average_score': float(round(rating.average, 2))
    }


@app.route("/review", methods=["POST"])
def review():
    if not session.get('user_id'):
        flash("Please login first")
        return redirect(url_for('home'))

    rating = request.form.get("rating")
    comment = request.form.get("comment")
    isbn = request.form.get("isbn")

    book_item = db.execute("SELECT id, title, isbn, author, year FROM books WHERE isbn = :isbn",
                           {"isbn": isbn}).fetchone()
    if not book_item:
        return render_template("book.html", message=f"No book fo ISBN {isbn} was found")

    has_review = db.execute(
        "SELECT COUNT(*) as cnt FROM reviews WHERE book_id = :book_id AND user_id = :user_id",
        {"user_id": session['user_id'], "book_id": book_item.id}).fetchone().cnt > 0
    if has_review:
        return render_template("book.html", message="You already left review for this book")

    if not rating:
        return render_template("book.html", message="No rating was provided", book=book_item, rating=rating,
                               comment=comment)

    try:
        db.execute("INSERT INTO reviews (rating, comment, book_id, user_id, created_at) "
                   "VALUES (:rating, :comment, :book_id, :user_id, :created_ad)",
                   {"rating": rating, "comment": comment, "book_id": book_item.id,
                    "user_id": session['user_id'], "created_ad": datetime.datetime.utcnow()})

        flash(
            f"Added review {rating} with comment {comment} by {session['user_name']} for book {book_item.title} ({isbn}).")
        db.commit()
    except Exception:
        return render_template("book.html", message="Error creating review, please try again later.", book=book_item,
                               rating=rating, comment=comment)

    return redirect(url_for('book', isbn=isbn))


@app.route("/reviews", methods=["GET"])
def reviews():
    if not session.get('user_id'):
        flash("Please login first")
        return redirect(url_for('home'))

    page = int(request.args.get("page", 1))
    results_count = db.execute("SELECT COUNT(*) as cnt "
                               "FROM reviews "
                               "WHERE user_id = :user_id",
                               {"user_id": session.get('user_id')}).fetchone().cnt

    book_reviews = db.execute(
        "SELECT r.rating, r.comment, r.created_at, b.title, b.author, b.isbn, b.year "
        "FROM reviews AS r "
        "INNER JOIN books AS b ON b.id = r.book_id "
        "WHERE r.user_id = :user_id "
        "LIMIT :limit OFFSET :offset",
        {"user_id": session.get('user_id'), "offset": per_page * (page - 1), "limit": per_page}
    ).fetchall()

    rating = db.execute(
        "SELECT AVG(rating) as average, COUNT(*) as count FROM reviews WHERE user_id = :user_id",
        {"user_id": session.get('user_id')}).fetchone()

    return render_template("reviews.html", reviews=book_reviews, rating=rating, pages=ceil(results_count / per_page),
                           count=results_count, page=page, per_page=per_page)


@app.route("/search", methods=["GET"])
def search():
    if not session.get('user_id'):
        flash("Please login first")
        return redirect(url_for('home'))

    page = int(request.args.get("page", 1))
    search = request.args.get("search")

    if not search:
        return render_template("search.html")

    results_count = db.execute("SELECT COUNT(id) as cnt "
                               "FROM books "
                               "WHERE isbn LIKE :search OR title LIKE :search OR author LIKE :search",
                               {"search": f"%{search}%"}).fetchone().cnt

    books_list = db.execute("SELECT title, isbn, author, year "
                            "FROM books "
                            "WHERE isbn LIKE :search OR title LIKE :search OR author LIKE :search "
                            "ORDER BY year ASC, isbn ASC "
                            "LIMIT :limit OFFSET :offset",
                            {"search": f"%{search}%", "offset": per_page * (page - 1), "limit": per_page}
                            ).fetchall()

    if results_count > 0:
        return render_template("search.html", search=search, books=books_list, pages=ceil(results_count / per_page),
                               count=results_count, page=page, per_page=per_page)

    else:
        return render_template("search.html", search=search, message=f"No book for search request '{search}' was found")
