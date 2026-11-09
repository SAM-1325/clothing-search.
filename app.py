import os
import certifi
import pymysql
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


def get_connection():
    return pymysql.connect(
        host=os.environ["DB_HOST"].strip(),
        port=int(os.environ.get("DB_PORT", "4000")),
        user=os.environ["DB_USER"].strip(),
        password=os.environ["DB_PASSWORD"],
        database=os.environ.get("DB_NAME", "clothing_store"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        ssl_ca=certifi.where(),
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        connect_timeout=15,
        read_timeout=25,
    )


@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@app.route("/")
def home():
    return jsonify({"message": "Clothing Store API is running", "endpoint": "/api/dashboard"})


@app.route("/api/dashboard")
def dashboard():
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.product_id, c.product_name, c.category_id,
                           ct.category_name, b.brand_name, c.color, c.size,
                           c.price, c.stock_qty, c.image_url,
                           pi.file_name
                    FROM clothing c
                    JOIN categories ct ON ct.category_id = c.category_id
                    JOIN brands b ON b.brand_id = c.brand_id
                    LEFT JOIN product_photos pi ON pi.product_id = c.product_id
                    ORDER BY c.product_id
                """)
                raw_products = cur.fetchall()

                cur.execute("""
                    SELECT ct.category_id, ct.category_name,
                           COUNT(c.product_id) AS product_count,
                           COALESCE(SUM(c.stock_qty), 0) AS stock
                    FROM categories ct
                    LEFT JOIN clothing c ON c.category_id = ct.category_id
                    GROUP BY ct.category_id, ct.category_name
                    ORDER BY ct.category_id
                """)
                raw_categories = cur.fetchall()

                cur.execute("""
                    SELECT COALESCE(SUM(oi.quantity), 0) AS sales_units,
                           COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS sales_amount
                    FROM order_items oi
                    JOIN orders o ON o.order_id = oi.order_id
                    WHERE o.status = '已完成'
                """)
                sales = cur.fetchone()

                cur.execute("""
                    SELECT ct.category_name AS name,
                           COALESCE(SUM(CASE WHEN o.status = '已完成'
                                             THEN oi.quantity ELSE 0 END), 0) AS value
                    FROM categories ct
                    LEFT JOIN clothing c ON c.category_id = ct.category_id
                    LEFT JOIN order_items oi ON oi.product_id = c.product_id
                    LEFT JOIN orders o ON o.order_id = oi.order_id
                    GROUP BY ct.category_id, ct.category_name
                    ORDER BY ct.category_id
                """)
                raw_sales_by_category = cur.fetchall()

            products = [
                {
                    "id": r["product_id"],
                    "name": r["product_name"],
                    "categoryId": r["category_id"],
                    "category": r["category_name"],
                    "brand": r["brand_name"],
                    "color": r["color"],
                    "size": r["size"],
                    "price": float(r["price"]),
                    "stock": r["stock_qty"],
                    "image_url": r["image_url"],
                    "image_file": r["file_name"],
                }
                for r in raw_products
            ]
            categories = [
                {"id": r["category_id"], "name": r["category_name"],
                 "count": int(r["product_count"]), "stock": int(r["stock"])}
                for r in raw_categories
            ]
            return jsonify({
                "summary": {
                    "products": len(products),
                    "categories": len(categories),
                    "stock": sum(p["stock"] for p in products),
                    "salesUnits": int(sales["sales_units"]),
                    "salesAmount": float(sales["sales_amount"]),
                },
                "categories": categories,
                "salesByCategory": [
                    {"name": r["name"], "value": int(r["value"])}
                    for r in raw_sales_by_category
                ],
                "products": products,
            })
        finally:
            conn.close()
    except Exception:
        app.logger.exception("Database connection/query failed")
        return jsonify({"error": "無法取得資料，請確認 TiDB Cloud 連線與資料是否完成匯入。"}), 503
