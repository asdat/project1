import os, datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    login = db.Column(db.String, unique=True, nullable=False)
    password = db.Column(db.String, nullable=False)

    reviews = relationship("Review", back_populates="user")


class Book(db.Model):
    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True)
    isbn = db.Column(db.String, nullable=False)
    title = db.Column(db.String, nullable=False)
    author = db.Column(db.String, nullable=False)
    year = db.Column(db.Integer, nullable=False)

    reviews = relationship("Review", back_populates="book", order_by="desc(Review.created_at)")


class Review(db.Model):
    __tablename__ = "reviews"

    rating = db.Column(db.SmallInteger)
    comment = db.Column(db.String)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="reviews")
    book = relationship("Book", back_populates="reviews")