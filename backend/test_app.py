from app import create_app

def client():
    return create_app(init=False).test_client()

def test_health():
    r = client().get("/health")
    assert r.status_code == 200 and r.json["status"] == "ok"

def test_cart_requires_login():
    assert client().get("/api/cart").status_code == 401

def test_admin_requires_login():
    assert client().get("/api/admin/orders").status_code == 401

def test_register_validation():
    assert client().post("/api/register", json={"email": "a@b.c"}).status_code == 400
