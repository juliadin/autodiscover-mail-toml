"""Small WSGI service to implement Mozilla autodiscovery for small mail providers"""

import logging
import pathlib
import tomllib
from . import config
from . import template
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

logger = logging.getLogger(__name__)


def get_config(email_address: config.EmailAddress) -> dict[str, str | list[str]]:
    """Open, parse and layer the config for the current request
    and return the context to be used in jinja

    :param email_address: The email address to generate the context for
    :type email_address: EmailAddress
    :return: The jinja2.Context to be used in jinja
    :rtype: dict[str, str | list[str]]
    """
    config_data = tomllib.loads(config_file.read_text(encoding="utf-8"))
    context = get_context(config_data, email_address)
    return context


def get_context(
    config_data: dict[Any, Any], email_address: config.EmailAddress
) -> dict[str, str | list[str]]:
    """Layer the context to be used in jinja

        user.<email_address> takes precedence over
        domain.<domain_name> takes precedence over
        provider

    :param config_data: The parsed toml as dict
    :param email_address: The email address to generate the context for
    :type email_address: EmailAddress
    :return: The dict to be used in the jinja2 template
    :rtype: dict[str, str | list[str]]
    """
    if email_address.domain:
        if email_address.domain not in config_data.get("provider", {}).get(
            "domains", []
        ):
            if email_address.domain not in config_data.get("domain", {}).keys():
                if (
                    f"{email_address.local_part}@{email_address.domain}"
                    not in config_data.get("user", {}).keys()
                ):
                    raise HTTPException(status_code=404, detail="No such configuration")
    base = config_data["provider"].copy()
    try:
        for key in config_data["domain"][email_address.domain].keys():
            base[key] = config_data["domain"][email_address.domain][key]
        base["domains"] = [email_address.domain]
    except KeyError:
        pass
    try:
        addr = f"{email_address.local_part}@{email_address.domain}"
        for key in config_data["user"][addr].keys():
            base[key] = config_data["user"][addr][key]
        base["domains"] = [email_address.domain]
    except KeyError:
        pass

    base["address"] = email_address
    context = config.Provider()
    context.update_from_config(base)
    context.resolve_references()
    return context.__dict__


def craft_mozilla_xml(
    email_address: config.EmailAddress = config.EmailAddress.from_string(""),
):
    """Generate an XML string from the email address by templating it with the resulting context
    Format taken from https://wiki.mozilla.org/Thunderbird:Autoconfiguration:ConfigFileFormat

    :param email_address: The email address of the request
    :type email_address: str
    :return: The XML string
    :rtype: str
    """
    config_data = get_config(email_address)
    return jinja2.Template(template.get("config-v1.1.xml")).render(config_data)


@app.get("/mail/config-v1.1.xml")
async def get_xml(emailaddress: str = ""):
    """the xml document for auto-configuration"""
    return Response(
        craft_mozilla_xml(email_address=config.EmailAddress.from_string(emailaddress)),
        media_type="application/xml",
    )
