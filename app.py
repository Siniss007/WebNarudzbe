from flask import Flask, render_template, request, redirect
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)

# -----------------------
# Konfiguracija fajla
# -----------------------
FILE_PATH = "narudzbe.xlsx"
columns = ["Kupac/Farma", "Datum isporuke", "Vrsta hrane", "Količina (kg)", "Napomena"]

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
def save_data():
    df_to_save = df.copy()
    df_to_save["Datum isporuke"] = df_to_save["Datum isporuke"].apply(lambda x: x.strftime("%d.%m.%Y."))
    df_to_save.to_excel(FILE_PATH, index=False)

def get_orders():
    df_sorted = df.sort_values(by="Datum isporuke")
    orders = []
    for _, row in df_sorted.iterrows():
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
    totals = df[df["Napomena"] != "Završeno"].groupby("Vrsta hrane")["Količina (kg)"].sum().to_dict()
    return totals

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
    global df
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
    df = pd.concat([df, pd.DataFrame([new_order])], ignore_index=True)
    save_data()
    return redirect("/")

@app.route("/delete", methods=["POST"])
def delete_order():
    global df
    kupac_to_delete = request.form.get("delete")
    df = df[df["Kupac/Farma"] != kupac_to_delete]
    save_data()
    return redirect("/")

@app.route("/mark_done", methods=["POST"])
def mark_done():
    global df
    kupac_done = request.form.get("done")
    df.loc[df["Kupac/Farma"] == kupac_done, "Napomena"] = "Završeno"
    save_data()
    return redirect("/")

@app.route("/edit", methods=["POST"])
def edit_order():
    global df
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

    df.loc[df["Kupac/Farma"] == kupac_edit, ["Vrsta hrane","Količina (kg)","Datum isporuke","Napomena"]] = [
        vrsta_edit, kolicina_edit, datum_obj, napomena_edit
    ]
    save_data()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
