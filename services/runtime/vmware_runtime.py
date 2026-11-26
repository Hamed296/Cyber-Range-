import json
import random
import shutil
import socket
import string
import subprocess
import time
from pathlib import Path

from core.config import settings
from services.runtime.base import RuntimeBase, RuntimeStartResult

DEFAULT_RDP_PORT = 3389
DEFAULT_SSH_PORT = 22
DEFAULT_RDP_USER = "student"
DEFAULT_RDP_PASS = "Cyber1234"


def _rand_digits(n=5) -> str:
    return "".join(random.choice(string.digits) for _ in range(n))


def _run(cmd: list[str], allow_fail: bool = False) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if p.returncode != 0 and not allow_fail:
        raise RuntimeError(
            f"Command failed (code={p.returncode}):\n{' '.join(cmd)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )
    return p


def _wait_tcp(host: str, port: int, timeout: float = 120.0) -> None:
    end = time.time() + timeout
    last_err = None
    while time.time() < end:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError as e:
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"TCP not open: {host}:{port} (last_err={last_err})")


def _replace_or_append_vmx_line(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f'{key} = '
    new_line = f'{key} = "{value}"\n'
    replaced = False
    out = []

    for line in lines:
        if line.strip().startswith(prefix):
            out.append(new_line)
            replaced = True
        else:
            out.append(line)

    if not replaced:
        out.append(new_line)

    return out


def _set_vmx_network(vmx_path: Path, vmnet_name: str, nic_index: int = 0) -> None:
    """
    يربط NIC معيّن داخل الـ VM على custom VMnet معيّنة.
    يتطلب أن تكون VMnetX موجودة مسبقًا في VMware Workstation.
    """
    key_base = f"ethernet{nic_index}"
    lines = vmx_path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)

    lines = _replace_or_append_vmx_line(lines, f"{key_base}.present", "TRUE")
    lines = _replace_or_append_vmx_line(lines, f"{key_base}.startConnected", "TRUE")
    lines = _replace_or_append_vmx_line(lines, f"{key_base}.connectionType", "custom")
    lines = _replace_or_append_vmx_line(lines, f"{key_base}.vnet", vmnet_name)

    vmx_path.write_text("".join(lines), encoding="utf-8")


def _get_vmnet_pool() -> list[str]:
    raw = getattr(settings, "vmware_vmnet_pool", None) or "VMnet10,VMnet11,VMnet12,VMnet13"
    pool = [x.strip() for x in str(raw).split(",") if x.strip()]
    if not pool:
        raise RuntimeError("vmware_vmnet_pool is empty")
    return pool


def _get_vmnet_locks_dir() -> Path:
    base_dir = Path(settings.vm_clones_dir)
    locks_dir = base_dir / "_vmnet_locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    return locks_dir


def _acquire_vmnet(project_name: str, preferred_vmnet: str | None = None) -> tuple[str, str]:
    """
    يحجز VMnet من الـ pool عبر lock file بسيط.
    يمنع طالبين من استخدام نفس VMnet بنفس الوقت.
    يرجع:
        (vmnet_name, lock_file_path)
    """
    pool = _get_vmnet_pool()
    locks_dir = _get_vmnet_locks_dir()

    candidates = [preferred_vmnet] if preferred_vmnet else pool[:]
    if not preferred_vmnet:
        random.shuffle(candidates)

    for vmnet_name in candidates:
        if vmnet_name not in pool:
            raise RuntimeError(f"VMnet '{vmnet_name}' is not in vmware_vmnet_pool")

        lock_file = locks_dir / f"{vmnet_name}.lock"

        try:
            # x mode = create exclusively, fail if exists
            with open(lock_file, "x", encoding="utf-8") as f:
                f.write(project_name)
            return vmnet_name, str(lock_file)
        except FileExistsError:
            continue

    raise RuntimeError("No free VMnet available in vmware_vmnet_pool")


def _release_vmnet(lock_file_path: str | None) -> None:
    if not lock_file_path:
        return
    try:
        Path(lock_file_path).unlink(missing_ok=True)
    except Exception:
        pass


