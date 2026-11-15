"""Zero-Config Local Root CA & SAN Leaf Certificate Generator for KaizenReader.

Enables a trusted HTTPS Secure Context over USB-C tethering, Mac-to-iPhone
ad-hoc Wi-Fi, or local LAN so iOS WebKit unlocks Service Workers (`sw.js`),
persistent IndexedDB storage (`navigator.storage.persist()`), and lock-screen
media session controls without requiring public internet or paid certificates.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Tuple

from src.config import DATA_DIR, get_local_ip

CERTS_DIR = DATA_DIR / "certs"
CA_KEY_PATH = CERTS_DIR / "kaizen-root-ca.key"
CA_CERT_PATH = CERTS_DIR / "kaizen-root-ca.pem"
SERVER_KEY_PATH = CERTS_DIR / "kaizen-server.key"
SERVER_CSR_PATH = CERTS_DIR / "kaizen-server.csr"
SERVER_CERT_PATH = CERTS_DIR / "kaizen-server.pem"
OPENSSL_CNF_PATH = CERTS_DIR / "kaizen-openssl.cnf"


def _collect_local_ips() -> list[str]:
    """Collect active non-loopback IPv4 addresses (LAN, USB-C tether, Tailscale 100.x)."""
    ips: list[str] = []
    primary = get_local_ip()
    if primary and primary != "127.0.0.1":
        ips.append(primary)
    try:
        out = subprocess.run(
            ["/sbin/ifconfig"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[1]
                    if ip != "127.0.0.1" and "." in ip and ip not in ips:
                        ips.append(ip)
    except Exception:
        pass
    return sorted(ips)


def ensure_local_tls_certs(force_regen: bool = False) -> Tuple[Path, Path, Path]:
    """Ensure local Root CA and SAN leaf certificate exist; return (server_cert, server_key, ca_cert)."""
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    local_ip = get_local_ip()
    all_ips = _collect_local_ips()
    san_signature = ",".join(all_ips) if all_ips else local_ip

    # Check if existing cert already covers current LAN + Tailscale + USB IPs
    ip_marker = CERTS_DIR / ".last_san_ip"
    cached_sig = ip_marker.read_text(encoding="utf-8").strip() if ip_marker.exists() else ""

    if (
        not force_regen
        and CA_CERT_PATH.exists()
        and SERVER_CERT_PATH.exists()
        and SERVER_KEY_PATH.exists()
        and cached_sig == san_signature
    ):
        return SERVER_CERT_PATH, SERVER_KEY_PATH, CA_CERT_PATH

    # 1. Generate Root CA if not already created (10-year validity so user only trusts it once)
    if not CA_KEY_PATH.exists() or not CA_CERT_PATH.exists():
        subprocess.run(
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-new",
                "-nodes",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(CA_KEY_PATH),
                "-sha256",
                "-days",
                "3650",
                "-out",
                str(CA_CERT_PATH),
                "-subj",
                "/C=US/ST=California/O=KaizenReader Sovereign Vault/CN=KaizenReader Local Root CA",
            ],
            check=True,
            capture_output=True,
        )

    # 2. Build SAN OpenSSL configuration covering localhost, *.local, *.ts.net, and all active LAN/Tailscale IPs
    san_entries = [
        "DNS.1 = localhost",
        "DNS.2 = kaizen.local",
        "DNS.3 = *.local",
        "DNS.4 = *.ts.net",
        "IP.1 = 127.0.0.1",
    ]
    for idx, ip_addr in enumerate(all_ips, start=2):
        san_entries.append(f"IP.{idx} = {ip_addr}")

    cnf_content = "\n".join(
        [
            "[req]",
            "default_bits = 2048",
            "prompt = no",
            "default_md = sha256",
            "distinguished_name = dn",
            "req_extensions = v3_req",
            "",
            "[dn]",
            "C = US",
            "ST = California",
            "O = KaizenReader Atelier",
            f"CN = {local_ip}",
            "",
            "[v3_req]",
            "basicConstraints = CA:FALSE",
            "keyUsage = nonRepudiation, digitalSignature, keyEncipherment",
            "extendedKeyUsage = serverAuth",
            "subjectAltName = @alt_names",
            "",
            "[alt_names]",
            *san_entries,
            "",
        ]
    )
    OPENSSL_CNF_PATH.write_text(cnf_content, encoding="utf-8")

    # 3. Generate server key and CSR
    subprocess.run(
        [
            "/usr/bin/openssl",
            "req",
            "-new",
            "-nodes",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(SERVER_KEY_PATH),
            "-out",
            str(SERVER_CSR_PATH),
            "-config",
            str(OPENSSL_CNF_PATH),
        ],
        check=True,
        capture_output=True,
    )

    # 4. Sign leaf certificate with Root CA (825-day maximum Apple iOS trusted leaf validity)
    subprocess.run(
        [
            "/usr/bin/openssl",
            "x509",
            "-req",
            "-in",
            str(SERVER_CSR_PATH),
            "-CA",
            str(CA_CERT_PATH),
            "-CAkey",
            str(CA_KEY_PATH),
            "-CAcreateserial",
            "-out",
            str(SERVER_CERT_PATH),
            "-days",
            "824",
            "-sha256",
            "-extensions",
            "v3_req",
            "-extfile",
            str(OPENSSL_CNF_PATH),
        ],
        check=True,
        capture_output=True,
    )

    ip_marker.write_text(san_signature, encoding="utf-8")
    return SERVER_CERT_PATH, SERVER_KEY_PATH, CA_CERT_PATH


def get_tls_info(port: int) -> Dict[str, str | bool]:
    """Return status and URLs for local TLS certificate provisioning."""
    local_ip = get_local_ip()
    has_ca = CA_CERT_PATH.exists()
    return {
        "has_ca": has_ca,
        "local_ip": local_ip,
        "https_url": f"https://{local_ip}:{port}",
        "http_url": f"http://{local_ip}:{port}",
        "ca_download_path": "/api/trust-profile",
    }
