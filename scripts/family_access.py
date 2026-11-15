import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chromantis.config import AppConfig
from chromantis.db.family_access import FamilyAccess
from chromantis.db.repository import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestiona el acceso familiar local de Chromantis.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("invite", help="Crea un código de un solo uso durante 24 horas.").add_argument("label")
    commands.add_parser("list", help="Lista invitaciones y sesiones vigentes.")
    commands.add_parser("revoke", help="Elimina una invitación o sesión.").add_argument("id", type=int)
    args = parser.parse_args()

    config = AppConfig.from_env()
    repository = Repository(config.sqlite_path)
    repository.init_schema()
    access = FamilyAccess(repository)
    if args.command == "invite":
        if not (config.api_chat_tokens or config.api_token):
            parser.error("Configura primero un token de API para proteger el archivo.")
        try:
            identity, code = access.invite(args.label)
        except ValueError as error:
            parser.error(str(error))
        print(f"Invitación {identity}. Abre «Acceso familiar» en el navegador y pega el código en 24 horas.")
        print(code)
    elif args.command == "revoke":
        if not 1 <= args.id < 2**63 or not access.revoke(args.id):
            parser.error("El ID no corresponde a una invitación o sesión.")
        print(f"Acceso {args.id} revocado.")
    else:
        for row in access.list():
            kind = "invitación" if row["kind"] == "invite" else "sesión"
            print(f'{row["id"]}  {row["label"]}  {kind}  {row["expires_at"]}')


if __name__ == "__main__":
    main()
