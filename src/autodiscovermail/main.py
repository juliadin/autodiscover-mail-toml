"""Small WSGI service to implement Mozilla autodiscovery for small mail providers"""

import dataclasses

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

import pathlib
import tomllib
from typing import Any

from fastapi import FastAPI, Response, HTTPException
import jinja2

app = FastAPI()

config_file = pathlib.Path("domains.toml")


@dataclasses.dataclass(frozen=True, kw_only=True)
class EmailAddress:
    full: str
    domain: str
    local_part: str

    @classmethod
    def from_string(cls, address: str) -> "EmailAddress":
        try:
            local_part, domain = address.split("@")
        except ValueError:
            local_part, domain = ("", "")
        return cls(full=address, domain=domain, local_part=local_part)


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


def deep_replace(context: dict[str, str | list[str]]) -> dict[str, str | list[str]]:
    for key, value in context.items():
        if isinstance(value, list):
            new_value = []
            for item in value:
                new_value.append(string_replace(item))
            context[key] = new_value
        if isinstance(value, str):
            context[key] = string_replace(value)

    return context


def string_replace(string: str) -> str:
    string = string.replace("#")
    return string


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

    return base


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
  <incomingServer type="imap">
    {% if imap_host is defined %}<hostname>{{ imap_host }}</hostname>{% endif %}
    {% if imap_port is defined %}<port>{{ imap_port }}</port>{% endif %}
    {% if imap_type is defined %}<socketType>{{ imap_type }}</socketType>{% endif %}
    {% if username is defined %}<username>{{ username }}</username>{% endif %}
    {% if imap_auth is defined %}
        {% for auth in imap_auth %}<authentication>{{ auth }}</authentication>{% endfor %}
    {% endif %}
  </incomingServer>
  <outgoingServer type="smtp">
    {% if smtp_host is defined %}<hostname>{{ smtp_host }}</hostname>{% endif %}
    {% if smtp_port is defined %}<port>{{ smtp_port }}</port>{% endif %}
    {% if smtp_type is defined %}<socketType>{{ smtp_type }}</socketType>{% endif %}
    {% if username is defined %}<username>{{ username }}</username>{% endif %}
    {% if smtp_auth is defined %}
        {% for auth in smtp_auth %}<authentication>{{ auth }}</authentication>{% endfor %}
    {% endif %}
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
