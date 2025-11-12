from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pandas as pd
import os
from functools import wraps

app = Flask(__name__)

# -----------------------
# LOGIN / AUTH
# -----------------------
AUTH_USERNAME = "agromix"
AUTH_PASSWORD = "agromix007"
app.secret_key = os.environ.get("SESSION_SECRET", "change_this_secret_in_prod")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == AUTH_USERNAME and password == AUTH_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            error = "Neispravno korisničko ime ili lozinka."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

# -----------------------
# Konfiguracija baze (Neon / PostgreSQL)
# -----------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db = SQLAlchemy(app)
else:
    db = None

# -----------------------
# Model tabele (DB)
# -----------------------
if db:
    class Narudzba(db.Model):
        __tablename__ = "orders"
        id = db.Column(db.Integer, primary_key=True)
        kupac = db.Column(db.String(255), nullable=False)
        datum = db.Column(db.Date, nullable=False)
        vrsta = db.Column(db.String(255), nullable=False)
        kolicina = db.Column(db.Float, nullable=False)
        napomena = db.Column(db.String(255), default="")

        def __repr__(self):
            return f"<Narudzba {self.kupac} - {self.vrsta}>"

    with app.app_context():
        db.create_all()

# -----------------------
# Konfiguracija Excel fajla
# -----------------------
FILE_PATH = "narudzbe.xlsx"
columns = ["Kupac/Farma", "Datum isporuke", "Vrsta hrane", "Količina (kg)", "Napomena"]

if not db:
    if os.path.exists(FILE_PATH):
        df = pd.read_excel(FILE_PATH)
        if "Datum isporuke" in df.columns:
            df["Datum isporuke"] = pd.to_datetime(df["Datum isporuke"], dayfirst=True).dt.date
        if "Napomena" not in df.columns:
            df["Napomena"] = ""
    else:
        df = pd.DataFrame(columns=columns)
        df.to_excel(FILE_PATH, index=False)
else:
    df = pd.DataFrame(columns=columns)

# -----------------------
# Helper i save funkcije
# -----------------------
def load_data_for_display():
    global df
    if db:
        with app.app_context():
            try:
                q = Narudzba.query.order_by(Narudzba.id).all()
                rows = []
                for n in q:
                    rows.append({
                        "ID": n.id,
                        "Kupac/Farma": n.kupac,
                        "Datum isporuke": n.datum,
                        "Vrsta hrane": n.vrsta,
                        "Količina (kg)": n.kolicina,
                        "Napomena": n.napomena
                    })
                df = pd.DataFrame(rows, columns=["ID"] + columns)
            except Exception:
                df = pd.DataFrame(columns=["ID"] + columns)
    else:
        if os.path.exists(FILE_PATH):
            df = pd.read_excel(FILE_PATH)
            if "Datum isporuke" in df.columns:
                df["Datum isporuke"] = pd.to_datetime(df["Datum isporuke"], dayfirst=True).dt.date
            if "Napomena" not in df.columns:
                df["Napomena"] = ""
        else:
            df = pd.DataFrame(columns=columns)

def save_data_from_df_to_storage():
    global df
    if db:
        with app.app_context():
            try:
                Narudzba.query.delete()
                db.session.commit()
                for _, row in df.iterrows():
                    datum_val = row["Datum isporuke"]
                    if isinstance(datum_val, str):
                        try:
                            datum_parsed = datetime.strptime(datum_val, "%d.%m.%Y.").date()
                        except Exception:
                            datum_parsed = datetime.today().date()
                    else:
                        datum_parsed = datum_val
                    n = Narudzba(
                        kupac=row.get("Kupac/Farma", ""),
                        datum=datum_parsed,
                        vrsta=row.get("Vrsta hrane", ""),
                        kolicina=float(row.get("Količina (kg)", 0) or 0),
                        napomena=row.get("Napomena", "") or ""
                    )
                    db.session.add(n)
                db.session.commit()
            except Exception:
                db.session.rollback()
    else:
        df_to_save = df.copy()
        if "Datum isporuke" in df_to_save.columns:
            df_to_save["Datum isporuke"] = df_to_save["Datum isporuke"].apply(lambda x: x.strftime("%d.%m.%Y.") if not pd.isna(x) else "")
        df_to_save.to_excel(FILE_PATH, index=False)

