"""生产入口：``flask --app wsgi:app run`` 或 gunicorn 均可加载。"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
