from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    db_host: str
    db_port: int = 25060
    db_user: str
    db_password: str
    db_name: str
    db_sslmode: str = "require"

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
