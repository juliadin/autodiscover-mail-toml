"""Small WSGI service to implement Mozilla autodiscovery for small mail providers"""

import dataclasses
import logging
import pathlib
import re
import tomllib
import typing

import jinja2

from typing import Any
from fastapi import FastAPI, Response, HTTPException

#     Copyright (C) 2024  Julia Brunenberg
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.


app = FastAPI()

config_file = pathlib.Path("domains.toml")
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
                logger.warning(f"looking up references for {name} in {key}")
                try:
                    new_name = v.self_reference(name, lookup_source=lookup_source)
                except KeyError:
                    pass
        if name in self.static_references.keys():
            logger.warning(
                f" found {self.static_references[name]} in static keys for {name}"
            )
            new_name = self.static_references[name]
        lookup = name.strip(self.prefix)
        logger.warning(f"looking up references for {lookup} locally")
        if lookup in self.__dict__.keys():
            logger.warning(f" found {self.__dict__[lookup]} locally for {lookup}")
            new_name = self.__dict__[lookup]
        logger.warning(f" Returning {new_name}")
        if new_name is None:
            raise KeyError(f"{name} not found")
        return self.value_proxy(new_name, lookup_source=lookup_source)

    def value_proxy(self, name: str, lookup_source: "ConfigClass") -> typing.Any:
        logger.warning(f"{self}")

        new_value: str = name
        for placeholder_match in value_match.finditer(new_value):
            matched_string = placeholder_match.expand(value_template)
            logger.warning(f"looking up {matched_string} in '{new_value}'")
            try:
                replacement = lookup_source.self_reference(
                    placeholder_match.groupdict()["name"], lookup_source=lookup_source
                )
            except KeyError:
                raise
            else:
                new_value = new_value.replace(matched_string, replacement)
        logger.warning(f"{self.__class__.__name__} returns {new_value}")
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


def get_config(email_address: EmailAddress) -> dict[str, str | list[str]]:
    """Open, parse and layer the config for the current request
    and return the context to be used in jinja

    :param email_address: The email address to generate the context for
    :type email_address: EmailAddress
    :return: The jinja2.Context to be used in jinja
    :rtype: dict[str, str | list[str]]
    """
    config = tomllib.loads(config_file.read_text(encoding="utf-8"))
    context = get_context(config, email_address)
    return context


def get_context(
    config: dict[Any, Any], email_address: EmailAddress
) -> dict[str, str | list[str]]:
    """Layer the context to be used in jinja

        user.<email_address> takes precedence over
        domain.<domain_name> takes precedence over
        provider

    :param config: The parsed toml as dict
    :param email_address: The email address to generate the context for
    :type email_address: EmailAddress
    :return: The dict to be used in the jinja2 template
    :rtype: dict[str, str | list[str]]
    """
    if email_address.domain:
        if email_address.domain not in config.get("provider", {}).get("domains", []):
            if email_address.domain not in config.get("domain", {}).keys():
                if (
                    f"{email_address.local_part}@{email_address.domain}"
                    not in config.get("user", {}).keys()
                ):
                    raise HTTPException(status_code=404, detail="No such configuration")
    base = config["provider"].copy()
    try:
        for key in config["domain"][email_address.domain].keys():
            base[key] = config["domain"][email_address.domain][key]
        base["domains"] = [email_address.domain]
    except KeyError:
        pass
    try:
        addr = f"{email_address.local_part}@{email_address.domain}"
        for key in config["user"][addr].keys():
            base[key] = config["user"][addr][key]
        base["domains"] = [email_address.domain]
    except KeyError:
        pass

    base["address"] = email_address
    context = Provider()
    context.update_from_config(base)
    context.resolve_references()
    logger.warning(context)
    return context.__dict__


def craft_mozilla_xml(email_address: EmailAddress = EmailAddress.from_string("")):
    """Generate an XML string from the email address by templating it with the resulting context
    Format taken from https://wiki.mozilla.org/Thunderbird:Autoconfiguration:ConfigFileFormat

    :param email_address: The email address of the request
    :type email_address: str
    :return: The XML string
    :rtype: str
    """
    config = get_config(email_address)
    return jinja2.Template(
        """<?xml version="1.0"?>
<clientConfig version="1.1">
 <emailProvider id="{{ id|default('provider') }}">
{% for domain in domains %}
    <domain>{{ domain }}</domain>
{% endfor %}
    {% if name_display is defined %}<displayName>{{ name_display }}</displayName>{% endif %}
    {% if name_short is defined %}<displayShortName>{{ name_short }}</displayShortName>{% endif %}
  <incomingServer type="{{ in_server.type }}">
    <hostname>{{ in_server.host }}</hostname>
    <port>{{ in_server.port }}</port>
    <socketType>{{ in_server.type }}</socketType>
    <username>{{ in_server.user }}</username>
        {% for auth in in_server.auth %}<authentication>{{ auth }}</authentication>{% endfor %}
  </incomingServer>
  <outgoingServer type="{{ out_server.type }}">
    <hostname>{{ out_server.host }}</hostname>
    <port>{{ out_server.port }}</port>
    <socketType>{{ out_server.type }}</socketType>
    <username>{{ out_server.user }}</username>
        {% for auth in out_server.auth %}<authentication>{{ auth }}</authentication>{% endfor %}
  </outgoingServer>
  </emailProvider>
</clientConfig>"""
    ).render(config)


@app.get("/mail/config-v1.1.xml")
async def get_xml(emailaddress: str = ""):
    """the xml document for auto-configuration"""
    return Response(
        craft_mozilla_xml(email_address=EmailAddress.from_string(emailaddress)),
        media_type="application/xml",
    )
