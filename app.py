from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pandas as pd
import os

app = Flask(__name__)

# -----------------------
# Konfiguracija baze (Neon / PostgreSQL)
# -----------------------
# Render: postavi env var DATABASE_URL na tvoj Neon connection string
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db = SQLAlchemy(app)
else:
    db = None

# -----------------------
# Model tabele (samo ako imamo DB)
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

    # Kreiraj tablu ako ne postoji
    with app.app_context():
        db.create_all()

# -----------------------
# Konfiguracija fajla (Excel fallback)
# -----------------------
FILE_PATH = "narudzbe.xlsx"
columns = ["Kupac/Farma", "Datum isporuke", "Vrsta hrane", "Količina (kg)", "Napomena"]

# Ako nema DB, učitaj Excel ili ga kreiraj
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
    # Definišemo df varijablu da izbjegnemo KeyError ako se negdje referencira
    df = pd.DataFrame(columns=columns)

# -----------------------
# Helper: učitavanje podataka u df var (ako treba za templating)
# -----------------------
def load_data_for_display():
    """
    Vrati pandas DataFrame koji koristi template. Ako imamo DB, povuci iz DB.
    Ako nemamo DB, koristi lokalni Excel df.
    """
    global df
    if db:
        # Učitavanje iz baze u pandas DataFrame radi iste templating logike kao prije
        with app.app_context():
            try:
                q = Narudzba.query.order_by(Narudzba.datum).all()
                rows = []
                for n in q:
                    rows.append({
                        "Kupac/Farma": n.kupac,
                        "Datum isporuke": n.datum,
                        "Vrsta hrane": n.vrsta,
                        "Količina (kg)": n.kolicina,
                        "Napomena": n.napomena
                    })
                df = pd.DataFrame(rows, columns=columns)
            except Exception:
                # Ako DB pukne, fallback na prazan DataFrame sa kolonama
                df = pd.DataFrame(columns=columns)
    else:
        # df već učitan iz fajla ili inicijalizovan
        if os.path.exists(FILE_PATH):
            df = pd.read_excel(FILE_PATH)
            if "Datum isporuke" in df.columns:
                df["Datum isporuke"] = pd.to_datetime(df["Datum isporuke"], dayfirst=True).dt.date
            if "Napomena" not in df.columns:
                df["Napomena"] = ""
        else:
            df = pd.DataFrame(columns=columns)

# -----------------------
# Funkcije za čuvanje (Excel ili DB)
# -----------------------
def save_data_from_df_to_storage():
    """
    Ako koristimo DB, upiši df u DB (replace-once). Ako koristimo Excel, upiši u FILE_PATH.
    Napomena: kad koristimo DB, normalno koristimo ORM operacije umjesto masovnog replace,
    ali zadržavam jednostavnost: sync df -> DB radi ako treba.
    """
    global df
    if db:
        # Sync df u DB: jednostavan način je da obrišemo sve i upišemo iz df (ako dataset nije veliki)
        # Ali da budemo sigurni, radimo to unutar transakcije i rollback na grešku.
        with app.app_context():
            try:
                # Obriši sve stare zapise (oprez: ovo briše sve, koristi samo ako želiš "replace" ponašanje)
                Narudzba.query.delete()
                db.session.commit()
                # Insert nove
                for _, row in df.iterrows():
                    # row["Datum isporuke"] je datetime.date ili string; normaliziraj
                    datum_val = row["Datum isporuke"]
                    if isinstance(datum_val, str):
                        # pokuša parseirati oblik dd.mm.yyyy.
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
        # Save to excel, kao prije
        df_to_save = df.copy()
        if "Datum isporuke" in df_to_save.columns:
            df_to_save["Datum isporuke"] = df_to_save["Datum isporuke"].apply(lambda x: x.strftime("%d.%m.%Y.") if not pd.isna(x) else "")
        df_to_save.to_excel(FILE_PATH, index=False)

# -----------------------
# Helper funkcije za view
# -----------------------
def get_orders():
    """
    Vrati listu narudžbi formiranu iz df (koji je sinhronizovan sa DB ako DB postoji).
    """
    load_data_for_display()
    orders = []
    today = datetime.today().date()
    # Ako nema kolone ili je prazan, vratiti praznu listu
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
def index():
    orders = get_orders()
    totals = get_totals()
    return render_template("index.html", orders=orders, totals=totals)

@app.route("/add", methods=["POST"])
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
        # Ubaci direktno u DB, sa try/except i rollback
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
        # Excel fallback
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
def delete_order():
    # prvo probaj po id (ako front-end prosledjuje), fallback na kupac
    id_to_delete = request.form.get("id")
    kupac_to_delete = request.form.get("delete")

    if db:
        try:
            if id_to_delete:
                obj = Narudzba.query.get(int(id_to_delete))
                if obj:
                    db.session.delete(obj)
                    db.session.commit()
            elif kupac_to_delete:
                obj = Narudzba.query.filter_by(kupac=kupac_to_delete).first()
                if obj:
                    db.session.delete(obj)
                    db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        global df
        if kupac_to_delete:
            df = df[df["Kupac/Farma"] != kupac_to_delete]
            save_data_from_df_to_storage()
    return redirect("/")

@app.route("/mark_done", methods=["POST"])
def mark_done():
    id_done = request.form.get("id")
    kupac_done = request.form.get("done")
    if db:
        try:
            if id_done:
                obj = Narudzba.query.get(int(id_done))
                if obj:
                    obj.napomena = "Završeno"
                    db.session.commit()
            elif kupac_done:
                obj = Narudzba.query.filter_by(kupac=kupac_done).first()
                if obj:
                    obj.napomena = "Završeno"
                    db.session.commit()
        except Exception:
            db.session.rollback()
    else:
        global df
        df.loc[df["Kupac/Farma"] == kupac_done, "Napomena"] = "Završeno"
        save_data_from_df_to_storage()
    return redirect("/")

@app.route("/edit", methods=["POST"])
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
            else:
                obj = Narudzba.query.filter_by(kupac=kupac_edit).first()
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
        df.loc[df["Kupac/Farma"] == kupac_edit, ["Vrsta hrane", "Količina (kg)", "Datum isporuke", "Napomena"]] = [
            vrsta_edit, kolicina_edit_val, datum_obj, napomena_edit
        ]
        save_data_from_df_to_storage()

    return redirect("/")

# -----------------------
# Pokretanje aplikacije
# -----------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