def _build_machine_defs(vmware: dict) -> list[dict]:
    """
    يدعم حالتين:
    1) قديم:
       {
         "template_vmx": "...",
         "clone_type": "linked"
       }

    2) جديد multi-machine:
       {
         "clone_type": "linked",
         "entry_machine": "attacker",
         "machines": [
           {
             "name": "attacker",
             "template_vmx": "...",
             "access": "rdp",
             "username": "student",
             "password": "Cyber1234"
           },
           {
             "name": "victim",
             "template_vmx": "...",
             "access": "internal"
           }
         ]
       }
    """
    machines = vmware.get("machines")
    if machines and isinstance(machines, list):
        out = []
        for m in machines:
            template_vmx = m.get("template_vmx")
            if not template_vmx:
                raise RuntimeError("Each machine must include template_vmx")

            out.append({
                "name": m.get("name") or f"machine_{len(out) + 1}",
                "template_vmx": template_vmx,
                "access": (m.get("access") or "internal").lower(),   # rdp | ssh | internal
                "username": m.get("username") or m.get("rdp_user") or DEFAULT_RDP_USER,
                "password": m.get("password") or m.get("rdp_pass") or DEFAULT_RDP_PASS,
                "rdp_port": int(m.get("rdp_port") or DEFAULT_RDP_PORT),
                "ssh_port": int(m.get("ssh_port") or DEFAULT_SSH_PORT),
                "nic_index": int(m.get("nic_index") or 0),
            })
        return out

    template_vmx = vmware.get("template_vmx")
    if not template_vmx:
        raise RuntimeError("scenario.json must include vmware.template_vmx or vmware.machines[]")

    return [{
        "name": "default",
        "template_vmx": template_vmx,
        "access": (vmware.get("access") or "rdp").lower(),
        "username": vmware.get("rdp_user") or DEFAULT_RDP_USER,
        "password": vmware.get("rdp_pass") or DEFAULT_RDP_PASS,
        "rdp_port": int(vmware.get("rdp_port") or DEFAULT_RDP_PORT),
        "ssh_port": int(vmware.get("ssh_port") or DEFAULT_SSH_PORT),
        "nic_index": 0,
    }]


def _get_entry_machine_name(vmware: dict, machine_defs: list[dict]) -> str:
    entry = vmware.get("entry_machine")
    if entry:
        return entry

    for m in machine_defs:
        if m["access"] in ("rdp", "ssh"):
            return m["name"]

    return machine_defs[0]["name"]


