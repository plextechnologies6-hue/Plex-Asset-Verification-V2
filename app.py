import os
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")

database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url or (
    "sqlite:///" + os.path.join(BASE_DIR, "plex_v2.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Client(db.Model):
    __tablename__ = "clients"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(80), unique=True, nullable=True)
    contact_person = db.Column(db.String(160))
    email = db.Column(db.String(160))
    phone = db.Column(db.String(80))
    address = db.Column(db.String(300))
    notes = db.Column(db.Text)
    status = db.Column(db.String(40), default="Active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sessions = db.relationship("VerificationSession", back_populates="client",
                               cascade="all, delete-orphan")


class VerificationSession(db.Model):
    __tablename__ = "verification_sessions"
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    name = db.Column(db.String(240), nullable=False)
    reference_no = db.Column(db.String(100), unique=True, nullable=True)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(40), default="Planning")
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship("Client", back_populates="sessions")
    far_assets = db.relationship("FARAsset", back_populates="session",
                                 cascade="all, delete-orphan")
    field_assets = db.relationship("FieldAsset", back_populates="session",
                                   cascade="all, delete-orphan")


class FARAsset(db.Model):
    __tablename__ = "far_assets"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("verification_sessions.id"), nullable=False)
    asset_name = db.Column(db.String(250), nullable=False)
    description = db.Column(db.Text)
    tag_number = db.Column(db.String(120))
    location = db.Column(db.String(250))
    serial_number = db.Column(db.String(180))
    model = db.Column(db.String(180))
    user_name = db.Column(db.String(180))
    custodian = db.Column(db.String(180))
    source_row = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship("VerificationSession", back_populates="far_assets")


class FieldAsset(db.Model):
    __tablename__ = "field_assets"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("verification_sessions.id"), nullable=False)
    asset_name = db.Column(db.String(250), nullable=False)
    description = db.Column(db.Text)
    tag_number = db.Column(db.String(120))
    location = db.Column(db.String(250))
    serial_number = db.Column(db.String(180))
    model = db.Column(db.String(180))
    user_name = db.Column(db.String(180))
    custodian = db.Column(db.String(180))
    status = db.Column(db.String(60), default="Verified")
    condition = db.Column(db.String(80), default="Good")
    remarks = db.Column(db.Text)
    verified_by = db.Column(db.String(160))
    verified_at = db.Column(db.DateTime, default=datetime.utcnow)
    photo_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = db.relationship("VerificationSession", back_populates="field_assets")


with app.app_context():
    db.create_all()


def norm(value):
    return "".join((value or "").lower().split())


def field_match_status(far_asset, field_assets):
    tag = norm(far_asset.tag_number)
    serial = norm(far_asset.serial_number)

    if tag:
        matches = [a for a in field_assets if norm(a.tag_number) == tag]
        if matches:
            return matches[0], "Tag Number"
    if serial:
        matches = [a for a in field_assets if norm(a.serial_number) == serial]
        if matches:
            return matches[0], "Serial Number"

    key = (norm(far_asset.asset_name), norm(far_asset.location))
    candidates = [
        a for a in field_assets
        if (norm(a.asset_name), norm(a.location)) == key
    ]
    if len(candidates) == 1:
        return candidates[0], "Asset Name + Location"

    return None, ""


@app.route("/")
def dashboard():
    clients = Client.query.count()
    sessions = VerificationSession.query.count()
    field_count = FieldAsset.query.count()
    far_count = FARAsset.query.count()
    verified = FieldAsset.query.filter_by(status="Verified").count()
    not_found = FieldAsset.query.filter_by(status="Not Found").count()
    untagged = FieldAsset.query.filter_by(status="Untagged").count()
    active_sessions = VerificationSession.query.filter(
        VerificationSession.status.in_(["Planning", "Active"])
    ).count()

    recent_sessions = VerificationSession.query.order_by(
        VerificationSession.created_at.desc()
    ).limit(8).all()

    return render_template(
        "dashboard.html",
        clients=clients, sessions=sessions, field_count=field_count,
        far_count=far_count, verified=verified, not_found=not_found,
        untagged=untagged, active_sessions=active_sessions,
        recent_sessions=recent_sessions
    )


@app.route("/clients")
def clients():
    rows = Client.query.order_by(Client.name.asc()).all()
    return render_template("clients.html", clients=rows)


