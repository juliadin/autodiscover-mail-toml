"""Small WSGI service to implement Mozilla autodiscovery for small mail providers"""

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


def get_config(domain: str = "", local: str = "") -> dict[str, str | list[str]]:
    """Open, parse and layer the config for the current request
    and return the context to be used in jinja

    :param domain: The domain name of the email address requested
    :type domain: str
    :param local: The local part of the email address requested
    :type local: str
    :return: The jinja2.Context to be used in jinja
    :rtype: dict[str, str | list[str]]
    """
    config = tomllib.loads(config_file.read_text(encoding="utf-8"))
    context = get_context(config, domain, local)
    return context


def get_context(
    config: dict[Any, Any], domain: str = "", local: str = ""
) -> dict[str, str | list[str]]:
    """Layer the context to be used in jinja

        user.<emailaddress> takes precedence over
        domain.<domainname> takes precedence over
        provider

    :param config: The parsed toml as dict
    :param domain: The domain name of the email address requested
    :type domain: str
    :param local: The local part of the email address requested
    :type local: str
    :return: The dict to be used in the jinja2 template
    :rtype: dict[str, str | list[str]]
    """
    if domain:
        if domain not in config.get("provider", {}).get("domains", []):
            if domain not in config.get("domain", {}).keys():
                if f"{local}@{domain}" not in config.get("user", {}).keys():
                    raise HTTPException(status_code=404, detail="No such configuration")
    base = config["provider"].copy()
    try:
        for key in config["domain"][domain].keys():
            base[key] = config["domain"][domain][key]
        base["domains"] = [domain]
    except KeyError:
        pass
    try:
        addr = f"{local}@{domain}"
        for key in config["user"][addr].keys():
            base[key] = config["user"][addr][key]
        base["domains"] = [domain]
    except KeyError:
        pass
    return base


def craft_xml(emailaddress: str = ""):
    """Generate an XML string from the email address by tempating it with the resulting context

    :param emailaddress: The email address of the request
    :type emailaddress: str
    :return: The XML string
    :rtype: str
    """
    try:
        local, domain = emailaddress.split("@")
    except ValueError:
        local, domain = ("", "")
    config = get_config(domain, local)
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
    return Response(craft_xml(emailaddress=emailaddress), media_type="application/xml")
