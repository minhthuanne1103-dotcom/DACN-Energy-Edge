"""Sinh CA riêng + chứng chỉ server (mosquitto) + chứng chỉ client cho mutual TLS.

Chạy tự động một lần bởi service `certgen` trong docker-compose; bỏ qua nếu đã có ca.crt.
"""
import datetime as dt
import ipaddress
import os
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from . import config as C

CLIENTS = ("gateway", "bridge", "operator")


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Energy Edge Lab"),
                      x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)
    os.chmod(path, 0o644)      # mosquitto chạy bằng user khác trong container nên cần đọc được


def _pem_key(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _pem_cert(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def _issue(cn, ca_key, ca_cert, server=False):
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    b = (x509.CertificateBuilder().subject_name(_name(cn)).issuer_name(ca_cert.subject)
         .public_key(key.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=825))
         .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
         .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                      data_encipherment=False, key_agreement=True, key_cert_sign=False,
                                      crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
         .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if server
                                               else ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
         .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False))
    if server:
        b = b.add_extension(x509.SubjectAlternativeName([
            x509.DNSName("mosquitto"), x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
    return key, b.sign(ca_key, hashes.SHA256())


def main(out=None):
    out = out or C.CERT_DIR
    os.makedirs(out, exist_ok=True)
    if os.path.exists(os.path.join(out, "ca.crt")) and "--force" not in sys.argv:
        print("Chứng chỉ đã tồn tại, bỏ qua (dùng --force để tạo lại).")
        return
    ca_key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    ca_cert = (x509.CertificateBuilder().subject_name(_name("Energy Edge Root CA")).issuer_name(_name("Energy Edge Root CA"))
               .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
               .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                            data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                            crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
               .sign(ca_key, hashes.SHA256()))
    _write(os.path.join(out, "ca.crt"), _pem_cert(ca_cert))
    key, cert = _issue("mosquitto", ca_key, ca_cert, server=True)
    _write(os.path.join(out, "server.crt"), _pem_cert(cert))
    _write(os.path.join(out, "server.key"), _pem_key(key))
    for name in CLIENTS:
        key, cert = _issue(name, ca_key, ca_cert)
        _write(os.path.join(out, f"{name}.crt"), _pem_cert(cert))
        _write(os.path.join(out, f"{name}.key"), _pem_key(key))
    print("Đã tạo CA, chứng chỉ server và client:", ", ".join(CLIENTS))


if __name__ == "__main__":
    main()
