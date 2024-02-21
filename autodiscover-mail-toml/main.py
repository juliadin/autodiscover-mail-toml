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

from fastapi import FastAPI, Response, HTTPException
import jinja2

app = FastAPI()

config_file = pathlib.Path("../domains.toml")


def get_config(domain: str = "", local: str = ""):
    config = tomllib.loads(config_file.read_text())
    context = get_context(config, domain, local)
    return context


def get_context(config, domain: str = "", local: str = ""):
    print(config.keys())
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
    try:
        local, domain = emailaddress.split("@")
    except ValueError:
        local, domain = ("", "")
    config = get_config(domain, local)
    return jinja2.Template(
        """<?xml version="1.0"?>
<clientConfig version="1.1">
 <emailProvider>
{% for domain in domains %}
    <domain>{{ domain }}</domain>
{% endfor %}
    {% if name_display is defined %}<displayName>{{ name_display }}</displayName>{% endif %}
    {% if name_short is defined %}<displayShortName>{{ name_short }}</displayShortName>{% endif %}
  <incomingServer type="imap">
    {% if imap_host is defined %}<hostname>{{ imap_host }}</hostname>{% endif %}
    {% if imap_port is defined %}<port>{{ imap_port }}</port>{% endif %}
    {% if imap_type is defined %}<socketType>{{ imap_type }}</socketType>{% endif %}
    {% if imap_auth is defined %}
        {% for auth in imap_auth %}<authentication>{{ auth }}</authentication>{% endfor %}
    {% endif %}
    {% if username is defined %}<username>{{ username }}</username>{% endif %}
  </incomingServer>
  <outgoingServer type="smtp">
    {% if smtp_host is defined %}<hostname>{{ smtp_host }}</hostname>{% endif %}
    {% if smtp_port is defined %}<port>{{ smtp_port }}</port>{% endif %}
    {% if smtp_type is defined %}<socketType>{{ smtp_type }}</socketType>{% endif %}
    {% if smtp_auth is defined %}
        {% for auth in smtp_auth %}<authentication>{{ auth }}</authentication>{% endfor %}
    {% endif %}
    {% if username is defined %}<username>{{ username }}</username>{% endif %}
  </outgoingServer>
  </emailProvider>
</clientConfig>"""
    ).render(config)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/mail/config-v1.1.xml")
async def get_xml(emailaddress: str = ""):
    return Response(craft_xml(emailaddress=emailaddress), media_type="application/xml")
