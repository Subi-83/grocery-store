import os, time, datetime
from functools import wraps
import pymysql, jwt
from flask import Flask, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

SECRET = os.getenv("JWT_SECRET", "dev-secret")
DB = dict(host=os.getenv("DB_HOST", "localhost"), user=os.getenv("DB_USER", "grocery"),
          password=os.getenv("DB_PASSWORD", "grocery"), database=os.getenv("DB_NAME", "grocery"),
          cursorclass=pymysql.cursors.DictCursor, autocommit=True)

def db():
    return pymysql.connect(**DB)

def q(sql, args=(), one=False, write=False):
    c = db()
    try:
        with c.cursor() as cur:
            cur.execute(sql, args)
            if write:
                return cur.lastrowid
            return cur.fetchone() if one else cur.fetchall()
    finally:
        c.close()

SCHEMA = [
 """CREATE TABLE IF NOT EXISTS users(id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100), email VARCHAR(120) UNIQUE,
    password_hash VARCHAR(255), phone VARCHAR(20), address VARCHAR(255), role VARCHAR(10) DEFAULT 'customer')""",
 "CREATE TABLE IF NOT EXISTS categories(id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) UNIQUE)",
 """CREATE TABLE IF NOT EXISTS products(id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(120) UNIQUE, description VARCHAR(255),
    price DECIMAL(10,2), stock INT DEFAULT 0, category_id INT NULL,
    FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL)""",
 """CREATE TABLE IF NOT EXISTS cart_items(user_id INT, product_id INT, qty INT, PRIMARY KEY(user_id, product_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE)""",
 """CREATE TABLE IF NOT EXISTS orders(id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, total DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'Placed', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
 """CREATE TABLE IF NOT EXISTS order_items(id INT AUTO_INCREMENT PRIMARY KEY, order_id INT, product_id INT, name VARCHAR(120),
    qty INT, price DECIMAL(10,2), FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE)""",
]
SEED = {"Fruits": [("Apple", 120), ("Banana", 50), ("Orange", 80), ("Mango", 150), ("Grapes", 90)],
        "Vegetables": [("Tomato", 30), ("Potato", 25), ("Onion", 35), ("Carrot", 45), ("Spinach", 20)],
        "Dairy": [("Milk 1L", 55), ("Curd 500g", 40), ("Butter 100g", 60), ("Paneer 200g", 85)],
        "Bakery": [("Bread", 40), ("Cookies", 30), ("Cake Slice", 70)],
        "Snacks": [("Chips", 20), ("Peanuts", 35), ("Biscuits", 25)]}

def init_db():
    for _ in range(40):  # wait for MySQL to come up
        try:
            c = db(); break
        except Exception:
            time.sleep(3)
    else:
        raise RuntimeError("MySQL not reachable")
    with c.cursor() as cur:
        cur.execute("SELECT GET_LOCK('grocery_init', 60)")  # safe with many workers/pods
        for s in SCHEMA:
            cur.execute(s)
        cur.execute("INSERT IGNORE INTO users(name,email,password_hash,role) VALUES('Admin','admin@grocery.com',%s,'admin')",
                    (generate_password_hash("admin123"),))
        for cat, items in SEED.items():
            cur.execute("INSERT IGNORE INTO categories(name) VALUES(%s)", (cat,))
            for name, price in items:
                cur.execute("INSERT IGNORE INTO products(name,description,price,stock,category_id) "
                            "VALUES(%s,%s,%s,50,(SELECT id FROM categories WHERE name=%s))",
                            (name, f"Fresh {name}", price, cat))
        cur.execute("SELECT RELEASE_LOCK('grocery_init')")
    c.close()

def auth(admin=False):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            try:
                g.user = jwt.decode(request.headers.get("Authorization", "").replace("Bearer ", ""), SECRET, algorithms=["HS256"])
            except Exception:
                return jsonify(error="unauthorized"), 401
            if admin and g.user["role"] != "admin":
                return jsonify(error="forbidden"), 403
            return f(*a, **k)
        return w
    return deco

def create_app(init=True):
    app = Flask(__name__)
    if init:
        init_db()

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    # ---------- auth & profile ----------
    @app.post("/api/register")
    def register():
        d = request.json or {}
        if not d.get("email") or not d.get("password") or not d.get("name"):
            return jsonify(error="name, email, password required"), 400
        try:
            q("INSERT INTO users(name,email,password_hash) VALUES(%s,%s,%s)",
              (d["name"], d["email"], generate_password_hash(d["password"])), write=True)
        except pymysql.err.IntegrityError:
            return jsonify(error="email already registered"), 409
        return jsonify(message="registered"), 201

    @app.post("/api/login")
    def login():
        d = request.json or {}
        u = q("SELECT * FROM users WHERE email=%s", (d.get("email"),), one=True)
        if not u or not check_password_hash(u["password_hash"], d.get("password", "")):
            return jsonify(error="invalid credentials"), 401
        tok = jwt.encode({"id": u["id"], "role": u["role"],
                          "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=12)}, SECRET, algorithm="HS256")
        return jsonify(token=tok, role=u["role"], name=u["name"])

    @app.route("/api/profile", methods=["GET", "PUT"])
    @auth()
    def profile():
        if request.method == "PUT":
            d = request.json or {}
            q("UPDATE users SET name=%s, phone=%s, address=%s WHERE id=%s",
              (d.get("name"), d.get("phone"), d.get("address"), g.user["id"]), write=True)
        return jsonify(q("SELECT id,name,email,phone,address FROM users WHERE id=%s", (g.user["id"],), one=True))

    # ---------- catalog ----------
    @app.get("/api/categories")
    def categories():
        return jsonify(q("SELECT * FROM categories ORDER BY name"))

    @app.get("/api/products")
    def products():
        page = max(int(request.args.get("page", 1)), 1)
        per = min(int(request.args.get("per_page", 8)), 100)
        where, args = "WHERE 1=1", []
        if request.args.get("q"):
            where += " AND p.name LIKE %s"; args.append(f"%{request.args['q']}%")
        if request.args.get("category_id"):
            where += " AND p.category_id=%s"; args.append(request.args["category_id"])
        total = q(f"SELECT COUNT(*) n FROM products p {where}", args, one=True)["n"]
        items = q(f"SELECT p.*, c.name category FROM products p LEFT JOIN categories c ON c.id=p.category_id "
                  f"{where} ORDER BY p.id LIMIT %s OFFSET %s", args + [per, (page - 1) * per])
        return jsonify(items=items, total=total, page=page, pages=max(-(-total // per), 1))

    @app.get("/api/products/<int:pid>")
    def product(pid):
        p = q("SELECT p.*, c.name category FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=%s", (pid,), one=True)
        return (jsonify(p), 200) if p else (jsonify(error="not found"), 404)

    # ---------- cart ----------
    @app.get("/api/cart")
    @auth()
    def cart():
        return jsonify(q("SELECT ci.product_id, ci.qty, p.name, p.price FROM cart_items ci "
                         "JOIN products p ON p.id=ci.product_id WHERE ci.user_id=%s", (g.user["id"],)))

    @app.post("/api/cart")
    @auth()
    def cart_add():
        d = request.json or {}
        q("INSERT INTO cart_items(user_id,product_id,qty) VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE qty=qty+VALUES(qty)",
          (g.user["id"], d["product_id"], int(d.get("qty", 1))), write=True)
        return jsonify(message="added")

    @app.delete("/api/cart/<int:pid>")
    @auth()
    def cart_del(pid):
        q("DELETE FROM cart_items WHERE user_id=%s AND product_id=%s", (g.user["id"], pid), write=True)
        return jsonify(message="removed")

    # ---------- orders ----------
    @app.post("/api/orders")
    @auth()
    def place_order():
        uid = g.user["id"]
        c = db(); c.autocommit(False)
        try:
            with c.cursor() as cur:
                cur.execute("SELECT ci.product_id, ci.qty, p.name, p.price, p.stock FROM cart_items ci "
                            "JOIN products p ON p.id=ci.product_id WHERE ci.user_id=%s FOR UPDATE", (uid,))
                rows = cur.fetchall()
                if not rows:
                    return jsonify(error="cart is empty"), 400
                for r in rows:
                    if r["qty"] > r["stock"]:
                        raise ValueError(f"Not enough stock for {r['name']}")
                cur.execute("INSERT INTO orders(user_id,total) VALUES(%s,%s)", (uid, sum(r["price"] * r["qty"] for r in rows)))
                oid = cur.lastrowid
                for r in rows:
                    cur.execute("INSERT INTO order_items(order_id,product_id,name,qty,price) VALUES(%s,%s,%s,%s,%s)",
                                (oid, r["product_id"], r["name"], r["qty"], r["price"]))
                    cur.execute("UPDATE products SET stock=stock-%s WHERE id=%s", (r["qty"], r["product_id"]))
                cur.execute("DELETE FROM cart_items WHERE user_id=%s", (uid,))
            c.commit()
            return jsonify(order_id=oid), 201
        except ValueError as e:
            c.rollback()
            return jsonify(error=str(e)), 400
        finally:
            c.close()

    @app.get("/api/orders")
    @auth()
    def my_orders():
        return jsonify(q("SELECT * FROM orders WHERE user_id=%s ORDER BY id DESC", (g.user["id"],)))

    @app.get("/api/orders/<int:oid>")
    @auth()
    def order(oid):
        o = q("SELECT * FROM orders WHERE id=%s AND user_id=%s", (oid, g.user["id"]), one=True)
        if not o:
            return jsonify(error="not found"), 404
        o["items"] = q("SELECT name, qty, price FROM order_items WHERE order_id=%s", (oid,))
        return jsonify(o)

    # ---------- admin ----------
    @app.post("/api/admin/products")
    @auth(admin=True)
    def a_add():
        d = request.json
        pid = q("INSERT INTO products(name,description,price,stock,category_id) VALUES(%s,%s,%s,%s,%s)",
                (d["name"], d.get("description", ""), d["price"], d.get("stock", 0), d.get("category_id") or None), write=True)
        return jsonify(id=pid), 201

    @app.put("/api/admin/products/<int:pid>")
    @auth(admin=True)
    def a_edit(pid):
        d = request.json
        q("UPDATE products SET name=%s, description=%s, price=%s, stock=%s, category_id=%s WHERE id=%s",
          (d["name"], d.get("description", ""), d["price"], d["stock"], d.get("category_id") or None, pid), write=True)
        return jsonify(message="updated")

    @app.delete("/api/admin/products/<int:pid>")
    @auth(admin=True)
    def a_del(pid):
        q("DELETE FROM products WHERE id=%s", (pid,), write=True)
        return jsonify(message="deleted")

    @app.post("/api/admin/categories")
    @auth(admin=True)
    def a_cat():
        q("INSERT IGNORE INTO categories(name) VALUES(%s)", (request.json["name"],), write=True)
        return jsonify(message="ok"), 201

    @app.delete("/api/admin/categories/<int:cid>")
    @auth(admin=True)
    def a_cat_del(cid):
        q("DELETE FROM categories WHERE id=%s", (cid,), write=True)
        return jsonify(message="deleted")

    @app.get("/api/admin/customers")
    @auth(admin=True)
    def a_customers():
        return jsonify(q("SELECT id,name,email,phone,address FROM users WHERE role='customer'"))

    @app.get("/api/admin/orders")
    @auth(admin=True)
    def a_orders():
        return jsonify(q("SELECT o.*, u.name customer FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.id DESC"))

    @app.put("/api/admin/orders/<int:oid>/status")
    @auth(admin=True)
    def a_status(oid):
        s = request.json.get("status")
        if s not in ("Placed", "Packed", "Shipped", "Delivered", "Cancelled"):
            return jsonify(error="bad status"), 400
        q("UPDATE orders SET status=%s WHERE id=%s", (s, oid), write=True)
        return jsonify(message="updated")

    return app
