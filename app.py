from flask import Flask, render_template, request, redirect
import pandas as pd
from datetime import datetime
import os
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# -----------------------
# Konfiguracija baze
# -----------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db = SQLAlchemy(app)

    # Definicija modela tabele
    class Order(db.Model):
        __tablename__ = "orders"
        id = db.Column(db.Integer, primary_key=True)
        kupac = db.Column(db.String(255))
        datum = db.Column(db.Date)
        vrsta = db.Column(db.String(255))
        kolicina = db.Column(db.Float)
        napomena = db.Column(db.String(255))

    with app.app_context():
        db.create_all()
else:
    db = None

# -----------------------
# Konfiguracija fajla
# -----------------------
FILE_PATH = "narudzbe.xlsx"
columns = ["Kupac/Farma", "Datum isporuke", "Vrsta hrane", "Količina (kg)", "Napomena"]

if not db:  # Fallback na Excel ako nema baze
    if os.path.exists(FILE_PATH):
        df = pd.read_excel(FILE_PATH)
        if "Datum isporuke" in df.columns:
            df["Datum isporuke"] = pd.to_datetime(df["Datum isporuke"], dayfirst=True).dt.date
        if "Napomena" not in df.columns:
            df["Napomena"] = ""
    else:
        df = pd.DataFrame(columns=columns)
        df.to_excel(FILE_PATH, index=False)

# -----------------------
# Funkcije
# -----------------------
def load_data():
    global df
    if db:
        with app.app_context():
            df = pd.read_sql_table("orders", con=db.engine)
    else:
        if os.path.exists(FILE_PATH):
            df = pd.read_excel(FILE_PATH)
            if "Datum isporuke" in df.columns:
                df["Datum isporuke"] = pd.to_datetime(df["Datum isporuke"], dayfirst=True).dt.date
            if "Napomena" not in df.columns:
                df["Napomena"] = ""
        else:
            df = pd.DataFrame(columns=columns)

def save_data():
    global df
    if db:
        with app.app_context():
            df.to_sql("orders", con=db.engine, if_exists="replace", index=False)
    else:
        df_to_save = df.copy()
        df_to_save["Datum isporuke"] = df_to_save["Datum isporuke"].apply(lambda x: x.strftime("%d.%m.%Y."))
        df_to_save.to_excel(FILE_PATH, index=False)

# -----------------------
# Helper funkcije
# -----------------------
def get_orders():
    orders = []
    for _, row in df.sort_values(by="Datum isporuke").iterrows():
        days_left = (row["Datum isporuke"] - datetime.today().date()).days
        if row["Napomena"] == "Završeno":
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
            "kupac": row["Kupac/Farma"],
            "datum": row["Datum isporuke"].strftime("%d.%m.%Y."),
            "vrsta": row["Vrsta hrane"],
            "kolicina": row["Količina (kg)"],
            "napomena": row["Napomena"],
            "tag": tag
        })
    return orders

def get_totals():
    return df[df["Napomena"] != "Završeno"].groupby("Vrsta hrane")["Količina (kg)"].sum().to_dict()

# -----------------------
# Rute
# -----------------------
@app.route("/")
def index():
    load_data()
    orders = get_orders()
    totals = get_totals()
    return render_template("index.html", orders=orders, totals=totals)

@app.route("/add", methods=["POST"])
def add_order():
    load_data()
    kupac = request.form.get("kupac")
    vrsta = request.form.get("vrsta")
    kolicina = request.form.get("kolicina", "").replace(",", ".")
    datum = request.form.get("datum")
    napomena = request.form.get("napomena", "")

    if not kupac or not vrsta or not kolicina or not datum:
        return redirect("/")

    try:
        kolicina = float(kolicina)
        datum_obj = datetime.strptime(datum, "%d.%m.%Y.").date()
    except:
        return redirect("/")

    new_order = {
        "Kupac/Farma": kupac,
        "Datum isporuke": datum_obj,
        "Vrsta hrane": vrsta,
        "Količina (kg)": kolicina,
        "Napomena": napomena
    }
    global df
    df = pd.concat([df, pd.DataFrame([new_order])], ignore_index=True)
    save_data()
    return redirect("/")

@app.route("/delete", methods=["POST"])
def delete_order():
    load_data()
    kupac_to_delete = request.form.get("delete")
    global df
    df = df[df["Kupac/Farma"] != kupac_to_delete]
    save_data()
    return redirect("/")

@app.route("/mark_done", methods=["POST"])
def mark_done():
    load_data()
    kupac_done = request.form.get("done")
    global df
    df.loc[df["Kupac/Farma"] == kupac_done, "Napomena"] = "Završeno"
    save_data()
    return redirect("/")

@app.route("/edit", methods=["POST"])
def edit_order():
    load_data()
    kupac_edit = request.form.get("kupac_edit")
    vrsta_edit = request.form.get("vrsta_edit")
    kolicina_edit = request.form.get("kolicina_edit").replace(",", ".")
    datum_edit = request.form.get("datum_edit")
    napomena_edit = request.form.get("napomena_edit")

    try:
        kolicina_edit = float(kolicina_edit)
        datum_obj = datetime.strptime(datum_edit, "%d.%m.%Y.").date()
    except:
        return redirect("/")

    global df
    df.loc[df["Kupac/Farma"] == kupac_edit, ["Vrsta hrane", "Količina (kg)", "Datum isporuke", "Napomena"]] = [
        vrsta_edit, kolicina_edit, datum_obj, napomena_edit
    ]
    save_data()
    return redirect("/")

# -----------------------
# Pokretanje aplikacije
# -----------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