class VmwareRuntime(RuntimeBase):
    """
    VMware Runtime:
    - يدعم single VM و multi-machine
    - يعزل كل Session على VMnet خاصة
    - يربط جميع ماكينات السيناريو بنفس VMnet الخاصة بالطالب
    - يعرض فقط entry machine للطالب
    - يمنع تعارض VMnet بين الطلاب عبر lock file
    """

    def start(self, user, scenario) -> RuntimeStartResult:
        scenario_dir = settings.scenarios_dir / scenario.path
        meta_file = scenario_dir / "scenario.json"
        if not meta_file.exists():
            raise RuntimeError(f"scenario.json not found: {meta_file}")

        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        vmware = meta.get("vmware") or {}

        clone_type = (vmware.get("clone_type") or "linked").lower()
        clone_mode = "linked" if clone_type == "linked" else "full"

        machine_defs = _build_machine_defs(vmware)
        entry_machine_name = _get_entry_machine_name(vmware, machine_defs)

        clones_root = Path(settings.vm_clones_dir)
        clones_root.mkdir(parents=True, exist_ok=True)

        project_name = f"cr_u{user.id}_s{scenario.id}_{_rand_digits(5)}"
        clone_dir = clones_root / project_name
        clone_dir.mkdir(parents=True, exist_ok=True)

        created_vmx_paths: list[str] = []
        machine_states: list[dict] = []
        vmnet_name = None
        vmnet_lock_file = None

        try:
            # ✅ حجز VMnet غير مستخدمة لهذه الجلسة
            preferred_vmnet = vmware.get("vmnet")
            vmnet_name, vmnet_lock_file = _acquire_vmnet(project_name, preferred_vmnet)

            # 1) Clone + attach same private network + start all VMs
            for m in machine_defs:
                machine_name = m["name"]
                machine_dir = clone_dir / machine_name
                machine_dir.mkdir(parents=True, exist_ok=True)

                target_vmx = machine_dir / f"{machine_name}.vmx"

                _run([settings.vmrun_path, "clone", m["template_vmx"], str(target_vmx), clone_mode])

                # اربطها بالشبكة الخاصة لنفس الطالب
                _set_vmx_network(target_vmx, vmnet_name, nic_index=m["nic_index"])

                _run([settings.vmrun_path, "start", str(target_vmx), "nogui"])

                created_vmx_paths.append(str(target_vmx))
                machine_states.append({
                    "name": machine_name,
                    "vmx_path": str(target_vmx),
                    "access": m["access"],
                    "username": m["username"],
                    "password": m["password"],
                    "rdp_port": m["rdp_port"],
                    "ssh_port": m["ssh_port"],
                })

            # 2) تأكد أنها شغالة
            lst = _run([settings.vmrun_path, "list"])
            running_text = lst.stdout or ""
            for vmx_path in created_vmx_paths:
                if vmx_path not in running_text:
                    raise RuntimeError(f"VM not running after start: {vmx_path}\nvmrun list:\n{running_text}")

            # 3) اجلب IPs وانتظر الخدمات المطلوبة
            entry_state = None

            for s in machine_states:
                p = _run([settings.vmrun_path, "getGuestIPAddress", s["vmx_path"], "-wait"])
                guest_ip = (p.stdout or "").strip()
                if not guest_ip:
                    raise RuntimeError(
                        f"Failed to get guest IP for machine '{s['name']}'. Ensure VMware Tools is installed."
                    )

                s["guest_ip"] = guest_ip

                if s["access"] == "rdp":
                    _wait_tcp(guest_ip, s["rdp_port"], timeout=180.0)
                    s["access_url"] = f"{guest_ip}:{s['rdp_port']}"
                elif s["access"] == "ssh":
                    _wait_tcp(guest_ip, s["ssh_port"], timeout=180.0)
                    s["access_url"] = f"{guest_ip}:{s['ssh_port']}"
                else:
                    s["access_url"] = None

                if s["name"] == entry_machine_name:
                    entry_state = s

            if not entry_state:
                raise RuntimeError(f"entry_machine '{entry_machine_name}' not found")

            # 4) جهّز targets الداخلية فقط
            targets = []
            for s in machine_states:
                if s["name"] == entry_machine_name:
                    continue
                targets.append({
                    "name": s["name"],
                    "ip": s.get("guest_ip"),
                    "access": s.get("access"),
                })

            runtime_data = {
                "type": "vm_rdp" if entry_state["access"] == "rdp" else "vm_ssh",
                "project_name": project_name,
                "clone_dir": str(clone_dir),
                "vmnet_name": vmnet_name,
                "vmnet_lock_file": vmnet_lock_file,
                "entry_machine": {
                    "name": entry_state["name"],
                    "vmx_path": entry_state["vmx_path"],
                    "guest_ip": entry_state["guest_ip"],
                    "access": entry_state["access"],
                    "username": entry_state["username"],
                    "password": entry_state["password"],
                    "port": entry_state["rdp_port"] if entry_state["access"] == "rdp" else entry_state["ssh_port"],
                    "access_url": entry_state["access_url"],
                },
                "machines": machine_states,
                "targets": targets,

                # للتوافق مع كودك الحالي
                "vmx_path": entry_state["vmx_path"],
                "guest_ip": entry_state["guest_ip"],
                "rdp_port": entry_state["rdp_port"] if entry_state["access"] == "rdp" else None,
                "rdp_user": entry_state["username"] if entry_state["access"] == "rdp" else None,
                "rdp_pass": entry_state["password"] if entry_state["access"] == "rdp" else None,
                "access_url": entry_state["access_url"],
            }

            return RuntimeStartResult(
                access_url=entry_state["access_url"] or "",
                runtime_data=runtime_data,
            )

        except Exception:
            for vmx_path in created_vmx_paths:
                _run([settings.vmrun_path, "stop", vmx_path, "hard"], allow_fail=True)
                _run([settings.vmrun_path, "deleteVM", vmx_path], allow_fail=True)

            shutil.rmtree(clone_dir, ignore_errors=True)
            _release_vmnet(vmnet_lock_file)
            raise

    def stop(self, runtime_data: dict) -> None:
        clone_dir = runtime_data.get("clone_dir")
        machines = runtime_data.get("machines") or []
        vmnet_lock_file = runtime_data.get("vmnet_lock_file")

        if machines:
            for m in machines:
                vmx_path = m.get("vmx_path")
                if not vmx_path:
                    continue
                _run([settings.vmrun_path, "stop", vmx_path, "hard"], allow_fail=True)
                _run([settings.vmrun_path, "deleteVM", vmx_path], allow_fail=True)
        else:
            # fallback للتوافق مع runtime_data القديم
            vmx_path = runtime_data.get("vmx_path")
            if vmx_path:
                _run([settings.vmrun_path, "stop", vmx_path, "hard"], allow_fail=True)
                _run([settings.vmrun_path, "deleteVM", vmx_path], allow_fail=True)

        if clone_dir:
            shutil.rmtree(clone_dir, ignore_errors=True)

        # ✅ فك حجز VMnet بعد انتهاء الجلسة
        _release_vmnet(vmnet_lock_file)