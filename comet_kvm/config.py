"""Local endpoints and credentials; never exposed through MCP."""

import asyncio
import json
import os
import ssl
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    model_validator,
)

from . import CometError


class Endpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    username: str = "admin"
    password: SecretStr | None = None
    password_command: list[str] | None = Field(default=None, min_length=1)
    ca_file: str | None = None

    @model_validator(mode="after")
    def validate_endpoint(self):
        url = urlsplit(self.url)
        if (
            url.scheme not in {"https", "http"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError(
                "url must be an HTTP(S) origin without credentials or a path"
            )
        if (self.password is None) == (self.password_command is None):
            raise ValueError("provide exactly one of password or password_command")
        self.url = self.url.rstrip("/")
        return self

    def tls_context(self):
        return ssl.create_default_context(
            cafile=str(Path(self.ca_file).expanduser()) if self.ca_file else None
        )

    async def resolve_password(self):
        if self.password is not None:
            return self.password.get_secret_value()
        process = await asyncio.create_subprocess_exec(
            *self.password_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(30):
                output, _ = await process.communicate()
            if process.returncode or not output:
                raise CometError("Password command failed or returned no password")
            return output.removesuffix(b"\n").decode("utf-8")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comets: dict[str, Endpoint]


def load_config(path: str | None = None) -> Configuration:
    path = path or os.environ.get("COMET_KVM_CONFIG", "~/.config/comet-kvm/config.json")
    try:
        return Configuration.model_validate(
            json.loads(Path(path).expanduser().read_text())
        )
    except ValidationError as error:
        # Report locations and reasons only; input values can include passwords.
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}"
            for e in error.errors(include_input=False, include_url=False)
        )
        raise RuntimeError(f"Invalid Comet configuration: {problems}") from None
    except (OSError, ValueError):
        raise RuntimeError(
            "Cannot load Comet configuration; check its path and config.example.json"
        ) from None
