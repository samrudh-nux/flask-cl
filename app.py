import logging

from flask import Flask, send_from_directory

from api.routes import bp as api_bp
from config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_mb * 1024 * 1024
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.port, debug=False)
