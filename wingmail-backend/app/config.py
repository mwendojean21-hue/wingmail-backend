from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://wingmail_user:change_me@localhost:5432/wingmail"
    JWT_SECRET: str = "change_me_super_secret_random_string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost,capacitor://localhost"
    MAPTILER_KEY: str = ""

    # Comptes automatiquement promus administrateur au premier login,
    # d'apres leur nom d'utilisateur (liste separee par des virgules).
    ADMIN_USERNAMES: str = "erickbenoit337"

    # Utilise pour generer les liens de parrainage (ex: https://wingmail.onrender.com)
    FRONTEND_URL: str = "http://localhost:5173"

    # Depot GitHub verifie pour la recompense "etoile"
    GITHUB_REPO: str = "erickbenoit337/wingmail"

    @property
    def admin_usernames_list(self) -> List[str]:
        return [u.strip().lower() for u in self.ADMIN_USERNAMES.split(",") if u.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
