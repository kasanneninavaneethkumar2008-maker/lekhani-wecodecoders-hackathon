"""Entry point: `python run.py` (dev) or `gunicorn run:app` (production)."""
import os

from inkloom import create_app

app = create_app()

if __name__ == "__main__":
    # Hosts like Render expect 0.0.0.0 and provide the port via $PORT.
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=True,
    )
