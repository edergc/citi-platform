"""Creates the base Administrator role and the first superuser. Run once: python -m app.initial_data"""

import getpass

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.identity import Role, User


def run() -> None:
    db = SessionLocal()
    try:
        admin_role = db.scalar(select(Role).where(Role.name == "Administrator"))
        if admin_role is None:
            admin_role = Role(name="Administrator", description="Acceso total a la plataforma", is_system_role=True)
            db.add(admin_role)
            db.commit()
            print("Rol 'Administrator' creado.")

        if db.scalar(select(User).where(User.is_superuser.is_(True))) is not None:
            print("Ya existe un superusuario. Nada que hacer.")
            return

        print("Creando el primer superusuario de CITI Platform.")
        email = input("Email: ").strip()
        username = input("Username: ").strip()
        full_name = input("Nombre completo: ").strip()
        password = getpass.getpass("Password: ")

        user = User(
            email=email,
            username=username,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        db.commit()
        print(f"Superusuario '{email}' creado correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
