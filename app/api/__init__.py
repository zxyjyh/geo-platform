from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from app.auth import LoginLimiter
from app.config import get_settings
from app.db import get_session


def create_app(session_factory: sessionmaker | None = None, embedder=None) -> FastAPI:
    cfg = get_settings()
    if not cfg.secret_key:
        raise RuntimeError("缺少环境变量 SECRET_KEY")
    app = FastAPI(title="豆包 GEO 内部网站", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=cfg.secret_key, https_only=cfg.cookie_secure,
                       same_site="lax", session_cookie="geo_session", max_age=7 * 24 * 3600)
    app.state.login_limiter = LoginLimiter()
    if embedder is None and cfg.ark_api_key:
        from app.kb.embed import HttpArkEmbedder
        embedder = HttpArkEmbedder(cfg.ark_api_key)
    app.state.embedder = embedder
    app.state.kb_dir = cfg.kb_dir

    if session_factory is not None:
        def _session():
            with session_factory() as s:
                yield s
        app.dependency_overrides[get_session] = _session

    from app.api import (routes_auth, routes_dashboard, routes_kb, routes_questions, routes_runs, routes_settings,
                         routes_sources, routes_suggestions)

    for r in (routes_auth, routes_dashboard, routes_kb, routes_runs, routes_questions, routes_sources, routes_suggestions,
              routes_settings):
        app.include_router(r.router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app
