from enum import StrEnum

from keboola.component.exceptions import UserException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ExtractionMode(StrEnum):
    PRESET = "Preset"
    CUSTOM = "Custom"


class SourceConfig(BaseModel):
    extraction_mode: ExtractionMode = ExtractionMode.PRESET
    module: str = ""
    entity: str = ""
    org_id: int | None = None
    ledger_id: int | None = None
    custom_query: str = ""


class DestinationConfig(BaseModel):
    output_table: str = ""
    incremental: bool = False
    primary_key: list[str] = Field(default_factory=list)


class SSHKeys(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    private: str = Field(alias="#private", default="")
    public: str = ""


class SSHOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    enabled: bool = False
    user: str = ""
    ssh_host: str = Field(alias="sshHost", default="")
    ssh_port: int = Field(alias="sshPort", default=22)
    keys: SSHKeys = Field(default_factory=SSHKeys)


class Configuration(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    # Connection fields — flattened from configSchema "connection" block
    db_host: str = ""
    db_port: int = 1521
    db_service_name: str = ""
    db_user: str = ""
    db_password: str = Field(alias="#db_password", default="")

    ssh_options: SSHOptions = Field(default_factory=SSHOptions)

    # Row-level extraction config
    source: SourceConfig = Field(default_factory=SourceConfig)
    destination: DestinationConfig = Field(default_factory=DestinationConfig)

    debug: bool = False

    @model_validator(mode="before")
    @classmethod
    def _flatten_connection(cls, data: dict) -> dict:
        if isinstance(data, dict) and "connection" in data:
            conn = data.pop("connection")
            if isinstance(conn, dict):
                data = {**data, **conn}
        return data

    def __init__(self, **data: object) -> None:
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Configuration error: {', '.join(error_messages)}")

    def validate_connection(self) -> None:
        if not self.db_host:
            raise UserException("'db_host' is required in connection settings.")
        if not self.db_service_name:
            raise UserException("'db_service_name' is required in connection settings.")
        if not self.db_user:
            raise UserException("'db_user' is required in connection settings.")
        if not self.db_password:
            raise UserException("'db_password' is required in connection settings.")
        if self.ssh_options.enabled:
            if not self.ssh_options.ssh_host:
                raise UserException("'sshHost' is required when SSH tunnel is enabled.")
            if not self.ssh_options.user:
                raise UserException("SSH tunnel 'user' is required.")
            if not self.ssh_options.keys.private:
                raise UserException("SSH private key is required when SSH tunnel is enabled.")

    def validate_row(self) -> None:
        self.validate_connection()
        if self.source.extraction_mode == ExtractionMode.PRESET:
            if not self.source.module:
                raise UserException("'module' is required in preset mode.")
            if not self.source.entity:
                raise UserException("'entity' is required in preset mode.")
        else:
            if not self.source.custom_query:
                raise UserException("'custom_query' is required in custom mode.")
        if not self.destination.output_table:
            raise UserException("'output_table' is required.")
