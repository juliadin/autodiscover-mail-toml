import logging
import pathlib

logger = logging.getLogger(__name__)


template_base_path = pathlib.Path(".")
template_base: dict[str, str] = {
    "config-v1.1.xml": """<?xml version="1.0"?>
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
}


def get(filename: str, base_path: pathlib.Path = template_base_path) -> str:
    filepath = pathlib.Path(filename)
    template_file = base_path / filepath.with_suffix(".j2")
    if not template_file.exists():
        logging.warning(
            f"Template for file {filename} does not exist. Creating {template_file.absolute()}"
        )
        template_file.write_text(template_base.get(filename, ""))
    return template_file.read_text()
