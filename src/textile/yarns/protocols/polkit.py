"""
Modular PolicyKit (Polkit-1) Capability Yarn for Textile.
Provides full privilege check, custom .policy XML generation,
.rules JavaScript rule creation, and pkexec command execution.
Layer 50 (Desktop Protocol).
"""

import glob
import json
import logging
import os
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from typing import Any, Literal

try:
    from dbus_fast import Variant
except Exception:
    Variant = None

from textile.core.base import CapabilityTier, Yarn, strand
from textile.yarns.protocols.dbus_system import dbus_api

logger = logging.getLogger(__name__)

IMPLICIT_AUTH_MAP = {
    0: "no",
    1: "admin",
    2: "admin_keep",
    3: "yes",
    4: "auth_self",
    5: "auth_self_keep",
    6: "auth_admin",
    7: "auth_admin_keep",
}


class PolkitAPI:
    """Universal Linux Polkit-1 Authority & Privilege Management Controller."""

    def __init__(self):
        self._authority_dest = "org.freedesktop.PolicyKit1"
        self._authority_path = "/org/freedesktop/PolicyKit1/Authority"
        self._authority_iface = "org.freedesktop.PolicyKit1.Authority"

    def is_available(self) -> bool:
        try:
            res = dbus_api.run_sync(
                dbus_api.get_property(
                    bus="system",
                    destination=self._authority_dest,
                    path=self._authority_path,
                    interface=self._authority_iface,
                    property_name="BackendName",
                ),
                timeout=3.0,
            )
            return bool(res)
        except Exception:
            return os.path.exists("/usr/share/polkit-1/actions") or shutil.which("pkexec") is not None

    def check_authorization(
        self,
        action_id: str,
        details: dict[str, str] | None = None,
        allow_user_interaction: bool = False,
        pid: int | None = None,
    ) -> dict[str, Any]:
        target_pid = pid or os.getpid()
        subject = ("unix-process", {"pid": Variant("u", target_pid) if Variant else target_pid, "start-time": Variant("t", 0) if Variant else 0})
        det = details or {}
        flags = 1 if allow_user_interaction else 0
        cancellation_id = ""

        try:
            res = dbus_api.run_sync(
                dbus_api.call(
                    bus="system",
                    destination=self._authority_dest,
                    path=self._authority_path,
                    interface=self._authority_iface,
                    member="CheckAuthorization",
                    signature="(sa{sv})sa{ss}us",
                    body=[subject, action_id, det, flags, cancellation_id],
                ),
                timeout=60.0 if allow_user_interaction else 5.0,
            )

            if res and isinstance(res, (list, tuple)) and len(res) >= 3:
                is_auth = bool(res[0])
                is_challenge = bool(res[1])
                res_details = res[2] if isinstance(res[2], dict) else {}
                return {
                    "success": True,
                    "action_id": action_id,
                    "is_authorized": is_auth,
                    "is_challenge": is_challenge,
                    "details": res_details,
                    "result": res_details.get("polkit.result", "yes" if is_auth else ("challenge" if is_challenge else "no")),
                }
            return {"success": False, "error": f"Unexpected Polkit response: {res}"}
        except Exception as e:
            return {"success": False, "error": f"Polkit check failed: {e}"}

    def list_actions(self, filter_query: str | None = None) -> list[dict[str, Any]]:
        try:
            res = dbus_api.run_sync(
                dbus_api.call(
                    bus="system",
                    destination=self._authority_dest,
                    path=self._authority_path,
                    interface=self._authority_iface,
                    member="EnumerateActions",
                    signature="s",
                    body=["en_US.UTF-8"],
                ),
                timeout=5.0,
            )

            actions = []
            if res and isinstance(res, (list, tuple)):
                for item in res:
                    if isinstance(item, (list, tuple)) and len(item) >= 10:
                        act_id = str(item[0])
                        desc = str(item[1])
                        msg = str(item[2])
                        vendor = str(item[3])
                        imp_any = IMPLICIT_AUTH_MAP.get(item[6], str(item[6]))
                        imp_inact = IMPLICIT_AUTH_MAP.get(item[7], str(item[7]))
                        imp_act = IMPLICIT_AUTH_MAP.get(item[8], str(item[8]))

                        if filter_query:
                            q = filter_query.lower()
                            if q not in act_id.lower() and q not in desc.lower() and q not in vendor.lower():
                                continue

                        actions.append({
                            "action_id": act_id,
                            "description": desc,
                            "message": msg,
                            "vendor": vendor,
                            "implicit_any": imp_any,
                            "implicit_inactive": imp_inact,
                            "implicit_active": imp_act,
                        })

                if actions:
                    return actions
        except Exception as e:
            logger.debug(f"D-Bus EnumerateActions fallback: {e}")

        results = []
        for policy_file in glob.glob("/usr/share/polkit-1/actions/*.policy"):
            try:
                tree = ET.parse(policy_file)
                root = tree.getroot()
                vendor = root.findtext("vendor", "System")
                for act in root.findall("action"):
                    act_id = act.get("id", "")
                    desc = act.findtext("description", "")
                    msg = act.findtext("message", "")
                    defaults = act.find("defaults")
                    imp_any = defaults.findtext("allow_any", "auth_admin") if defaults is not None else "auth_admin"
                    imp_inact = defaults.findtext("allow_inactive", "auth_admin") if defaults is not None else "auth_admin"
                    imp_act = defaults.findtext("allow_active", "auth_admin_keep") if defaults is not None else "auth_admin_keep"

                    if filter_query:
                        q = filter_query.lower()
                        if q not in act_id.lower() and q not in desc.lower() and q not in vendor.lower():
                            continue

                    results.append({
                        "action_id": act_id,
                        "description": desc,
                        "message": msg,
                        "vendor": vendor,
                        "implicit_any": imp_any,
                        "implicit_inactive": imp_inact,
                        "implicit_active": imp_act,
                    })
            except Exception:
                continue

        return results

    def generate_policy(
        self,
        actions: list[dict[str, Any]],
        vendor: str = "Textile Desktop Intelligence",
        vendor_url: str = "https://github.com/textile",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        root = ET.Element("policyconfig")
        v_elem = ET.SubElement(root, "vendor")
        v_elem.text = vendor
        u_elem = ET.SubElement(root, "vendor_url")
        u_elem.text = vendor_url

        for act in actions:
            act_elem = ET.SubElement(root, "action", id=act.get("id", "com.textile.unnamed"))
            desc_elem = ET.SubElement(act_elem, "description")
            desc_elem.text = act.get("description", "Textile Action")
            msg_elem = ET.SubElement(act_elem, "message")
            msg_elem.text = act.get("message", "Authentication required.")
            def_elem = ET.SubElement(act_elem, "defaults")
            a_any = ET.SubElement(def_elem, "allow_any")
            a_any.text = act.get("allow_any", "auth_admin")
            a_inact = ET.SubElement(def_elem, "allow_inactive")
            a_inact.text = act.get("allow_inactive", "auth_admin")
            a_act = ET.SubElement(def_elem, "allow_active")
            a_act.text = act.get("allow_active", "auth_admin_keep")

        xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
        import xml.dom.minidom
        dom = xml.dom.minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ")

        if output_path:
            out = os.path.expanduser(output_path)
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                f.write(pretty_xml)
            return {"success": True, "path": out, "actions_count": len(actions), "xml": pretty_xml}

        return {"success": True, "actions_count": len(actions), "xml": pretty_xml}

    def generate_rule(
        self,
        rule_name: str,
        action_pattern: str,
        users: list[str] | None = None,
        groups: list[str] | None = None,
        result: str = "yes",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        res_enum = f"polkit.Result.{result.upper()}"
        users_list = [f'"{u}"' for u in (users or [])]
        groups_list = [f'"{g}"' for g in (groups or [])]

        conditions = []
        if action_pattern.endswith("*"):
            prefix = action_pattern[:-1]
            conditions.append(f'action.id.indexOf("{prefix}") === 0')
        else:
            conditions.append(f'action.id === "{action_pattern}"')

        if users_list:
            conditions.append(f'[{", ".join(users_list)}].indexOf(subject.user) !== -1')

        if groups_list:
            groups_checks = " || ".join([f'subject.isInGroup({g})' for g in groups_list])
            conditions.append(f"({groups_checks})")

        joined_conditions = " &&\n        ".join(conditions)

        js_content = f"""/* Polkit Rule: {rule_name} */
polkit.addRule(function(action, subject) {{
    if ({joined_conditions}) {{
        return {res_enum};
    }}
}});
"""
        if output_path:
            out = os.path.expanduser(output_path)
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                f.write(js_content)
            return {"success": True, "path": out, "rule_name": rule_name, "content": js_content}

        return {"success": True, "rule_name": rule_name, "content": js_content}

    def pkexec(
        self,
        command: str | list[str],
        user: str = "root",
        env: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        pkexec_bin = shutil.which("pkexec")
        if not pkexec_bin:
            return {"success": False, "error": "pkexec binary not found."}

        if isinstance(command, str):
            cmd_args = [pkexec_bin, "--user", user, "sh", "-c", command]
        else:
            cmd_args = [pkexec_bin, "--user", user] + list(command)

        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                env=exec_env,
                timeout=timeout_seconds,
            )
            elapsed = round(time.time() - start_time, 3)
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "elapsed_seconds": elapsed,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"pkexec timed out after {timeout_seconds}s."}
        except Exception as e:
            return {"success": False, "error": f"pkexec execution failed: {e}"}


polkit_api = PolkitAPI()


class Polkit(Yarn):
    def is_available(self) -> bool:
        return polkit_api.is_available()

    @strand(
        description="Check authorization for a Polkit action ID against org.freedesktop.PolicyKit1.Authority.",
        tier=CapabilityTier.OBSERVE,
    )
    def polkit_check_auth(
        self,
        action_id: str,
        details: str | None = None,
        allow_user_interaction: bool = False,
    ) -> dict[str, Any]:
        """Check authorization for a Polkit action ID against org.freedesktop.PolicyKit1.Authority.

        :param action_id: Polkit action ID.
        :param details: Optional details JSON string.
        :param allow_user_interaction: Allow interactive prompt.
        """
        act_id = action_id.strip()
        det = {}
        if details:
            try:
                det = json.loads(details) if isinstance(details, str) else details
            except Exception:
                det = {}

        return polkit_api.check_authorization(action_id=act_id, details=det, allow_user_interaction=allow_user_interaction)

    @strand(description="List and search registered Polkit action definitions.", tier=CapabilityTier.OBSERVE)
    def polkit_list_actions(self, filter_query: str | None = None) -> dict[str, Any]:
        """List and search registered Polkit action definitions.

        :param filter_query: Search term.
        """
        actions = polkit_api.list_actions(filter_query=filter_query)
        return {"count": len(actions), "filter": filter_query or "all", "actions": actions[:100]}

    @strand(
        description="Generate standards-compliant .policy XML definitions for custom actions.",
        tier=CapabilityTier.MUTATE,
    )
    def polkit_generate_policy(
        self,
        actions: str,
        vendor: str = "Textile Desktop Intelligence",
        vendor_url: str = "https://github.com/textile",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Generate standards-compliant .policy XML definitions for custom actions.

        :param actions: JSON array of action definitions.
        :param vendor: Vendor name.
        :param vendor_url: Vendor URL.
        :param output_path: Output file path.
        """
        try:
            parsed_actions = json.loads(actions) if isinstance(actions, str) else actions
            if not isinstance(parsed_actions, list):
                return {"success": False, "error": "actions must be a JSON array."}
        except Exception as e:
            return {"success": False, "error": f"Invalid JSON in actions: {e}"}

        return polkit_api.generate_policy(actions=parsed_actions, vendor=vendor, vendor_url=vendor_url, output_path=output_path)

    @strand(
        description="Generate a Polkit-1 JavaScript rule (.rules) for pre-authorizing specific actions.",
        tier=CapabilityTier.MUTATE,
    )
    def polkit_generate_rule(
        self,
        rule_name: str,
        action_pattern: str,
        users: str | None = None,
        groups: str | None = None,
        result: Literal["yes", "no", "auth_admin", "auth_admin_keep", "auth_self", "auth_self_keep"] = "yes",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Generate a Polkit-1 JavaScript rule (.rules) for pre-authorizing specific actions.

        :param rule_name: Descriptive rule name.
        :param action_pattern: Action ID pattern.
        :param users: JSON array of usernames.
        :param groups: JSON array of group names.
        :param result: Result.
        :param output_path: Output file path.
        """
        r_name = rule_name.strip() or "textile_rule"
        act_pattern = action_pattern.strip() or "*"

        parsed_users = None
        if users:
            try:
                parsed_users = json.loads(users) if isinstance(users, str) else users
            except Exception:
                parsed_users = [str(users)]

        parsed_groups = None
        if groups:
            try:
                parsed_groups = json.loads(groups) if isinstance(groups, str) else groups
            except Exception:
                parsed_groups = [str(groups)]

        return polkit_api.generate_rule(
            rule_name=r_name,
            action_pattern=act_pattern,
            users=parsed_users,
            groups=parsed_groups,
            result=result or "yes",
            output_path=output_path,
        )

    @strand(
        description="Execute a command with elevated privileges using pkexec CLI escalation.",
        tier=CapabilityTier.PRIVILEGED,
    )
    def polkit_pkexec(
        self,
        command: str,
        user: str = "root",
        timeout_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """Execute a command with elevated privileges using pkexec CLI escalation.

        :param command: Command string to execute.
        :param user: Target user (default 'root').
        :param timeout_seconds: Timeout in seconds.
        """
        cmd = command.strip()
        u = user.strip() or "root"
        return polkit_api.pkexec(command=cmd, user=u, timeout_seconds=timeout_seconds)