@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Client name is required.", "error")
            return render_template("client_form.html", title="New Client", client={})

        code = request.form.get("code", "").strip() or None
        if code and Client.query.filter_by(code=code).first():
            flash("Client code already exists.", "error")
            return render_template("client_form.html", title="New Client", client=request.form)

        client = Client(
            name=name, code=code,
            contact_person=request.form.get("contact_person", "").strip(),
            email=request.form.get("email", "").strip(),
            phone=request.form.get("phone", "").strip(),
            address=request.form.get("address", "").strip(),
            notes=request.form.get("notes", "").strip(),
            status=request.form.get("status", "Active")
        )
        db.session.add(client)
        db.session.commit()
        flash("Client created successfully.", "success")
        return redirect(url_for("clients"))

    return render_template("client_form.html", title="New Client", client={})


@app.route("/clients/<int:client_id>")
def client_detail(client_id):
    client = Client.query.get_or_404(client_id)
    sessions = VerificationSession.query.filter_by(client_id=client_id).order_by(
        VerificationSession.created_at.desc()
    ).all()
    return render_template("client_detail.html", client=client, sessions=sessions)


@app.route("/sessions/new", methods=["GET", "POST"])
def new_session():
    client_id = request.args.get("client_id", type=int)
    clients_list = Client.query.order_by(Client.name.asc()).all()

    if request.method == "POST":
        client_id = request.form.get("client_id", type=int)
        client = Client.query.get(client_id) if client_id else None
        if not client:
            flash("Please select a valid client.", "error")
            return render_template("session_form.html", clients=clients_list, session={})

        name = request.form.get("name", "").strip()
        if not name:
            flash("Session name is required.", "error")
            return render_template("session_form.html", clients=clients_list, session=request.form)

        reference_no = request.form.get("reference_no", "").strip() or None
        if reference_no and VerificationSession.query.filter_by(reference_no=reference_no).first():
            flash("Reference number already exists.", "error")
            return render_template("session_form.html", clients=clients_list, session=request.form)

        start_date = request.form.get("start_date") or None
        end_date = request.form.get("end_date") or None
        from datetime import date
        sd = date.fromisoformat(start_date) if start_date else None
        ed = date.fromisoformat(end_date) if end_date else None

        session_obj = VerificationSession(
            client_id=client_id,
            name=name,
            reference_no=reference_no,
            start_date=sd,
            end_date=ed,
            status=request.form.get("status", "Planning"),
            notes=request.form.get("notes", "").strip()
        )
        db.session.add(session_obj)
        db.session.commit()
        flash("Verification session created.", "success")
        return redirect(url_for("session_detail", session_id=session_obj.id))

    return render_template("session_form.html", clients=clients_list,
                           session={"client_id": client_id} if client_id else {})


@app.route("/sessions/<int:session_id>")
def session_detail(session_id):
    s = VerificationSession.query.get_or_404(session_id)
    far_count = FARAsset.query.filter_by(session_id=session_id).count()
    field_count = FieldAsset.query.filter_by(session_id=session_id).count()
    verified = FieldAsset.query.filter_by(session_id=session_id, status="Verified").count()
    not_found = FieldAsset.query.filter_by(session_id=session_id, status="Not Found").count()
    untagged = FieldAsset.query.filter_by(session_id=session_id, status="Untagged").count()

    return render_template(
        "session_detail.html", session=s, far_count=far_count,
        field_count=field_count, verified=verified, not_found=not_found,
        untagged=untagged
    )


@app.route("/sessions/<int:session_id>/assets")
def session_assets(session_id):
    s = VerificationSession.query.get_or_404(session_id)
    q = request.args.get("q", "").strip()

    query = FieldAsset.query.filter_by(session_id=session_id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            FieldAsset.asset_name.ilike(like),
            FieldAsset.tag_number.ilike(like),
            FieldAsset.serial_number.ilike(like),
            FieldAsset.location.ilike(like),
            FieldAsset.custodian.ilike(like)
        ))
    assets = query.order_by(FieldAsset.id.desc()).all()

    return render_template("session_assets.html", session=s, assets=assets, q=q)


@app.route("/sessions/<int:session_id>/assets/new", methods=["GET", "POST"])
def new_field_asset(session_id):
    s = VerificationSession.query.get_or_404(session_id)

    if request.method == "POST":
        asset_name = request.form.get("asset_name", "").strip()
        if not asset_name:
            flash("Asset name is required.", "error")
            return render_template("asset_form.html", session=s, asset=request.form, title="Capture Asset")

        asset = FieldAsset(
            session_id=session_id,
            asset_name=asset_name,
            description=request.form.get("description", "").strip(),
            tag_number=request.form.get("tag_number", "").strip(),
            location=request.form.get("location", "").strip(),
            serial_number=request.form.get("serial_number", "").strip(),
            model=request.form.get("model", "").strip(),
            user_name=request.form.get("user_name", "").strip(),
            custodian=request.form.get("custodian", "").strip(),
            status=request.form.get("status", "Verified"),
            condition=request.form.get("condition", "Good"),
            remarks=request.form.get("remarks", "").strip(),
            verified_by=request.form.get("verified_by", "").strip()
        )
        db.session.add(asset)
        db.session.commit()
        flash("Field asset captured.", "success")
        return redirect(url_for("session_assets", session_id=session_id))

    return render_template("asset_form.html", session=s, asset={}, title="Capture Asset")


