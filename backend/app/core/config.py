from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "CITI Platform"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg://citi_app:changeme@localhost:5432/citi_platform"
    # Only read by backend/tests/conftest.py — never used by the running app itself.
    TEST_DATABASE_URL: str = "postgresql+psycopg://citi_app:changeme@localhost:5432/citi_platform_test"

    SECRET_KEY: str = "changeme-generate-a-real-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    CONFIG_ENCRYPTION_KEY: str = "changeme-fernet-key-generate-with-cryptography"

    CORS_ORIGINS: list[str] = ["http://localhost:5190"]
    FRONTEND_URL: str = "http://localhost:5190"

    DOCUMENTS_STORAGE_PATH: str = r"E:\PROGRAMACION\Citi-Platform\storage\documents"


settings = Settings()
