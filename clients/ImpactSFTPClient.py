import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SFTPConfig:
    host: str
    port: int
    username: str
    password: str | None = None
    remote_dir: str = "."
    private_key_path: str | None = None


def config_from_app_config(config):
    nested = (config or {}).get("impact_sftp", {})

    host = nested.get("host") or os.getenv("IMPACT_SFTP_HOST")
    username = nested.get("username") or os.getenv("IMPACT_SFTP_USERNAME")
    password = nested.get("password") or os.getenv("IMPACT_SFTP_PASSWORD")
    private_key_path = nested.get("private_key_path") or os.getenv("IMPACT_SFTP_PRIVATE_KEY_PATH")
    remote_dir = nested.get("remote_dir") or os.getenv("IMPACT_SFTP_REMOTE_DIR") or "."
    port = nested.get("port") or os.getenv("IMPACT_SFTP_PORT") or 22

    if not host or not username or (not password and not private_key_path):
        return None

    return SFTPConfig(
        host=host,
        port=int(port),
        username=username,
        password=password,
        remote_dir=remote_dir,
        private_key_path=private_key_path,
    )


class ImpactSFTPClient:
    def __init__(self, config: SFTPConfig):
        self.config = config

    def upload_file(self, local_path):
        try:
            import paramiko
        except ImportError as exc:
            raise RuntimeError("paramiko is required for SFTP upload. Install dependencies from requirements.txt.") from exc

        transport = paramiko.Transport((self.config.host, self.config.port))
        try:
            connect_kwargs = {
                "username": self.config.username,
            }
            if self.config.private_key_path:
                connect_kwargs["pkey"] = paramiko.RSAKey.from_private_key_file(self.config.private_key_path)
            else:
                connect_kwargs["password"] = self.config.password

            transport.connect(**connect_kwargs)
            sftp = paramiko.SFTPClient.from_transport(transport)
            try:
                remote_name = os.path.basename(local_path)
                remote_path = f"{self.config.remote_dir.rstrip('/')}/{remote_name}"
                sftp.put(local_path, remote_path)
                return remote_path
            finally:
                sftp.close()
        finally:
            transport.close()
