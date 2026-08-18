from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine, SessionLocal
from .config import settings
from . import models
from .routers import auth, pigeons, messages, friends, rewards, admin, feedback

app = FastAPI(
    title="Wingmail API",
    description="Backend de Wingmail - messagerie par pigeon voyageur virtuel",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(pigeons.router)
app.include_router(messages.router)
app.include_router(friends.router)
app.include_router(rewards.router)
app.include_router(admin.router)
app.include_router(feedback.router)


DEFAULT_BIRD_TYPES = [
    dict(code="pigeon", display_name="Pigeon voyageur", base_speed_mph=110,
         max_range_miles=800, loss_risk_multiplier=1.0, unlock_cost_feathers=15,
         description="L'oiseau de base de Wingmail. Fiable, mais sa portée reste modeste : au-delà de 800 miles, il n'arrivera pas.",
         sprite_key="pigeon"),
    dict(code="swallow", display_name="Hirondelle", base_speed_mph=45,
         max_range_miles=400, loss_risk_multiplier=0.6, unlock_cost_feathers=20,
         description="Petite et prudente, elle prend moins de risques mais vole plus lentement et pas très loin.",
         sprite_key="swallow"),
    dict(code="raven", display_name="Corbeau", base_speed_mph=65,
         max_range_miles=2500, loss_risk_multiplier=0.5, unlock_cost_feathers=60,
         description="Intelligent et endurant, il prend rarement des risques inutiles et couvre de bonnes distances.",
         sprite_key="raven"),
    dict(code="hawk", display_name="Faucon", base_speed_mph=150,
         max_range_miles=4000, loss_risk_multiplier=1.4, unlock_cost_feathers=90,
         description="Rapide et endurant, mais plus fragile : le risque de perte augmente sur les longs trajets.",
         sprite_key="hawk"),
    dict(code="albatross", display_name="Albatros", base_speed_mph=80,
         max_range_miles=12000, loss_risk_multiplier=0.3, unlock_cost_feathers=150,
         description="Taillé pour les très longues distances océaniques, presque increvable.",
         sprite_key="albatross"),
    dict(code="falcon", display_name="Faucon pèlerin", base_speed_mph=240,
         max_range_miles=26000, loss_risk_multiplier=2.0, unlock_cost_feathers=220,
         description="Le plus rapide et le plus endurant du ciel : capable de faire le tour du monde sur une pleine jauge d'énergie. Risque de perte élevé.",
         sprite_key="falcon"),
]


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for bt in DEFAULT_BIRD_TYPES:
            existing = db.query(models.BirdType).filter(models.BirdType.code == bt["code"]).first()
            if not existing:
                db.add(models.BirdType(**bt))
        db.commit()
    finally:
        db.close()


@app.get("/")
def root():
    return {"status": "ok", "service": "wingmail-api"}


@app.get("/health")
def health():
    return {"status": "healthy"}