def get_orders():
    load_data_for_display()
    orders = []
    today = datetime.today().date()
    if df.empty or "Datum isporuke" not in df.columns:
        return []
    df_sorted = df.sort_values(by="Datum isporuke")
    for _, row in df_sorted.iterrows():
        try:
            datum_val = row["Datum isporuke"]
            if isinstance(datum_val, str):
                datum_obj = datetime.strptime(datum_val, "%d.%m.%Y.").date()
            else:
                datum_obj = datum_val
            days_left = (datum_obj - today).days
        except Exception:
            datum_obj = today
            days_left = 0

        if row.get("Napomena", "") == "Završeno":
            tag = "done"
        elif days_left < 0:
            tag = "expired"
        elif days_left < 4:
            tag = "urgent"
        elif days_left <= 7:
            tag = "soon"
        else:
            tag = "normal"

        orders.append({
            "id": row.get("ID", ""),
            "kupac": row.get("Kupac/Farma", ""),
            "datum": datum_obj.strftime("%d.%m.%Y."),
            "vrsta": row.get("Vrsta hrane", ""),
            "kolicina": row.get("Količina (kg)", ""),
            "napomena": row.get("Napomena", ""),
            "tag": tag
        })
    return orders

def get_totals():
    load_data_for_display()
    if df.empty or "Vrsta hrane" not in df.columns:
        return {}
    try:
        totals = df[df["Napomena"] != "Završeno"].groupby("Vrsta hrane")["Količina (kg)"].sum().to_dict()
        return totals
    except Exception:
        return {}

# -----------------------
# Rute
# -----------------------
@app.route("/")
@login_required
def index():
    orders = get_orders()
    totals = get_totals()
    return render_template("index.html", orders=orders, totals=totals)

@app.route("/add", methods=["POST"])
@login_required
def add_order():
    kupac = request.form.get("kupac")
    vrsta = request.form.get("vrsta")
    kolicina = request.form.get("kolicina", "").replace(",", ".")
    datum = request.form.get("datum")
    napomena = request.form.get("napomena", "")

    if not kupac or not vrsta or not kolicina or not datum:
        return redirect("/")

    try:
        kolicina_val = float(kolicina)
        datum_obj = datetime.strptime(datum, "%d.%m.%Y.").date()
    except Exception:
        return redirect("/")

    if db:
        try:
            novi = Narudzba(
                kupac=kupac,
                vrsta=vrsta,
                kolicina=kolicina_val,
                datum=datum_obj,
                napomena=napomena
            )
            db.session.add(novi)
            db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        global df
        new_order = {
            "Kupac/Farma": kupac,
            "Datum isporuke": datum_obj,
            "Vrsta hrane": vrsta,
            "Količina (kg)": kolicina_val,
            "Napomena": napomena
        }
        df = pd.concat([df, pd.DataFrame([new_order])], ignore_index=True)
        save_data_from_df_to_storage()
    return redirect("/")

@app.route("/delete", methods=["POST"])
@login_required
def delete_order():
    id_to_delete = request.form.get("id")
    if db:
        try:
            if id_to_delete:
                obj = Narudzba.query.get(int(id_to_delete))
                if obj:
                    db.session.delete(obj)
                    db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        global df
        if id_to_delete:
            try:
                id_int = int(id_to_delete)
                if 0 <= id_int < len(df):
                    df = df.drop(df.index[id_int])
                    df.reset_index(drop=True, inplace=True)
                    save_data_from_df_to_storage()
            except Exception:
                pass
    return redirect("/")

@app.route("/mark_done", methods=["POST"])
@login_required
def mark_done():
    id_done = request.form.get("id")
    if db:
        try:
            if id_done:
                obj = Narudzba.query.get(int(id_done))
                if obj:
                    obj.napomena = "Završeno"
                    db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        global df
        try:
            id_int = int(id_done)
            if 0 <= id_int < len(df):
                df.loc[id_int, "Napomena"] = "Završeno"
                save_data_from_df_to_storage()
        except Exception:
            pass
    return redirect("/")

@app.route("/edit", methods=["POST"])
@login_required
def edit_order():
    id_edit = request.form.get("id_edit")
    kupac_edit = request.form.get("kupac_edit")
    vrsta_edit = request.form.get("vrsta_edit")
    kolicina_edit = request.form.get("kolicina_edit", "").replace(",", ".")
    datum_edit = request.form.get("datum_edit")
    napomena_edit = request.form.get("napomena_edit", "")

    try:
        kolicina_edit_val = float(kolicina_edit)
        datum_obj = datetime.strptime(datum_edit, "%d.%m.%Y.").date()
    except Exception:
        return redirect("/")

    if db:
        try:
            if id_edit:
                obj = Narudzba.query.get(int(id_edit))
            if obj:
                obj.kupac = kupac_edit
                obj.vrsta = vrsta_edit
                obj.kolicina = kolicina_edit_val
                obj.datum = datum_obj
                obj.napomena = napomena_edit
                db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        global df
        try:
            id_int = int(id_edit)
            if 0 <= id_int < len(df):
                df.loc[id_int, ["Kupac/Farma", "Vrsta hrane", "Količina (kg)", "Datum isporuke", "Napomena"]] = [
                    kupac_edit, vrsta_edit, kolicina_edit_val, datum_obj, napomena_edit
                ]
                save_data_from_df_to_storage()
        except Exception:
            pass
    return redirect("/")

# -----------------------
# Pokretanje aplikacije
# -----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
