import datetime
import logging
import tarfile
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from pit_panel.config import Settings
from pit_panel.core.docker_ops import DockerManager
from pit_panel.core.notifier import notify_app_backup
from pit_panel.db.models import AuditLog, Subdomain

logger = logging.getLogger(__name__)

def _get_db_service_info(compose_path: Path, env_path: Path) -> tuple | None:
    import yaml
    try:
        with open(compose_path) as f:
            data = yaml.safe_load(f)
        if not data or "services" not in data:
            return None
        env_vars = {}
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")
        def _resolve(key: str, cfg: dict) -> str:
            val = cfg.get(key, "")
            if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
                inner = val[2:-1]
                if ":-" in inner:
                    inner, default = inner.split(":-", 1)
                    return env_vars.get(inner, default)
                return env_vars.get(inner, val)
            if isinstance(val, str) and val.startswith("$"):
                return env_vars.get(val[1:], val)
            return str(val or "")
        for name, svc in data["services"].items():
            image = svc.get("image", "").lower()
            cfg = svc.get("environment", {})
            if isinstance(cfg, list):
                cfg = {kv.split("=", 1)[0]: kv.split("=", 1)[1] for kv in cfg if "=" in kv}
            if "postgres" in image:
                return (
                    name, "postgres",
                    _resolve("POSTGRES_USER", cfg),
                    _resolve("POSTGRES_PASSWORD", cfg),
                    _resolve("POSTGRES_DB", cfg),
                )
            if "mysql" in image or "mariadb" in image:
                u = _resolve("MYSQL_USER", cfg)
                p = _resolve("MYSQL_PASSWORD", cfg) or _resolve("MYSQL_ROOT_PASSWORD", cfg)
                dbn = _resolve("MYSQL_DATABASE", cfg)
                if not u:
                    u = "root"
                    p = _resolve("MYSQL_ROOT_PASSWORD", cfg) or p
                return name, "mysql", u, p, dbn
    except Exception as e:
        logger.warning(f"Failed to parse DB info from {compose_path}: {e}")
    return None

async def perform_app_backup(
    sd: Subdomain, db: AsyncSession, settings: Settings,
    user_id: int | None = None, ip: str | None = None, user_agent: str | None = None,
) -> dict[str, Any]:
    app_dir = Path(settings.apps_dir) / sd.subdomain
    backup_dir = Path(settings.data_dir) / "backups" / sd.subdomain
    backup_dir.mkdir(parents=True, exist_ok=True)
    docker_mgr = DockerManager(settings.apps_dir)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{sd.subdomain}_{ts}"
    path = backup_dir / f"{name}.tar.gz"
    try:
        db_dump = None
        compose_path = Path(settings.apps_dir) / sd.subdomain / "docker-compose.yml"
        env_path = Path(settings.apps_dir) / sd.subdomain / ".env"
        db_info = _get_db_service_info(compose_path, env_path)
        if db_info:
            svc_name, db_type, db_user, db_pass, db_name = db_info
            dump_text = None
            if db_type == "postgres":
                db_name_fmt = db_name or "postgres"
                cmd = ["pg_dump", "-U", db_user or "postgres", db_name_fmt]
                env = {"PGPASSWORD": db_pass} if db_pass else None
                r = await docker_mgr.exec_command(sd.subdomain, svc_name, cmd, env=env)
                dump_text = r.get("stdout") if r.get("success") else None
            elif "mysql" in db_type:
                pw_flag = f"-p{db_pass}" if db_pass else ""
                cmd = ["mysqldump", "--hex-blob", "-u", db_user or "root", pw_flag, db_name or "mysql"]  # noqa: E501
                r = await docker_mgr.exec_command(sd.subdomain, svc_name, cmd)
                dump_text = r.get("stdout") if r.get("success") else None
            if dump_text:
                db_dump = backup_dir / f"{name}_db_dump.sql"
                db_dump.write_text(dump_text)
        with tarfile.open(path, "w:gz") as tar:
            tar.add(app_dir, arcname=sd.subdomain)
            if db_dump and db_dump.exists():
                tar.add(db_dump, arcname=f"{sd.subdomain}/database_dump.sql")
                db_dump.unlink()
        size = path.stat().st_size
        sz_mb = size / 1024 / 1024
        size_str = f"{sz_mb:.1f} MB" if sz_mb > 1 else f"{size / 1024:.0f} KB"
        db.add(AuditLog(
            user_id=user_id, action="app_backup",
            target_type="subdomain", target_id=sd.id,
            details={"name": name, "size": size},
            ip=ip, user_agent=user_agent,
        ))
        await db.commit()
        await notify_app_backup(sd.subdomain, name, size_str)
        return {"success": True, "name": name, "size_str": size_str, "size": size}
    except Exception as e:
        logger.error(f"Backup error for {sd.subdomain}: {e}", exc_info=True)
        if path.exists():
            path.unlink()
        return {"success": False, "error": str(e)}

async def scheduled_backup_loop() -> None:
    import asyncio

    from sqlalchemy import select

    from pit_panel.config import get_settings
    from pit_panel.db.session import get_sessionmaker
    sessionmaker = get_sessionmaker()
    while True:
        try:
            settings = get_settings()
            if settings.backup_enabled:
                async with sessionmaker() as db:
                    stmt = select(Subdomain).where(Subdomain.app_type.is_not(None))
                    result = await db.execute(stmt)
                    subdomains = result.scalars().all()
                    for sd in subdomains:
                        logger.info(f"Running scheduled backup for {sd.subdomain}")
                        await perform_app_backup(sd=sd, db=db, settings=settings)
                        backup_dir = Path(settings.data_dir) / "backups" / sd.subdomain
                        if backup_dir.exists():
                            now = datetime.datetime.now().timestamp()
                            retention_seconds = settings.backup_retention_days * 86400
                            for f in backup_dir.glob("*.tar.gz"):
                                if f.is_file():
                                    try:
                                        mtime = f.stat().st_mtime
                                        if now - mtime > retention_seconds:
                                            f.unlink()
                                            logger.info(f"Deleted old backup: {f.name}")
                                    except Exception as e:
                                        logger.error(f"Error checking/deleting old backup {f}: {e}")
        except Exception as e:
            logger.error(f"Error in scheduled backup loop: {e}", exc_info=True)
        await asyncio.sleep(86400)
