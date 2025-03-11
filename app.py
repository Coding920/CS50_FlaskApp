from datetime import datetime
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd


# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    stocks = db.execute("""
                        SELECT symbol, SUM(quantity) as shares
                        FROM history
                        WHERE user_id = ?
                        GROUP BY symbol
                        HAVING SUM(quantity) > 0""", session["user_id"])

    subtotal = 0
    for stock in stocks:
        company = lookup(stock["symbol"])
        stock["price"] = company["price"]
        stock["total"] = stock["price"] * stock["shares"]
        subtotal += stock["total"]

    cash_rows = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    cash = cash_rows[0]["cash"]
    total = cash + subtotal

    return render_template("index.html", stocks=stocks, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        # Setting up data
        date_time = datetime.now().replace(microsecond=0)
        user_table = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        user_info = user_table[0]
        form = request.form.to_dict()
        company = lookup(form["symbol"])

        # Ensuring proper data from user
        if form["symbol"] == "":
            return apology("Please add a Symbol", 400)
        elif form["shares"] == "":
            return apology("Please specify amount of shares", 400)
        elif company == None:
            return apology("Symbol doesn't exist/Error", 400)
        try:
            if int(form["shares"]) < 1:
                return apology("Number of Shares must be a positive integer", 400)
            elif int(form["shares"]) * company["price"] > user_info["cash"]:
                return apology("Not enough cash to complete the purchase", 400)
        except Exception:
            return apology("Number of shares must be an integer", 400)

        # Modifying and inserting everything into users and history tables respectively
        new_cash = user_info["cash"] - (company["price"] * int(form["shares"]))
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, session["user_id"])
        db.execute("INSERT INTO history VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], company["symbol"], company["price"], int(form["shares"]), date_time)
        flash("Bought!")
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    history = db.execute(""" SELECT symbol, price, quantity, date_time FROM history \
                                WHERE user_id = ? """, session["user_id"])
    for entry in history:
        if entry["quantity"] > 0:
            entry["direction"] = "Buy"
        else:
            entry["direction"] = "Sell"

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        # Data setup
        symbol = request.form.get("symbol")
        company = lookup(symbol)

        # Ensuring proper data from user
        if company == None:
            return apology("Invalid Symbol", 400)

        # Formatting
        company["price"] = usd(company["price"])

        return render_template("quoted.html", company=company)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":
        # Data from user into dict
        form = request.form.to_dict()

        # Ensuring proper data from user
        if not form["username"]:
            return apology("must provide username", 400)
        elif not form["password"]:
            return apology("must provide password", 400)

        usernames = db.execute("SELECT username FROM users")

        # Ensuring username isn't previously taken
        for pair in usernames:
            if pair["username"] == form["username"]:
                return apology("username taken", 400)

        if form["password"] != form["confirmation"]:
            return apology("passwords must match", 400)

        # Insert user into db
        db.execute("INSERT INTO users (username, hash) VALUES (?,?)",
                   form["username"], generate_password_hash(form["password"]))
        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    stocks = db.execute("""
                        SELECT symbol, SUM(quantity) as shares
                        FROM history
                        WHERE user_id = ?
                        GROUP BY symbol
                        HAVING SUM(quantity) > 0""", session["user_id"])

    if request.method == "POST":
        date_time = datetime.now().replace(microsecond=0)
        form = request.form.to_dict()
        if form["symbol"] == "":
            return apology("Must select a stock to sell", 400)
        elif form["shares"] == "":
            return apology("Must select a number of shares to sell", 400)

        company = lookup(form["symbol"])
        if company == None:
            return apology("Symbol doesn't exist/Error", 400)

        for stock in stocks:
            if stock["symbol"] == form["symbol"]:
                break
        else:
            return apology("Stock not owned", 400)

        try:
            if int(form["shares"]) < 1:
                return apology("Number of shares must be 1 or more", 400)
            elif int(form["shares"]) > stock["shares"]:  # If they want to sell more than they have
                return apology("You don't have enough shares", 400)
        except Exception:
            return apology("Number of shares must be a positive integer", 400)

        user_table = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        user_info = user_table[0]

        new_cash = user_info["cash"] + (company["price"] * int(form["shares"]))
        db.execute(""" UPDATE users SET cash = ? WHERE id = ?""", new_cash, session["user_id"])
        db.execute("INSERT INTO history VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], company["symbol"], company["price"], -int(form["shares"]), date_time)

        flash("Sold!")
        return redirect("/")
    else:
        return render_template("sell.html", stocks=stocks)


@app.route("/manage", methods=["GET", "POST"])
@login_required
def manage():

    if request.method == "POST":

        form = request.form.to_dict()
        if not form["direction"]:
            return apology("Please select either \"Deposit\" or \"Withdraw\"", 403)
        if form["direction"] != "deposit" and form["direction"] != "withdraw":
            return apology("You must choose either Deposit or Withdraw and nothing else", 403)
        if not form["amount"]:
            return apology("Must enter an amount to withdraw or deposit", 403)
        try:
            if int(form["amount"]) < 1:
                return apology("Amount must be one or more", 403)
        except Exception:
            return apology("Amount must be an integer", 403)

        table = db.execute(""" SELECT * FROM users WHERE id = ? """, session["user_id"])
        user_info = table[0]

        if form["direction"] == "deposit":
            new_cash = int(form["amount"]) + user_info["cash"]
            db.execute(""" UPDATE users SET cash=? WHERE id = ?""", new_cash, session["user_id"])
            flash("Deposited")
            return redirect("/")

        elif form["direction"] == "withdraw":
            new_cash = user_info["cash"] - int(form["amount"])
            if new_cash < 0:
                return apology("Requested withdrawl is more than balance", 403)
            db.execute(""" UPDATE users SET cash=? WHERE id = ?""", new_cash, session["user_id"])
            flash("Withdrawn!")
            return redirect("/")

    else:
        return render_template("manage.html")


# Command to create history table
""" CREATE TABLE history (
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    price NUMERIC NOT NULL,
    quantity INTEGER NOT NULL,
    date_time TEXT NOT NULL,
    FOREIGN KEY (user_id)
        REFERENCES users (id)
    ); """
