# Grocery Store E-Commerce (React + Flask + MySQL)

Simple full-stack app. **All DevOps / cloud steps are in [DEVOPS_README.md](DEVOPS_README.md).**

- Frontend: React (Vite) served by Nginx, `/api` is proxied to Flask
- Backend: Flask REST API + JWT login (`backend/app.py`), tables and sample data are created automatically on start
- Database: MySQL 8

Features: register/login, product search + category filter + pagination (8 per page), product details, cart, place order, order status tracking, profile, admin dashboard (products, stock, categories, customers, order status).

Demo admin: `admin@grocery.com` / `admin123`

Quick run: `docker compose up --build` then open http://localhost:8080
