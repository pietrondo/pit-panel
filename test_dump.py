import tarfile
from pathlib import Path
import os
import io

def create_tar():
    backup_dir = Path("/tmp/test_backup")
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / "test.tar.gz"

    app_dir = Path("/tmp/app_dir")
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "test.txt").write_text("hello")

    db_dump_content = b"this is a db dump"

    try:
        with tarfile.open(path, "w:gz") as tar:
            # Add app dir
            tar.add(app_dir, arcname="app")

            # Add DB dump from memory
            info = tarfile.TarInfo(name="app/database_dump.sql")
            info.size = len(db_dump_content)
            tar.addfile(info, io.BytesIO(db_dump_content))

    except Exception as e:
        print(e)

    # verify
    with tarfile.open(path, "r:gz") as tar:
        for member in tar.getmembers():
            print(member.name)
            if member.name.endswith(".sql"):
                f = tar.extractfile(member)
                if f:
                    print(f.read())

create_tar()
