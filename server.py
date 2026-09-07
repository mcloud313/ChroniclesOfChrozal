"""Web-only entry point. One process owns the live world."""
import uvicorn
import config

if __name__ == "__main__":
    uvicorn.run("web.app:app", host=config.HOST, port=config.PORT, workers=1,
                ws_max_size=4096, ws_max_queue=16, timeout_graceful_shutdown=30)
