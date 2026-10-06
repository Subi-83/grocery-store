import { useState, useEffect } from "react";

const call = async (path, method = "GET", body, token) => {
  const r = await fetch("/api" + path, {
    method, body: body ? JSON.stringify(body) : undefined,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) },
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "Error");
  return d;
};

export default function App() {
  const [s, setS] = useState(JSON.parse(localStorage.getItem("s") || "null"));
  const [view, setView] = useState("shop");
  const [msg, setMsg] = useState("");
  const flash = (m) => { setMsg(m); setTimeout(() => setMsg(""), 3000); };
  const api = (p, m, b) => call(p, m, b, s?.token);
  const logout = () => { localStorage.removeItem("s"); setS(null); setView("shop"); };
  const P = { api, flash, s };

  return (<div>
    <h2>🛒 Grocery Store</h2>
    <nav>
      <button onClick={() => setView("shop")}>Shop</button>
      {s ? <>
        <button onClick={() => setView("cart")}>Cart</button>
        <button onClick={() => setView("orders")}>My Orders</button>
        <button onClick={() => setView("profile")}>Profile</button>
        {s.role === "admin" && <button onClick={() => setView("admin")}>Admin</button>}
        <button onClick={logout}>Logout ({s.name})</button>
      </> : <button onClick={() => setView("login")}>Login / Register</button>}
    </nav>
    <p className="msg">{msg}</p>
    {view === "shop" && <Shop {...P} go={setView} />}
    {view === "login" && <Auth {...P} done={(x) => { localStorage.setItem("s", JSON.stringify(x)); setS(x); setView("shop"); }} />}
    {s && view === "cart" && <Cart {...P} go={setView} />}
    {s && view === "orders" && <Orders {...P} />}
    {s && view === "profile" && <Profile {...P} />}
    {s?.role === "admin" && view === "admin" && <Admin {...P} />}
  </div>);
}

function Auth({ api, flash, done }) {
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const [reg, setReg] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async () => {
    try {
      if (reg) { await api("/register", "POST", f); flash("Registered! Now login."); setReg(false); }
      else done(await api("/login", "POST", f));
    } catch (e) { flash(e.message); }
  };
  return (<div>
    <h3>{reg ? "Register" : "Login"}</h3>
    {reg && <div><input placeholder="Name" onChange={set("name")} /></div>}
    <div><input placeholder="Email" onChange={set("email")} /></div>
    <div><input type="password" placeholder="Password" onChange={set("password")} /></div>
    <button className="b" onClick={submit}>{reg ? "Register" : "Login"}</button>
    <button className="b" onClick={() => setReg(!reg)}>{reg ? "I have an account" : "Create account"}</button>
    <p><small>Admin demo: admin@grocery.com / admin123</small></p>
  </div>);
}

