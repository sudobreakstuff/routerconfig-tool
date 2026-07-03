from __future__ import annotations

from dataclasses import dataclass, field
from jinja2 import Environment, BaseLoader, Template


_jinja_env = Environment(loader=BaseLoader(), autoescape=False)


@dataclass
class TemplateVariable:
    name: str
    label: str
    type: str = "string"
    default: str = ""
    required: bool = False
    description: str = ""
    options: list[str] | None = None


@dataclass
class RenderedConfig:
    commands: list[str]
    variables_used: dict


def parse_template(template_content: str) -> list[TemplateVariable]:
    variables: list[TemplateVariable] = []
    seen = set()
    template = _jinja_env.from_string(template_content)

    try:
        ast = _jinja_env.parse(template_content)
        for node in ast.find_all(lambda n: True):
            if hasattr(node, "name") and hasattr(node, "test"):
                pass

        import re
        var_pattern = re.findall(r'\{\{\s*(\w+)\s*\}\}', template_content)
        for_pattern = re.findall(r'\{%\s*for\s+\w+\s+in\s+(\w+)\s*%\}', template_content)

        for v in var_pattern:
            if v not in seen:
                seen.add(v)
                variables.append(TemplateVariable(
                    name=v,
                    label=v.replace("_", " ").title(),
                ))

        for v in for_pattern:
            if v not in seen:
                seen.add(v)
                variables.append(TemplateVariable(
                    name=v,
                    label=v.replace("_", " ").title(),
                    type="list",
                ))
    except Exception:
        pass

    return variables


def render_commands(template_content: str, variables: dict) -> RenderedConfig:
    template = _jinja_env.from_string(template_content)
    rendered = template.render(**variables)
    commands = [line.strip() for line in rendered.split("\n") if line.strip() and not line.strip().startswith("#")]
    return RenderedConfig(commands=commands, variables_used=variables)


def render_config_template(template_obj: dict, variables: dict) -> RenderedConfig:
    if template_obj.get("type") == "jinja2" and template_obj.get("jinja2_template"):
        return render_commands(template_obj["jinja2_template"], variables)

    commands = template_obj.get("config_commands", [])
    if isinstance(commands, str):
        commands = [commands]

    rendered = []
    for cmd in commands:
        rendered_cmd = cmd
        for key, val in variables.items():
            rendered_cmd = rendered_cmd.replace(f"${{{key}}}", str(val))
            rendered_cmd = rendered_cmd.replace(f"{{{{{key}}}}}", str(val))
        rendered.append(rendered_cmd)

    return RenderedConfig(commands=rendered, variables_used=variables)


BUILTIN_TEMPLATES = {
    "jenny-internet-bridge": {
        "name": "Jenny Internet - Bridge Mode",
        "description": "Disable DHCP, enable bridge/CPE passthrough. Standard Jenny Internet CPE setup.",
        "vendor": "generic",
        "is_default": True,
        "config_commands": [
            "/ip dhcp-server disable [find]",
            "/ip dhcp-server remove [find]",
            "/ip dhcp-client add interface=ether1 disabled=no",
            "/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade",
            "/system identity set name=\"{{{device_name}}}\"",
        ],
    },
    "mikrotik-ap-bridge": {
        "name": "MikroTik - AP Bridge Mode",
        "description": "Standard MikroTik setup as bridge/AP behind CPE. DHCP off, bridge mode on.",
        "vendor": "mikrotik",
        "is_default": True,
        "config_commands": [
            "/ip dhcp-server disable [find]",
            "/ip dhcp-server remove [find]",
            "/ip dhcp-client add interface=ether1 disabled=no add-default-route=yes use-peer-dns=yes",
            "/interface bridge add name=bridge1",
            "/interface bridge port add bridge=bridge1 interface=ether2",
            "/interface bridge port add bridge=bridge1 interface=wlan1",
            "/ip address add address={{{lan_ip}}}/24 interface=bridge1",
            "/interface wireless set [find] ssid=\"{{{ssid}}}\" mode=ap-bridge band=2ghz-b/g/n",
            "/interface wireless security-profiles set [find] authentication-types=wpa2-psk mode=dynamic-keys wpa2-pre-shared-key=\"{{{wifi_password}}}\"",
            "/user set [find name=admin] password=\"{{{admin_password}}}\"",
            "/system identity set name=\"{{{device_name}}}\"",
        ],
    },
    "tplink-ap-bridge": {
        "name": "TP-Link - AP Bridge Mode",
        "description": "TP-Link setup as AP behind CPE. DHCP disabled.",
        "vendor": "tplink",
        "is_default": True,
        "config_commands": [
            "uci set network.lan.proto=dhcp",
            "uci delete network.lan.ipaddr",
            "uci delete network.lan.netmask",
            "uci set dhcp.lan.ignore=1",
            "uci set wireless.@wifi-iface[0].ssid={{{ssid}}}",
            "uci set wireless.@wifi-iface[0].key={{{wifi_password}}}",
            "uci set wireless.@wifi-iface[0].encryption=psk2",
            "uci commit",
            "wifi reload",
        ],
    },
    "ubiquiti-ap-bridge": {
        "name": "Ubiquiti - AP Bridge Mode",
        "description": "Ubiquiti setup as bridge/AP. DHCP disabled.",
        "vendor": "ubiquiti",
        "is_default": True,
        "config_commands": [
            "sed -i 's/netmode=.*/netmode=bridge/' /tmp/system.cfg",
            "sed -i 's/dhcpserver.status=.*/dhcpserver.status=disabled/' /tmp/system.cfg",
            "sed -i 's/radio.1.ssid=.*/radio.1.ssid={{{ssid}}}/' /tmp/system.cfg",
            "sed -i 's/wpa.passphrase=.*/wpa.passphrase={{{wifi_password}}}/' /tmp/system.cfg",
            "save && /usr/etc/rc.d/rc.softrestart restart",
        ],
    },
}