@app.route("/sessions/<int:session_id>/far/import", methods=["GET", "POST"])
def import_far(session_id):
    s = VerificationSession.query.get_or_404(session_id)

    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename.lower().endswith(".csv"):
            flash("Please upload a CSV file for this V2 release.", "error")
            return redirect(url_for("import_far", session_id=session_id))

        if request.form.get("replace_existing") == "yes":
            FARAsset.query.filter_by(session_id=session_id).delete()

        text = f.read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        imported = 0

        def pick(row, *names):
            normalized = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k}
            aliases = {
                "asset name": ["asset name", "asset_name", "asset"],
                "description": ["description", "asset description"],
                "tag number": ["tag number", "tag_number", "asset tag", "tag"],
                "location": ["location", "current location"],
                "serial number": ["serial number", "serial_number", "serial", "serial no"],
                "model": ["model", "model number"],
                "user": ["user", "user name", "user_name"],
                "custodian": ["custodian"]
            }
            for key in names:
                for alias in aliases.get(key, [key]):
                    if alias in normalized:
                        return normalized[alias]
            return ""

        for row_no, row in enumerate(reader, start=2):
            name = pick(row, "asset name")
            if not name:
                continue
            db.session.add(FARAsset(
                session_id=session_id,
                asset_name=name,
                description=pick(row, "description"),
                tag_number=pick(row, "tag number"),
                location=pick(row, "location"),
                serial_number=pick(row, "serial number"),
                model=pick(row, "model"),
                user_name=pick(row, "user"),
                custodian=pick(row, "custodian"),
                source_row=row_no
            ))
            imported += 1

        db.session.commit()
        flash(f"{imported} FAR records imported into {s.name}.", "success")
        return redirect(url_for("session_detail", session_id=session_id))

    return render_template("import_far.html", session=s)


@app.route("/sessions/<int:session_id>/reconcile")
def reconcile(session_id):
    s = VerificationSession.query.get_or_404(session_id)
    far_assets = FARAsset.query.filter_by(session_id=session_id).order_by(FARAsset.id).all()
    field_assets = FieldAsset.query.filter_by(session_id=session_id).order_by(FieldAsset.id).all()

    results = []
    used = set()

    for f in far_assets:
        match, basis = field_match_status(f, field_assets)
        if match:
            used.add(match.id)
            differences = []
            for field in ["asset_name", "description", "tag_number", "location",
                          "serial_number", "model", "user_name", "custodian"]:
                if norm(getattr(f, field)) != norm(getattr(match, field)):
                    differences.append(field)
            status = "Matched - Differences" if differences else "Matched"
            results.append((f, match, basis, status, differences))
        else:
            results.append((f, None, "", "Not Found in Field", []))

    field_only = [a for a in field_assets if a.id not in used]
    matched = sum(1 for r in results if r[3].startswith("Matched"))
    differences = sum(1 for r in results if r[3] == "Matched - Differences")
    not_found = sum(1 for r in results if r[3] == "Not Found in Field")

    return render_template(
        "reconcile.html", session=s, results=results, field_only=field_only,
        stats={"far": len(far_assets), "matched": matched,
               "differences": differences, "not_found": not_found,
               "field_only": len(field_only)}
    )


@app.route("/sessions/<int:session_id>/export")
def export_field(session_id):
    s = VerificationSession.query.get_or_404(session_id)
    rows = FieldAsset.query.filter_by(session_id=session_id).order_by(FieldAsset.id).all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "ID", "Asset Name", "Description", "Tag Number", "Location",
        "Serial Number", "Model", "User", "Custodian", "Status",
        "Condition", "Remarks", "Verified By", "Verified At"
    ])
    for a in rows:
        writer.writerow([
            a.id, a.asset_name, a.description, a.tag_number, a.location,
            a.serial_number, a.model, a.user_name, a.custodian, a.status,
            a.condition, a.remarks, a.verified_by,
            a.verified_at.isoformat() if a.verified_at else ""
        ])

    data = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    return send_file(
        data, mimetype="text/csv", as_attachment=True,
        download_name=f"Field_Register_{s.reference_no or s.id}.csv"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