function Shop({ api, flash, s, go }) {
  const [d, setD] = useState({ items: [], pages: 1 });
  const [cats, setCats] = useState([]);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [detail, setDetail] = useState(null);
  useEffect(() => { api("/categories").then(setCats); }, []);
  useEffect(() => {
    api(`/products?page=${page}&per_page=8&q=${encodeURIComponent(q)}&category_id=${cat}`).then(setD);
  }, [page, q, cat]);
  const add = async (id) => {
    if (!s) return go("login");
    await api("/cart", "POST", { product_id: id, qty: 1 }); flash("Added to cart");
  };
  return (<div>
    <input placeholder="Search..." value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
    <select value={cat} onChange={(e) => { setCat(e.target.value); setPage(1); }}>
      <option value="">All categories</option>
      {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
    <div className="grid">
      {d.items.map((p) => (<div className="card" key={p.id}>
        <b>{p.name}</b><br />₹{p.price} <small>({p.category})</small><br />
        <button className="b" onClick={() => setDetail(p)}>Details</button>
        <button className="b" onClick={() => add(p.id)}>Add</button>
      </div>))}
    </div>
    {detail && <div className="card" style={{ marginTop: 10 }}>
      <h3>{detail.name}</h3><p>{detail.description}</p>
      <p>Price: ₹{detail.price} | In stock: {detail.stock} | Category: {detail.category}</p>
      <button className="b" onClick={() => setDetail(null)}>Close</button>
    </div>}
    <p>
      <button className="b" disabled={page <= 1} onClick={() => setPage(page - 1)}>« Prev</button>
      Page {page} of {d.pages}
      <button className="b" disabled={page >= d.pages} onClick={() => setPage(page + 1)}>Next »</button>
    </p>
  </div>);
}

function Cart({ api, flash, go }) {
  const [items, setItems] = useState([]);
  const load = () => api("/cart").then(setItems);
  useEffect(() => { load(); }, []);
  const total = items.reduce((a, i) => a + i.price * i.qty, 0);
  const del = async (id) => { await api("/cart/" + id, "DELETE"); load(); };
  const order = async () => {
    try { await api("/orders", "POST"); flash("Order placed!"); go("orders"); } catch (e) { flash(e.message); }
  };
  return (<div><h3>Your Cart</h3>
    <table><tbody>{items.map((i) => (<tr key={i.product_id}>
      <td>{i.name}</td><td>{i.qty} × ₹{i.price}</td>
      <td><button onClick={() => del(i.product_id)}>Remove</button></td></tr>))}</tbody></table>
    <p><b>Total: ₹{total}</b></p>
    {items.length > 0 && <button className="b" onClick={order}>Place Order</button>}
  </div>);
}

function Orders({ api }) {
  const [o, setO] = useState([]);
  useEffect(() => { api("/orders").then(setO); }, []);
  return (<div><h3>My Orders</h3><table>
    <thead><tr><th>#</th><th>Total</th><th>Status</th><th>Date</th></tr></thead>
    <tbody>{o.map((x) => <tr key={x.id}><td>{x.id}</td><td>₹{x.total}</td><td>{x.status}</td><td>{x.created_at}</td></tr>)}</tbody>
  </table></div>);
}

function Profile({ api, flash }) {
  const [p, setP] = useState({ name: "", phone: "", address: "" });
  useEffect(() => { api("/profile").then((d) => setP({ ...d, phone: d.phone || "", address: d.address || "" })); }, []);
  const set = (k) => (e) => setP({ ...p, [k]: e.target.value });
  const save = async () => { await api("/profile", "PUT", p); flash("Profile saved"); };
  return (<div><h3>Profile</h3><p>{p.email}</p>
    <div><input value={p.name} onChange={set("name")} placeholder="Name" /></div>
    <div><input value={p.phone} onChange={set("phone")} placeholder="Phone" /></div>
    <div><input value={p.address} onChange={set("address")} placeholder="Address" /></div>
    <button className="b" onClick={save}>Save</button></div>);
}

function Admin({ api, flash }) {
  const [tab, setTab] = useState("products");
  const [products, setProducts] = useState([]);
  const [cats, setCats] = useState([]);
  const [orders, setOrders] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [f, setF] = useState({ name: "", price: "", stock: "", category_id: "" });
  const [newCat, setNewCat] = useState("");
  const load = () => {
    api("/products?per_page=100").then((d) => setProducts(d.items));
    api("/categories").then(setCats);
    api("/admin/orders").then(setOrders);
    api("/admin/customers").then(setCustomers);
  };
  useEffect(load, []);
  const run = async (fn) => { try { await fn(); load(); } catch (e) { flash(e.message); } };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const stock = (p) => {
    const n = prompt(`New stock for ${p.name}`, p.stock);
    if (n !== null) run(() => api("/admin/products/" + p.id, "PUT", { ...p, stock: Number(n) }));
  };
  return (<div><h3>Admin Dashboard</h3>
    {["products", "categories", "orders", "customers"].map((t) => <button key={t} className="b" onClick={() => setTab(t)}>{t}</button>)}
    {tab === "products" && <div>
      <div><input placeholder="Name" onChange={set("name")} /><input placeholder="Price" size="6" onChange={set("price")} />
        <input placeholder="Stock" size="6" onChange={set("stock")} />
        <select onChange={set("category_id")}><option value="">Category</option>{cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <button className="b" onClick={() => run(() => api("/admin/products", "POST", f))}>Add product</button></div>
      <table><tbody>{products.map((p) => (<tr key={p.id}><td>{p.name}</td><td>₹{p.price}</td><td>Stock: {p.stock}</td>
        <td><button onClick={() => stock(p)}>Edit stock</button>
          <button onClick={() => run(() => api("/admin/products/" + p.id, "DELETE"))}>Delete</button></td></tr>))}</tbody></table></div>}
    {tab === "categories" && <div>
      <input placeholder="New category" onChange={(e) => setNewCat(e.target.value)} />
      <button className="b" onClick={() => run(() => api("/admin/categories", "POST", { name: newCat }))}>Add</button>
      <ul>{cats.map((c) => <li key={c.id}>{c.name} <button onClick={() => run(() => api("/admin/categories/" + c.id, "DELETE"))}>x</button></li>)}</ul></div>}
    {tab === "orders" && <table><tbody>{orders.map((o) => (<tr key={o.id}><td>#{o.id}</td><td>{o.customer}</td><td>₹{o.total}</td>
      <td><select value={o.status} onChange={(e) => run(() => api(`/admin/orders/${o.id}/status`, "PUT", { status: e.target.value }))}>
        {["Placed", "Packed", "Shipped", "Delivered", "Cancelled"].map((x) => <option key={x}>{x}</option>)}</select></td></tr>))}</tbody></table>}
    {tab === "customers" && <table><tbody>{customers.map((c) => <tr key={c.id}><td>{c.name}</td><td>{c.email}</td><td>{c.phone}</td></tr>)}</tbody></table>}
  </div>);
}
