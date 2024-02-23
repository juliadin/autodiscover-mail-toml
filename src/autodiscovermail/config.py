import logging
import typing
import dataclasses
import re

value_match = re.compile(r"##(?P<name>[^#]+)##")
value_template = r"##\g<name>##"

logger = logging.getLogger(__name__)


@dataclasses.dataclass(kw_only=True)
class ConfigClass:
    _stack: list = dataclasses.field(default_factory=list)
    prefix: str = ""
    static_references = {
        "EMAILADDRESS": "##full_address##",
    }

    def update_from_config(self, config: dict) -> None:

        for key in self.__dict__.keys():
            v = self.__dict__.get(key)
            if isinstance(v, ConfigClass):
                v.update_from_config(config)
        for key in self.__dict__.keys():
            if key in ("prefix", "static_references"):
                continue
            config_key = f"{self.prefix}{key}"
            if config_key in config:
                self.__dict__[key] = config[config_key]

    def resolve_references(self, lookup_source: typing.Optional["ConfigClass"] = None):
        if lookup_source is None:
            lookup_source = self
        for key in self.__dict__.keys():
            v = self.__dict__.get(key)
            if isinstance(v, ConfigClass):
                v.resolve_references(lookup_source)

        for key, value in self.__dict__.items():
            if key in ("prefix", "static_references"):
                continue
            if isinstance(value, str):
                self.__dict__[key] = self.value_proxy(
                    value, lookup_source=lookup_source
                )

    def self_reference(self, name: str, lookup_source: "ConfigClass") -> typing.Any:
        new_name: str | None = None
        for key in self.__dict__.keys():
            v = self.__dict__.get(key)
            if isinstance(v, ConfigClass):
                logger.info(f"looking up references for {name} in {key}")
                try:
                    new_name = v.self_reference(name, lookup_source=lookup_source)
                except KeyError:
                    pass
        if name in self.static_references.keys():
            logger.debug(
                f" found {self.static_references[name]} in static keys for {name}"
            )
            new_name = self.static_references[name]
        lookup = name.strip(self.prefix)
        logger.info(f"looking up references for {lookup} locally")
        if lookup in self.__dict__.keys():
            logger.debug(f" found {self.__dict__[lookup]} locally for {lookup}")
            new_name = self.__dict__[lookup]
        logger.debug(f" Returning {new_name}")
        if new_name is None:
            raise KeyError(f"{name} not found")
        return self.value_proxy(new_name, lookup_source=lookup_source)

    def value_proxy(self, name: str, lookup_source: "ConfigClass") -> typing.Any:

        new_value: str = name
        for placeholder_match in value_match.finditer(new_value):
            matched_string = placeholder_match.expand(value_template)
            logger.debug(f"looking up {matched_string} in '{new_value}'")
            try:
                replacement = lookup_source.self_reference(
                    placeholder_match.groupdict()["name"], lookup_source=lookup_source
                )
            except KeyError:
                raise
            else:
                new_value = new_value.replace(matched_string, replacement)
        logger.debug(f"{self.__class__.__name__} returns {new_value}")
        return new_value


@dataclasses.dataclass(kw_only=True)
class EmailAddress(ConfigClass):
    full_address: str = ""
    domain: str = ""
    local_part: str = ""

    @classmethod
    def from_string(cls, address: str = "") -> "EmailAddress":
        try:
            local_part, domain = address.split("@")
        except ValueError:
            local_part, domain = ("", "")
        return cls(full_address=address, domain=domain, local_part=local_part)


@dataclasses.dataclass(kw_only=True)
class MailServer(ConfigClass):
    host: typing.Optional[str] = ""
    port: typing.Optional[int] = 0
    socket: typing.Optional[str] = "STARTTLS"
    type: typing.Optional[str] = ""
    auth: typing.Optional[tuple[str, ...]] = ("plain-password",)
    user: typing.Optional[str] = "%EMAILADDRESS%"


@dataclasses.dataclass(kw_only=True)
class InServer(MailServer):
    prefix: str = "in_"
    port: typing.Optional[int] = 143
    type: typing.Optional[str] = "imap"


@dataclasses.dataclass(kw_only=True)
class OutServer(MailServer):
    prefix: str = "out_"
    port: typing.Optional[int] = 587
    type: typing.Optional[str] = "smtp"


@dataclasses.dataclass(kw_only=True)
class Provider(ConfigClass):
    id: typing.Optional[str] = ""
    name_short: typing.Optional[str] = ""
    name_display: typing.Optional[str] = ""
    domains: typing.Optional[tuple[str, ...]] = tuple(
        "",
    )
    in_server: InServer = dataclasses.field(default_factory=InServer)
    out_server: OutServer = dataclasses.field(default_factory=OutServer)
    address: EmailAddress = dataclasses.field(default_factory=EmailAddress.from_string)
