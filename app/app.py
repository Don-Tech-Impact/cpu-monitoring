from flask import Flask, flash, redirect, render_template, \
     request, url_for, jsonify
import mysql.connector
import requests
import os
from time import sleep
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("app_secret")


## Database configuration or connection
def database_connection():
    # return mysql.connector.connect(
        retries = 5

        while retries > 0:
            try:
                connection = mysql.connector.connect(
                    host=os.getenv("DB_HOST", "localhost"),
                    user=os.getenv("DB_USER", "finance_user"),
                    password=os.getenv("DB_PASSWORD", "finance_pass@2026"),
                    database=os.getenv("DB_NAME", "finance_db")
                )
                return connection
            except mysql.connector.Error as err:
                print(f"Error: {err}")
                retries -= 1
                time.sleep(2)
        return None

        
        # host=os.getenv("DB_HOST", "localhost"),
        # user=os.getenv("DB_USER", "finance_user"),
        # password=os.getenv("DB_PASSWORD", "finance_pass@2026"),
        # database=os.getenv("DB_NAME", "finance_db")

@app.route("/")
def index():
    return jsonify({
        "status": "success",
        "message": "Infrastructure Monitoring system running",
        "database" : "connected" if database_connection() else "not connected"
    })

@app.route("/health")
def health():
    conn = database_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM servers")
        server_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({
            "status": "healthy",
            "server": "Count " + str(server_count),
            "database" : "connected",
            "server_count": server_count
        }), 200
    return jsonify({
        "status": "unhealthy",
    }), 500

@app.route("/servers", methods=["GET"])
def servers():
    conn = database_connection()
    if not conn:
        return jsonify({
            "error": "database unavailable",
        }), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM servers")
    result = cursor.fetchall()
    conn.close()

    return jsonify({"server": "results"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)